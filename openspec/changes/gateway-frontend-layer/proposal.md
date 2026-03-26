## Why

当前 DV-Agent 系统缺少完整的用户接入层，无法支持多用户场景下的身份认证、会话管理和实时交互。需要构建 API 网关层（APISIX）和前端交互层（React），实现用户登录、Session 管理、JWT 鉴权、限流策略，以及实时的 Agent 执行状态反馈和 RAG 文件管理。

## What Changes

### 新增组件
- **APISIX 网关层**：JWT 鉴权、多级限流、路由配置、WebSocket 支持
- **Auth Service**：独立的用户认证服务，JWT 签发与验证
- **React 前端应用**：完整的用户交互界面，包含聊天、会话管理、RAG 文件管理
- **WebSocket 实时通信**：Agent 执行状态推送、文档处理进度通知

### 后端扩展
- 扩展现有 Session Manager 支持用户级别隔离
- 添加 WebSocket Manager 处理实时连接
- 扩展 RAG API 支持网关鉴权和租户隔离

### 部署配置
- 新增 APISIX + etcd Docker 配置
- 更新 docker-compose 集成新组件

## Capabilities

### New Capabilities
- `api-gateway`: APISIX 网关配置，包含路由、JWT 鉴权、限流、缓存策略
- `user-auth`: 用户认证服务，包含注册、登录、JWT 管理、密码策略
- `websocket-realtime`: WebSocket 实时通信层，Agent 状态推送、心跳保活、断线重连
- `frontend-app`: React 前端应用架构，状态管理、组件设计、路由配置
- `rag-file-management`: 前端 RAG 文件上传和管理界面

### Modified Capabilities
- `session-management`: 扩展支持用户级别会话隔离和网关集成

## Impact

### 代码影响
- `src/dv_agent/session/manager.py`: 添加用户隔离逻辑
- `src/dv_agent/a2a/server.py`: 集成 WebSocket Manager
- `src/dv_agent/rag/api.py`: 添加租户 ID 验证
- 新增 `src/dv_agent/auth/` 目录（认证服务）
- 新增 `src/dv_agent/websocket/` 目录（WebSocket 管理）
- 新增 `frontend/` 目录（React 前端）

### API 影响
- 新增 `/auth/*` 认证端点
- 新增 `/ws` WebSocket 端点
- 现有 `/api/*` 和 `/rag/*` 端点需通过 JWT 鉴权

### 依赖影响
- 后端新增：`python-jose[cryptography]`, `passlib[bcrypt]`
- 前端新增：`react`, `vite`, `zustand`, `@tanstack/react-query`, `tailwindcss`
- 基础设施：APISIX, etcd

### 部署影响
- 需要配置 JWT 密钥（环境变量）
- 需要 PostgreSQL 用户表
- 需要更新 Nginx/APISIX 配置
