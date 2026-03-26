-- 用户认证相关表结构
-- 此脚本在 PostgreSQL 启动时自动执行

-- =============================================
-- 用户表
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    
    -- 状态
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- 元数据
    metadata JSONB DEFAULT '{}',
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE,
    
    -- 约束
    CONSTRAINT users_email_check CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT users_role_check CHECK (role IN ('user', 'admin'))
);

-- 邮箱索引（用于登录查询）
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 角色索引
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 活跃用户索引
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE is_active = TRUE;

-- 更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Refresh Token 表（用于 Token 管理和吊销）
-- =============================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    
    -- Token 元数据
    device_info VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    
    -- 状态
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(100),
    
    -- 时间
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- 索引
    CONSTRAINT refresh_tokens_expires_check CHECK (expires_at > created_at)
);

-- 用户 ID 索引（用于查找用户的所有 Token）
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);

-- Token 哈希索引（用于验证）
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);

-- 过期 Token 索引（用于清理）
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- 未撤销 Token 索引
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens(user_id, is_revoked) 
WHERE is_revoked = FALSE;

-- =============================================
-- Token 黑名单表（用于紧急吊销 Access Token）
-- =============================================
CREATE TABLE IF NOT EXISTS token_blacklist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jti VARCHAR(255) NOT NULL UNIQUE,  -- JWT Token ID
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- 原因
    reason VARCHAR(255),
    
    -- 时间
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL  -- Token 原本过期时间
);

-- JTI 索引（用于验证）
CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON token_blacklist(jti);

-- 过期索引（用于清理）
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist(expires_at);

-- =============================================
-- 登录日志表（审计和安全）
-- =============================================
CREATE TABLE IF NOT EXISTS login_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    
    -- 结果
    success BOOLEAN NOT NULL,
    failure_reason VARCHAR(100),
    
    -- 请求信息
    ip_address INET,
    user_agent TEXT,
    
    -- 时间
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 用户登录历史索引
CREATE INDEX IF NOT EXISTS idx_login_logs_user_id ON login_logs(user_id);

-- 时间索引（用于审计查询）
CREATE INDEX IF NOT EXISTS idx_login_logs_created_at ON login_logs(created_at);

-- IP 地址索引（用于安全分析）
CREATE INDEX IF NOT EXISTS idx_login_logs_ip ON login_logs(ip_address);

-- 失败登录索引（用于检测暴力破解）
CREATE INDEX IF NOT EXISTS idx_login_logs_failures ON login_logs(email, created_at) 
WHERE success = FALSE;

-- =============================================
-- 清理过期数据的函数
-- =============================================
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER := 0;
BEGIN
    -- 删除过期的 Refresh Token
    WITH deleted_refresh AS (
        DELETE FROM refresh_tokens 
        WHERE expires_at < CURRENT_TIMESTAMP
        RETURNING id
    )
    SELECT COUNT(*) INTO deleted_count FROM deleted_refresh;
    
    -- 删除过期的黑名单记录
    WITH deleted_blacklist AS (
        DELETE FROM token_blacklist 
        WHERE expires_at < CURRENT_TIMESTAMP
        RETURNING id
    )
    SELECT deleted_count + COUNT(*) INTO deleted_count FROM deleted_blacklist;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================
-- 用于统计的视图
-- =============================================
CREATE OR REPLACE VIEW user_stats AS
SELECT 
    u.id,
    u.email,
    u.name,
    u.role,
    u.is_active,
    u.created_at,
    u.last_login_at,
    COUNT(DISTINCT rt.id) FILTER (WHERE rt.is_revoked = FALSE AND rt.expires_at > CURRENT_TIMESTAMP) as active_sessions,
    COUNT(DISTINCT ll.id) FILTER (WHERE ll.success = TRUE AND ll.created_at > CURRENT_TIMESTAMP - INTERVAL '30 days') as logins_last_30_days
FROM users u
LEFT JOIN refresh_tokens rt ON u.id = rt.user_id
LEFT JOIN login_logs ll ON u.id = ll.user_id
GROUP BY u.id;

-- =============================================
-- 注释
-- =============================================
COMMENT ON TABLE users IS '用户账户表';
COMMENT ON TABLE refresh_tokens IS 'JWT Refresh Token 存储表';
COMMENT ON TABLE token_blacklist IS 'Access Token 黑名单（紧急吊销）';
COMMENT ON TABLE login_logs IS '登录日志（审计和安全）';
COMMENT ON FUNCTION cleanup_expired_tokens IS '清理过期 Token 的定时任务函数';
COMMENT ON VIEW user_stats IS '用户统计视图';
