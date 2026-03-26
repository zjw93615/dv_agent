"""
用户数据存储层

提供用户和 Token 的持久化存储操作
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .models import LoginLog, RefreshToken, User, UserCreate, UserRole
from .security import password_hasher, token_hasher

logger = logging.getLogger(__name__)


class UserRepository:
    """用户数据仓库"""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        初始化用户仓库
        
        Args:
            pool: PostgreSQL 连接池
        """
        self._pool = pool
    
    async def create(self, user_create: UserCreate) -> User:
        """
        创建新用户
        
        Args:
            user_create: 用户创建请求
            
        Returns:
            创建的用户对象
            
        Raises:
            ValueError: 如果邮箱已存在
        """
        # 哈希密码
        password_hash = password_hasher.hash(user_create.password)
        
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, password_hash, name, role)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, email, password_hash, name, role, is_active, 
                              is_verified, metadata, created_at, updated_at, last_login_at
                    """,
                    user_create.email,
                    password_hash,
                    user_create.name,
                    UserRole.USER.value,
                )
                
                return self._row_to_user(row)
                
            except asyncpg.UniqueViolationError:
                raise ValueError("Email already registered")
    
    async def get_by_id(self, user_id: str) -> Optional[User]:
        """
        根据 ID 获取用户
        
        Args:
            user_id: 用户 ID
            
        Returns:
            用户对象，不存在返回 None
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, email, password_hash, name, role, is_active,
                       is_verified, metadata, created_at, updated_at, last_login_at
                FROM users WHERE id = $1
                """,
                user_id,
            )
            
            return self._row_to_user(row) if row else None
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        根据邮箱获取用户
        
        Args:
            email: 用户邮箱
            
        Returns:
            用户对象，不存在返回 None
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, email, password_hash, name, role, is_active,
                       is_verified, metadata, created_at, updated_at, last_login_at
                FROM users WHERE email = $1
                """,
                email.lower(),
            )
            
            return self._row_to_user(row) if row else None
    
    async def update_last_login(self, user_id: str) -> None:
        """
        更新最后登录时间
        
        Args:
            user_id: 用户 ID
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET last_login_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                user_id,
            )
    
    async def update_password(self, user_id: str, new_password: str) -> None:
        """
        更新用户密码
        
        Args:
            user_id: 用户 ID
            new_password: 新密码（明文）
        """
        password_hash = password_hasher.hash(new_password)
        
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET password_hash = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                user_id,
                password_hash,
            )
    
    async def deactivate(self, user_id: str) -> None:
        """
        停用用户
        
        Args:
            user_id: 用户 ID
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                user_id,
            )
    
    async def verify_credentials(self, email: str, password: str) -> Optional[User]:
        """
        验证用户凭据
        
        Args:
            email: 用户邮箱
            password: 用户密码
            
        Returns:
            用户对象（验证成功）或 None（验证失败）
        """
        user = await self.get_by_email(email)
        
        if not user:
            return None
        
        if not password_hasher.verify(password, user.password_hash):
            return None
        
        if not user.is_active:
            return None
        
        return user
    
    def _row_to_user(self, row: asyncpg.Record) -> User:
        """将数据库行转换为 User 对象"""
        import json
        
        # 处理 metadata 字段（可能是字符串或字典）
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        elif metadata is None:
            metadata = {}
        
        return User(
            id=str(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            name=row["name"],
            role=UserRole(row["role"]),
            is_active=row["is_active"],
            is_verified=row["is_verified"],
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )


class RefreshTokenRepository:
    """Refresh Token 数据仓库"""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        初始化 Token 仓库
        
        Args:
            pool: PostgreSQL 连接池
        """
        self._pool = pool
    
    async def create(
        self,
        user_id: str,
        token: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_info: Optional[str] = None,
    ) -> RefreshToken:
        """
        创建 Refresh Token 记录
        
        Args:
            user_id: 用户 ID
            token: 原始 Token
            expires_at: 过期时间
            ip_address: IP 地址
            user_agent: User Agent
            device_info: 设备信息
            
        Returns:
            Token 记录
        """
        # 哈希 Token
        token_hash = token_hasher.hash(token)
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO refresh_tokens 
                    (user_id, token_hash, expires_at, ip_address, user_agent, device_info)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, user_id, token_hash, device_info, ip_address, user_agent,
                          is_revoked, revoked_at, revoked_reason, created_at, expires_at, last_used_at
                """,
                user_id,
                token_hash,
                expires_at,
                ip_address,
                user_agent,
                device_info,
            )
            
            return self._row_to_refresh_token(row)
    
    async def get_by_token(self, token: str) -> Optional[RefreshToken]:
        """
        根据 Token 获取记录
        
        Args:
            token: 原始 Token
            
        Returns:
            Token 记录，不存在返回 None
        """
        token_hash = token_hasher.hash(token)
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, token_hash, device_info, ip_address, user_agent,
                       is_revoked, revoked_at, revoked_reason, created_at, expires_at, last_used_at
                FROM refresh_tokens WHERE token_hash = $1
                """,
                token_hash,
            )
            
            return self._row_to_refresh_token(row) if row else None
    
    async def update_last_used(self, token_id: str) -> None:
        """
        更新 Token 最后使用时间
        
        Args:
            token_id: Token 记录 ID
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE refresh_tokens SET last_used_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                token_id,
            )
    
    async def revoke(
        self,
        token_id: str,
        reason: str = "user_logout",
    ) -> None:
        """
        撤销 Token
        
        Args:
            token_id: Token 记录 ID
            reason: 撤销原因
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE refresh_tokens 
                SET is_revoked = TRUE, revoked_at = CURRENT_TIMESTAMP, revoked_reason = $2
                WHERE id = $1
                """,
                token_id,
                reason,
            )
    
    async def revoke_by_token(self, token: str, reason: str = "user_logout") -> bool:
        """
        根据 Token 撤销
        
        Args:
            token: 原始 Token
            reason: 撤销原因
            
        Returns:
            是否成功撤销
        """
        token_hash = token_hasher.hash(token)
        
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE refresh_tokens 
                SET is_revoked = TRUE, revoked_at = CURRENT_TIMESTAMP, revoked_reason = $2
                WHERE token_hash = $1 AND is_revoked = FALSE
                """,
                token_hash,
                reason,
            )
            
            return result.split()[-1] != "0"
    
    async def revoke_all_for_user(
        self,
        user_id: str,
        reason: str = "logout_all",
    ) -> int:
        """
        撤销用户的所有 Token
        
        Args:
            user_id: 用户 ID
            reason: 撤销原因
            
        Returns:
            撤销的 Token 数量
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE refresh_tokens 
                SET is_revoked = TRUE, revoked_at = CURRENT_TIMESTAMP, revoked_reason = $2
                WHERE user_id = $1 AND is_revoked = FALSE
                """,
                user_id,
                reason,
            )
            
            return int(result.split()[-1])
    
    async def is_valid(self, token: str) -> bool:
        """
        检查 Token 是否有效
        
        Args:
            token: 原始 Token
            
        Returns:
            是否有效
        """
        token_record = await self.get_by_token(token)
        
        if not token_record:
            return False
        
        if token_record.is_revoked:
            return False
        
        if token_record.expires_at < datetime.now(timezone.utc):
            return False
        
        return True
    
    async def cleanup_expired(self) -> int:
        """
        清理过期的 Token
        
        Returns:
            删除的记录数
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM refresh_tokens WHERE expires_at < CURRENT_TIMESTAMP
                """
            )
            
            return int(result.split()[-1])
    
    def _row_to_refresh_token(self, row: asyncpg.Record) -> RefreshToken:
        """将数据库行转换为 RefreshToken 对象"""
        return RefreshToken(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            token_hash=row["token_hash"],
            device_info=row["device_info"],
            ip_address=str(row["ip_address"]) if row["ip_address"] else None,
            user_agent=row["user_agent"],
            is_revoked=row["is_revoked"],
            revoked_at=row["revoked_at"],
            revoked_reason=row["revoked_reason"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
        )


class LoginLogRepository:
    """登录日志仓库"""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        初始化日志仓库
        
        Args:
            pool: PostgreSQL 连接池
        """
        self._pool = pool
    
    async def create(
        self,
        email: str,
        success: bool,
        user_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> LoginLog:
        """
        创建登录日志
        
        Args:
            email: 登录邮箱
            success: 是否成功
            user_id: 用户 ID
            failure_reason: 失败原因
            ip_address: IP 地址
            user_agent: User Agent
            
        Returns:
            日志记录
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO login_logs (email, success, user_id, failure_reason, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, user_id, email, success, failure_reason, ip_address, user_agent, created_at
                """,
                email,
                success,
                user_id,
                failure_reason,
                ip_address,
                user_agent,
            )
            
            return LoginLog(
                id=str(row["id"]),
                user_id=str(row["user_id"]) if row["user_id"] else None,
                email=row["email"],
                success=row["success"],
                failure_reason=row["failure_reason"],
                ip_address=str(row["ip_address"]) if row["ip_address"] else None,
                user_agent=row["user_agent"],
                created_at=row["created_at"],
            )
    
    async def count_recent_failures(
        self,
        email: str,
        minutes: int = 30,
    ) -> int:
        """
        统计近期失败登录次数
        
        Args:
            email: 登录邮箱
            minutes: 时间范围（分钟）
            
        Returns:
            失败次数
        """
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM login_logs
                WHERE email = $1 AND success = FALSE
                AND created_at > CURRENT_TIMESTAMP - INTERVAL '%s minutes'
                """,
                email,
                minutes,
            )
            
            return count or 0
