## ADDED Requirements

### Requirement: System SHALL support user registration

系统 SHALL 允许新用户通过邮箱和��码注册账户。

**注册数据**:
- email: 必填，有效邮箱格式，唯一
- password: 必填，最少 8 字符，包含字母和数字
- name: 可选，显示名称

#### Scenario: 成功注册
- **WHEN** 用户提交有效的注册信息
- **THEN** 系统 SHALL 创建用户账户
- **AND** 返回用户 ID 和 Access Token
- **AND** 密码 SHALL 使用 bcrypt 哈希存储

#### Scenario: 邮箱已存在
- **WHEN** 用户使用已注册的邮箱注册
- **THEN** 系统 SHALL 返回 409 Conflict
- **AND** 错误信息为 "Email already registered"

#### Scenario: 密码强度不足
- **WHEN** 用户提交少于 8 字符的密码
- **THEN** 系统 SHALL 返回 400 Bad Request
- **AND** 错误信息包含密码要求说明

#### Scenario: 邮箱格式无效
- **WHEN** 用户提交无效邮箱格式
- **THEN** 系统 SHALL 返回 400 Bad Request

---

### Requirement: System SHALL support user login

系统 SHALL 允许注册用户通过邮箱和密码登录。

**登录响应**:
- access_token: JWT Access Token（15 分钟有效）
- refresh_token: 设置为 HttpOnly Cookie（7 天有效）
- user: 用户基本信息

#### Scenario: 成功登录
- **WHEN** 用户提交正确的邮箱和密码
- **THEN** 系统 SHALL 返回 Access Token
- **AND** 设置 Refresh Token 到 HttpOnly Cookie
- **AND** 返回用户基本信息（id, email, name）

#### Scenario: 密码错误
- **WHEN** 用户提交错误的密码
- **THEN** 系统 SHALL 返回 401 Unauthorized
- **AND** 错误信息为 "Invalid credentials"

#### Scenario: 用户不存在
- **WHEN** 用户使用未注册的邮箱登录
- **THEN** 系统 SHALL 返回 401 Unauthorized
- **AND** 错误信息为 "Invalid credentials"（不透露用户是否存在）

---

### Requirement: System SHALL support token refresh

系统 SHALL 允许使用 Refresh Token 获取新的 Access Token。

#### Scenario: 成功刷新
- **WHEN** 请求携带有效的 Refresh Token Cookie
- **THEN** 系统 SHALL 返回新的 Access Token
- **AND** 可选地轮换 Refresh Token

#### Scenario: Refresh Token 过期
- **WHEN** Refresh Token 已过期
- **THEN** 系统 SHALL 返回 401 Unauthorized
- **AND** 清除 Refresh Token Cookie
- **AND** 客户端 SHALL 重新登录

#### Scenario: Refresh Token 无效
- **WHEN** Refresh Token 签名无效或被篡改
- **THEN** 系统 SHALL 返回 401 Unauthorized

---

### Requirement: System SHALL support user logout

系统 SHALL 允许用户安全登出。

#### Scenario: 成功登出
- **WHEN** 用户请求登出
- **THEN** 系统 SHALL 清除 Refresh Token Cookie
- **AND** 可选地将 Token 加入黑名单（如果实现）

---

### Requirement: System SHALL provide current user info

系统 SHALL 提供端点获取当前登录用户信息。

#### Scenario: 获取用户信息
- **WHEN** 已认证用户请求 `/auth/me`
- **THEN** 系统 SHALL 返回用户信息
- **AND** 包含 id, email, name, created_at

#### Scenario: 未认证请求
- **WHEN** 未携带有效 Token 请求 `/auth/me`
- **THEN** 系统 SHALL 返回 401 Unauthorized

---

### Requirement: JWT Token SHALL contain user claims

系统签发的 JWT Token SHALL 包含必要的用户声明。

**Token Payload 结构**:
```json
{
  "sub": "<user_id>",
  "email": "<user_email>",
  "role": "user|admin",
  "exp": <expiration_timestamp>,
  "iat": <issued_at_timestamp>,
  "jti": "<unique_token_id>"
}
```

#### Scenario: Token 包含必要声明
- **WHEN** 系统签发 Access Token
- **THEN** Token payload SHALL 包含 sub, email, role, exp, iat, jti 字段

#### Scenario: Token 使用正确算法签名
- **WHEN** 系统签发 Token
- **THEN** Token SHALL 使用 HS256 算法签名
- **AND** 使用服务器配置的密钥

---

### Requirement: System SHALL secure password storage

系统 SHALL 安全存储用户密码。

#### Scenario: 密码哈希存储
- **WHEN** 用户注册或更改密码
- **THEN** 系统 SHALL 使用 bcrypt 算法哈希密码
- **AND** 使用至少 12 轮加盐

#### Scenario: 原始密码不可恢复
- **WHEN** 数据库泄露
- **THEN** 攻击者 SHALL NOT 能从哈希值恢复原始密码
