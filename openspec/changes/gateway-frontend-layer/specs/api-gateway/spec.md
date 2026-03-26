## ADDED Requirements

### Requirement: Gateway SHALL route requests to backend services

系统 SHALL 根据 URL 路径将请求路由到正确的后端服务。

| 路径模式 | 目标服务 | 描述 |
|---------|---------|------|
| `/auth/*` | Auth Service | 认证相关 |
| `/api/v1/*` | DV-Agent API | 业务 API |
| `/api/rag/*` | DV-Agent API | RAG API |
| `/ws` | DV-Agent API | WebSocket |
| `/stream` | DV-Agent API | SSE 流 |

#### Scenario: API 路由正常工作
- **WHEN** 客户端请求 `/api/v1/sessions`
- **THEN** 网关 SHALL 将请求转发到 DV-Agent API 的 `/sessions` 端点

#### Scenario: WebSocket 路由正常工作
- **WHEN** 客户端请求升级到 WebSocket (`/ws`)
- **THEN** 网关 SHALL 建立到后端的 WebSocket 代理连接

---

### Requirement: Gateway SHALL enforce JWT authentication

系统 SHALL 对受保护的 API 端点验证 JWT Token。

**受保护端点**:
- `/api/v1/*`
- `/api/rag/*`
- `/ws`
- `/stream`

**公开端点**（无需认证）:
- `/auth/*`
- `/health`

#### Scenario: 有效 Token 通过验证
- **WHEN** 请求包含有效的 `Authorization: Bearer <token>` 头
- **THEN** 网关 SHALL 允许请求通过并注入 `X-User-ID` 头到后端

#### Scenario: 无 Token 被拒绝
- **WHEN** 请求缺少 Authorization 头
- **THEN** 网关 SHALL 返回 401 Unauthorized

#### Scenario: 过期 Token 被拒绝
- **WHEN** 请求包含过期的 JWT Token
- **THEN** 网关 SHALL 返回 401 Unauthorized 并包含 `Token expired` 错误信息

#### Scenario: 无效签名被拒绝
- **WHEN** 请求包含签名无效的 JWT Token
- **THEN** 网关 SHALL 返回 401 Unauthorized 并包含 `Invalid signature` 错误信息

---

### Requirement: Gateway SHALL enforce rate limiting

系统 SHALL 对 API 请求实施多级限流策略。

**限流配置**:
| 路由 | 限流键 | 速率 | 突发 |
|------|--------|------|------|
| `/auth/*` | IP 地址 | 10 req/s | 20 |
| `/api/v1/*` | 用户 ID | 30 req/s | 50 |
| `/api/rag/documents/upload` | 用户 ID | 5 req/min | 10 |
| `/api/rag/search` | 用户 ID | 30 req/s | 60 |

#### Scenario: 正常请求通过
- **WHEN** 用户在限流阈值内发送请求
- **THEN** 网关 SHALL 允许请求通过

#### Scenario: 超出限流被拒绝
- **WHEN** 用户在 1 秒内发送超过 30 次 API 请求
- **THEN** 网关 SHALL 返回 429 Too Many Requests
- **AND** 响应 SHALL 包含 `Retry-After` 头

#### Scenario: 登录接口防暴力破解
- **WHEN** 同一 IP 在 1 秒内发送超过 10 次登录请求
- **THEN** 网关 SHALL 返回 429 并阻止后续请求 60 秒

---

### Requirement: Gateway SHALL support response caching

系统 SHALL 对特定 GET 请求启用响应缓存以提升性能。

**缓存配置**:
| 端点 | 缓存 TTL | 缓存键 |
|------|---------|--------|
| `GET /api/v1/sessions` | 60s | user_id + uri |
| `GET /api/rag/documents` | 30s | user_id + uri + query |
| `GET /api/rag/search/simple` | 30s | user_id + query |

#### Scenario: 缓存命中
- **WHEN** 相同用户在 60 秒内请求相同的会话列表
- **THEN** 网关 SHALL 直接返回缓存响应
- **AND** 响应 SHALL 包含 `X-Cache: HIT` 头

#### Scenario: 缓存未命中
- **WHEN** 用户首次请求会话列表
- **THEN** 网关 SHALL 将请求转发到后端
- **AND** 响应 SHALL 包含 `X-Cache: MISS` 头

---

### Requirement: Gateway SHALL handle CORS

系统 SHALL 正确处理跨域资源共享 (CORS) 请求。

**CORS 配置**:
- 允许的来源: 配置的前端域名列表
- 允许的方法: GET, POST, PUT, DELETE, OPTIONS
- 允许的头: Authorization, Content-Type, X-Request-ID
- 暴露的头: X-Request-ID, X-Cache
- 允许凭证: true
- 预检缓存: 86400 秒

#### Scenario: 预检请求处理
- **WHEN** 浏览器发送 OPTIONS 预检请求
- **THEN** 网关 SHALL 返回 204 并包含正确的 CORS 头

#### Scenario: 跨域请求通过
- **WHEN** 来自允许域名的请求
- **THEN** 响应 SHALL 包含 `Access-Control-Allow-Origin` 头

#### Scenario: 非允许域名被拒绝
- **WHEN** 来自非配置域名的请求
- **THEN** 网关 SHALL 不返回 CORS 头，浏览器将阻止请求

---

### Requirement: Gateway SHALL provide health check endpoint

系统 SHALL 提供健康检查端点供监控系统使用。

#### Scenario: 网关健康
- **WHEN** 请求 `/apisix/status`
- **THEN** 系统 SHALL 返回 200 OK
- **AND** 响应 SHALL 包含网关状态信息

#### Scenario: 后端健康检查
- **WHEN** 网关定期探测后端 `/health` 端点
- **THEN** 系统 SHALL 根据响应状态更新上游节点健康状态
- **AND** 不健康节点 SHALL 被临时移出负载均衡池
