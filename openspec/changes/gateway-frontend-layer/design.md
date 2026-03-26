## Context

当前 DV-Agent 是一个功能完善的 AI Agent 系统，包含：
- A2A 协议服务器（FastAPI）
- Session 管理（Redis 存储）
- LLM Gateway（多提供商支持）
- RAG 系统（文档管理 + 检索）
- Memory 系统（长短期记忆）

现有架构使用 Nginx 作为简单反向代理，缺少：
- 用户认证体系
- API 网关级别的限流和鉴权
- 前端用户界面
- 实时通信能力

本设计将在现有架构上增加接入层和前端交互层。

## Goals / Non-Goals

**Goals:**
- 实现独立的用户认证服务，支持注册、登录、JWT 管理
- 部署 APISIX 网关，统一处理鉴权、限流、路由
- 构建 React 前端应用，提供会话管理、聊天、RAG 文件管理界面
- 实现 WebSocket 实时通信，推送 Agent 执行状态
- 保持与现有后端服务的兼容性

**Non-Goals:**
- 不修改现有 Agent 核心逻辑
- 不支持 OAuth2.0 第三方登录（后续迭代）
- 不实现多租户计费系统
- 不进行移动端适配

## Decisions

### Decision 1: 使用 APISIX 作为 API 网关

**选择**: APISIX

**原因**:
- 云原生设计，基于 etcd 动态配置
- 丰富的插件生态（jwt-auth, limit-req, proxy-cache）
- 原生支持 WebSocket 代理
- 相比 Kong 更轻量，配置更灵活
- 支持 Lua 自定义插件扩展

**替代方案考虑**:
| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Kong | 成熟稳定，企业级 | 较重，PostgreSQL 依赖 | 不选 |
| Traefik | Go 原生，配置简单 | 插件生态弱 | 不选 |
| Nginx + OpenResty | 已有基础 | 需要大量自定义开发 | 不选 |

### Decision 2: JWT 认证策略

**选择**: 双 Token 机制（Access Token + Refresh Token）

**设计**:
```
Access Token:  短期（15分钟），存储于内存
Refresh Token: 长期（7天），存储于 HttpOnly Cookie
```

**原因**:
- Access Token 短期过期减少泄露风险
- Refresh Token 支持静默续期，用户体验好
- HttpOnly Cookie 防止 XSS 攻击

**Token Payload**:
```json
{
  "sub": "<user_id>",
  "role": "user|admin",
  "exp": 1234567890,
  "iat": 1234567890,
  "jti": "<unique_token_id>"
}
```

### Decision 3: 前端技术栈

**选择**: React 18 + Vite + Zustand + React Query + TailwindCSS

**原因**:
- React 18: 生态成熟，团队熟悉
- Vite: 开发体验好，构建速度快
- Zustand: 轻量状态管理，比 Redux 简洁
- React Query: 服务端状态管理，自动缓存和重试
- TailwindCSS: 原子化 CSS，开发效率高

**前端架构**:
```
src/
├── api/          # API 封装层
├── hooks/        # 自定义 Hooks
├── stores/       # Zustand 状态
├── components/   # UI 组件
├── pages/        # 页面组件
└── lib/          # 工具函数
```

### Decision 4: WebSocket 通信协议

**选择**: 原生 WebSocket + 自定义消息协议

**消息格式**:
```json
{
  "type": "<event_type>",
  "sessionId": "<session_id>",
  "timestamp": 1234567890,
  "data": { ... }
}
```

**事件类型**:
| 事件 | 方向 | 描述 |
|------|------|------|
| `ping` | C→S | 心跳请求 |
| `pong` | S→C | 心跳响应 |
| `agent.thinking` | S→C | Agent 思考中 |
| `agent.tool_call` | S→C | 工具调用 |
| `agent.tool_result` | S→C | 工具结果 |
| `agent.response` | S→C | 流式响应 |
| `agent.error` | S→C | 错误通知 |
| `document.progress` | S→C | 文档处理进度 |

**原因**:
- 原生 WebSocket 无额外依赖
- 自定义协议灵活，满足 Agent 特定需求
- 不选 Socket.io：增加复杂度，且不需要其降级功能

### Decision 5: Session 与 User 关联

**选择**: Session 表添加 user_id 外键

**数据模型**:
```
users
├── id (UUID)
├── email
├── password_hash
├── created_at
└── updated_at

sessions (扩展现有模型)
├── session_id (UUID)
├── user_id (FK → users.id)  # 新增
├── state
├── created_at
└── ...
```

**Redis 键结构调整**:
```
session:{session_id}           → Session JSON
user:{user_id}:sessions        → Set of session_ids
```

### Decision 6: 限流策略分层

**设计**:
```
全局限流:
  - 连接数: 5000/总
  - 请求数: 1000 req/s/总

路由级限流:
  - /auth/*:   10 req/s/IP（防暴力破解）
  - /api/*:    30 req/s/用户
  - /rag/*:    20 req/s/用户
  - /ws:       100 连接/用户

用户级限流:
  - 聊天: 1000 次/小时
  - 上传: 5 次/分钟
```

## Risks / Trade-offs

### Risk 1: JWT 密钥泄露
- **风险**: 如果 JWT 密钥泄露，攻击者可以伪造任意用户身份
- **缓解**: 
  - 密钥通过环境变量注入，不存储在代码中
  - 支持密钥轮换机制
  - Access Token 短期过期（15分钟）

### Risk 2: WebSocket 连接管理复杂度
- **风险**: 大量 WebSocket 连接可能导致内存压力和连接管理复杂
- **缓解**:
  - 单用户连接数限制（100）
  - 心跳超时自动断开（60秒）
  - 支持优雅降级到轮询

### Risk 3: APISIX 学习曲线
- **风险**: 团队对 APISIX 不熟悉，可能导致配置错误
- **缓解**:
  - 使用声明式配置（YAML）
  - 充分的配置文档
  - 先在开发环境验证

### Risk 4: 前端构建复杂度
- **风险**: 新增前端项目增加了构建和部署复杂度
- **缓解**:
  - 前端独立打包为静态文件
  - 可通过 CDN 或 Nginx 托管
  - Docker 化部署

## Migration Plan

### Phase 1: 基础设施准备
1. 部署 APISIX + etcd
2. 配置基础路由（无鉴权）
3. 验证现有 API 通过网关访问正常

### Phase 2: 认证服务
1. 创建 users 表
2. 实现 Auth Service（注册、登录、刷新）
3. 配置 APISIX jwt-auth 插件
4. 验证鉴权流程

### Phase 3: 后端扩展
1. Session Manager 添加 user_id 支持
2. 实现 WebSocket Manager
3. 集成到 A2A Server

### Phase 4: 前端开发
1. 搭建 React 项目脚手架
2. 实现登录注册页面
3. 实现会话管理和聊天界面
4. 实现 RAG 文件管理界面

### Phase 5: 集成测试
1. 端到端测试全流程
2. 性能测试（限流、并发）
3. 安全测试（JWT、XSS、CSRF）

### Rollback Strategy
- APISIX 配置使用 etcd 版本控制，支持快速回滚
- 认证服务独立部署，可单独回滚
- 前端静态文件支持版本切换
