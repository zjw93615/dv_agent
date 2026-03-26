# DV-Agent Frontend

React + TypeScript 前端应用，提供智能对话界面和文档管理功能。

## 技术栈

- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite 5
- **Styling**: TailwindCSS 4
- **State Management**: Zustand
- **Data Fetching**: TanStack Query (React Query) v5
- **Routing**: React Router v7
- **UI Icons**: Lucide React

## 快速开始

### 环境要求

- Node.js >= 18.0.0
- npm >= 9.0.0

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
# 复制环境变量配置
cp .env.example .env.local

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173

### 生产构建

```bash
npm run build
```

构建产物在 `dist/` 目录。

### 测试

```bash
# 运行测试
npm run test

# 带 UI 的测试
npm run test:ui

# 生成覆盖率报告
npm run test:coverage
```

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 客户端
│   │   ├── session.api.ts
│   │   ├── message.api.ts
│   │   └── rag.api.ts
│   ├── components/       # React 组件
│   │   ├── agent/        # Agent 执行面板
│   │   ├── chat/         # 聊天组件
│   │   ├── common/       # 通用组件
│   │   ├── layout/       # 布局组件
│   │   ├── rag/          # RAG 文档管理
│   │   └── session/      # 会话管理
│   ├── hooks/            # 自定义 Hooks
│   ├── lib/              # 工具库
│   │   ├── apiClient.ts  # Axios 客户端（JWT 刷新）
│   │   └── websocket.ts  # WebSocket 管理
│   ├── pages/            # 页面组件
│   ├── stores/           # Zustand 状态管理
│   ├── test/             # 测试文件
│   ├── App.tsx           # 应用入口
│   └── main.tsx          # React 挂载
├── public/               # 静态资源
├── Dockerfile            # 生产镜像
├── nginx.conf            # Nginx 配置
└── tailwind.config.js    # TailwindCSS 配置
```

## 功能特性

### 🔐 认证系统
- 用户注册/登录
- JWT 双 Token 机制（Access + Refresh）
- 自动 Token 刷新
- 受保护路由

### 💬 智能对话
- 多会话管理
- 实时消息流
- Markdown 渲染（支持 GFM）
- 代码高亮
- Agent 思考过程可视化
- 工具调用展示

### 📁 文档管理 (RAG)
- 知识库集合管理
- 文档上传（拖拽支持）
- 上传进度显示
- 文档列表与删除
- 语义搜索

### 🔗 WebSocket
- 实时消息推送
- 心跳保活
- 自动重连（指数退避）
- 会话级订阅

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_URL` | API 网关地址 | `http://localhost:9080` |
| `VITE_WS_URL` | WebSocket 地址 | `ws://localhost:9080/ws` |
| `VITE_APP_ENV` | 运行环境 | `development` |

## Docker 部署

```bash
# 构建镜像
docker build -t dv-agent-frontend .

# 运行容器
docker run -p 3080:80 dv-agent-frontend
```

## 与网关集成

前端通过 APISIX 网关访问后端服务：

- 所有 `/api/*` 请求代理到后端
- `/auth/*` 认证路由
- `/ws` WebSocket 连接

## 开发说明

### 添加新页面

1. 在 `src/pages/` 创建页面组件
2. 在 `src/App.tsx` 添加路由
3. 在 `MainLayout.tsx` 添加导航（如需要）

### 添加新 API

1. 在 `src/api/` 创建 API 模块
2. 使用 `apiClient` 发送请求
3. 可选：创建对应的 Zustand store

### 添加新组件

1. 在 `src/components/` 对应目录创建
2. 使用 TailwindCSS 编写样式
3. 编写测试文件

## License

MIT