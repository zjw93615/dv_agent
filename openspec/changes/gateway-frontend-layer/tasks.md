## 1. 基础设施准备

- [x] 1.1 创建 APISIX + etcd Docker Compose 配置文件 (`deploy/docker-compose.apisix.yaml`)
- [x] 1.2 创建 APISIX 核心配置文件 (`deploy/apisix/config.yaml`)
- [x] 1.3 创建 APISIX 路由声明文件 (`deploy/apisix/apisix.yaml`)
- [x] 1.4 更新主 docker-compose.yml 集成 APISIX 服务
- [x] 1.5 创建 PostgreSQL 用户表初始化脚本 (`scripts/init_users.sql`)

## 2. 用户认证服务 (Auth Service)

- [x] 2.1 创建 auth 模块目录结构 (`src/dv_agent/auth/`)
- [x] 2.2 实现用户数据模型 (`auth/models.py`)
- [x] 2.3 实现密码哈希工具 (`auth/security.py`)
- [x] 2.4 实现 JWT 签发与验证 (`auth/jwt.py`)
- [x] 2.5 实现用户存储层 (`auth/repository.py`)
- [x] 2.6 实现注册端点 (`POST /auth/register`)
- [x] 2.7 实现登录端点 (`POST /auth/login`)
- [x] 2.8 实现 Token 刷新端点 (`POST /auth/refresh`)
- [x] 2.9 实现登出端点 (`POST /auth/logout`)
- [x] 2.10 实现获取当前用户端点 (`GET /auth/me`)
- [x] 2.11 创建 Auth API Router 并集成到 FastAPI app

## 3. APISIX 网关配置

- [x] 3.1 配置 JWT 验证插件 (jwt-auth)
- [x] 3.2 配置认证路由 (`/auth/*` - 公开访问)
- [x] 3.3 配置业务 API 路由 (`/api/v1/*` - JWT 保护)
- [x] 3.4 配置 RAG API 路由 (`/api/rag/*` - JWT 保护)
- [x] 3.5 配置 WebSocket 路由 (`/ws` - JWT 保护)
- [x] 3.6 配置限流策略 (limit-req, limit-conn)
- [x] 3.7 配置 CORS 插件
- [x] 3.8 配置响应缓存 (proxy-cache)
- [x] 3.9 配置健康检查和负载均衡

## 4. Session 管理扩展

- [x] 4.1 更新 Session 模型添加 user_id 字段 (`session/models.py`)
- [x] 4.2 更新 SessionManager 支持用户级别操作 (`session/manager.py`)
- [x] 4.3 实现用户会话索引 (Redis Set: `user:{user_id}:sessions`)
- [x] 4.4 实现会话归属验证中间件
- [x] 4.5 更新 Session API 端点添加用户隔离
- [x] 4.6 实现列出用户会话端点 (`GET /api/v1/sessions`)

## 5. WebSocket 实时通信

- [x] 5.1 创建 websocket 模块目录结构 (`src/dv_agent/websocket/`)
- [x] 5.2 实现 WebSocket 连接管理器 (`websocket/manager.py`)
- [x] 5.3 实现连接认证验证 (从 query param 获取 token)
- [x] 5.4 实现心跳机制 (ping/pong)
- [x] 5.5 实现连接数限制 (单用户最多 100 连接)
- [x] 5.6 定义 WebSocket 消息协议格式
- [x] 5.7 实现 Agent 事件订阅机制
- [x] 5.8 集成 WebSocket 到 A2A Server
- [x] 5.9 实现 Agent 执行状态推送 (thinking, tool_call, tool_result, response)
- [x] 5.10 实现文档处理进度推送 (document.progress, document.completed)

## 6. 前端项目脚手架

- [x] 6.1 使用 Vite 创建 React + TypeScript 项目 (`frontend/`)
- [x] 6.2 配置 TailwindCSS
- [x] 6.3 安装和配置 Zustand 状态管理
- [x] 6.4 安装和配置 React Query
- [x] 6.5 配置 React Router v6
- [x] 6.6 创建项目目录结构 (api/, hooks/, stores/, components/, pages/, lib/)
- [x] 6.7 配置 API 客户端 (Axios 拦截器)
- [x] 6.8 配置环境变量 (.env)

## 7. 前端认证模块

- [x] 7.1 实现 Auth API 封装 (`api/auth.api.ts`)
- [x] 7.2 实现 Auth Store (`stores/authStore.ts`)
- [x] 7.3 实现登录页面 (`pages/LoginPage.tsx`)
- [x] 7.4 实现注册页面 (`pages/RegisterPage.tsx`)
- [x] 7.5 实现 Token 自动刷新逻辑
- [x] 7.6 实现路由守卫 (ProtectedRoute)
- [x] 7.7 实现登出功能

## 8. 前端会话管理模块

- [x] 8.1 实现 Session API 封装 (`api/session.api.ts`)
- [x] 8.2 实现 Session Store (`stores/sessionStore.ts`)
- [x] 8.3 实现会话列表组件 (`components/session/SessionList.tsx`)
- [x] 8.4 实现会话项组件 (`components/session/SessionItem.tsx`)
- [x] 8.5 实现新建会话按钮
- [x] 8.6 实现删除会话功能

## 9. 前端聊天模块

- [x] 9.1 实现 Chat API 封装 (`api/chat.api.ts`)
- [x] 9.2 实现 Chat Store (`stores/chatStore.ts`)
- [x] 9.3 实现聊天页面布局 (`pages/ChatPage.tsx`)
- [x] 9.4 实现消息列表组件 (`components/chat/MessageList.tsx`)
- [x] 9.5 实现消息气泡组件 (`components/chat/MessageBubble.tsx`)
- [x] 9.6 实现输入区组件 (`components/chat/InputArea.tsx`)
- [x] 9.7 实现 Markdown 渲染 (react-markdown)
- [x] 9.8 实现代码块语法高亮 (highlight.js)
- [x] 9.9 实现流式响应渲染 (`components/chat/StreamingMessage.tsx`)

## 10. 前端 WebSocket 集成

- [x] 10.1 实现 WebSocket 管理器 (`lib/websocket.ts`)
- [x] 10.2 实现 useWebSocket Hook (`hooks/useWebSocket.ts`)
- [x] 10.3 实现 Agent 状态 Store (`stores/agentStore.ts`)
- [ ] 10.4 实现 Agent 执行状态面板 (`components/agent/AgentExecutionPanel.tsx`)
- [x] 10.5 实现思考状态指示器 (`components/agent/ThinkingIndicator.tsx`)
- [x] 10.6 实现工具调用卡片 (`components/agent/ToolCallCard.tsx`)
- [x] 10.7 实现断线重连逻辑
- [x] 10.8 实现心跳发送

## 11. 前端 RAG 文件管理模块

- [x] 11.1 实现 RAG API 封装 (`api/rag.api.ts`)
- [x] 11.2 实现 RAG Store (`stores/ragStore.ts`)
- [ ] 11.3 实现文档管理页面 (`pages/DocumentsPage.tsx`)
- [ ] 11.4 实现文件上传组件 (`components/rag/DocumentUploader.tsx`)
- [ ] 11.5 实现拖拽上传区域
- [ ] 11.6 实现上传进度条
- [ ] 11.7 实现文档列表组件 (`components/rag/DocumentList.tsx`)
- [ ] 11.8 实现文档项组件 (`components/rag/DocumentItem.tsx`)
- [ ] 11.9 实现处理状态展示 (`components/rag/ProcessingStatus.tsx`)
- [ ] 11.10 实现集合管理侧边栏 (`components/rag/CollectionManager.tsx`)
- [ ] 11.11 实现文档删除功能
- [ ] 11.12 实现搜索面板 (`components/rag/SearchPanel.tsx`)

## 12. 集成与测试

- [ ] 12.1 编写 Auth Service 单元测试
- [ ] 12.2 编写 WebSocket Manager 单元测试
- [ ] 12.3 编写 APISIX 路由配置集成测试
- [ ] 12.4 编写前端组件测试 (Vitest + Testing Library)
- [ ] 12.5 创建端到端测试脚本 (登录→聊天→上传文档)
- [ ] 12.6 性能测试：WebSocket 连接数
- [ ] 12.7 性能测试：限流策略验证

## 13. 部署与文档

- [x] 13.1 创建前端 Dockerfile
- [ ] 13.2 更新 docker-compose.yml 添加前端服务
- [ ] 13.3 配置 APISIX 静态文件服务（前端托管）
- [x] 13.4 创建环境变量文档 (.env.example)
- [ ] 13.5 更新 README 添加新功能说明
- [ ] 13.6 创建 API 文档 (OpenAPI spec)
