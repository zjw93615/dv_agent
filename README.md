# DV-Agent

> 🤖 通用AI Agent核心决策层 - 支持多Agent协作、LLM统一接入、ReAct决策循环、RAG知识库

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)

## 📑 目录

- [特性](#-特性)
- [系统架构](#-架构)
- [快速开始](#-快速开始)
  - [环境准备](#环境准备)
  - [方式一：Docker 一键部署（推荐）](#方式一docker-一键部署推荐)
  - [方式二：本地开发环境](#方式二本地开发环境)
- [数据库初始化](#-数据库初始化)
- [前端部署](#-前端部署)
- [配置说明](#-配置说明)
- [CLI 命令](#-cli-命令)
- [API 使用示例](#-代码示例)
- [项目结构](#-项目结构)
- [常见问题](#-常见问题)
- [贡献指南](#-贡献)

---

## ✨ 特性

- **🔄 ReAct 推理循环**: 基于 LangGraph 的 Think-Act-Observe 状态机
- **🌐 多Agent协调**: Orchestrator-Worker 架构，支持本地和远程Agent调度
- **🔌 LLM统一网关**: 支持 OpenAI、DeepSeek、Ollama，自动故障转移
- **📡 A2A协议**: 基于 JSON-RPC 2.0 的Agent间通信标准
- **💾 会话持久化**: Redis 存储，支持任务中断恢复
- **🛠️ MCP工具集成**: 支持外部工具服务器动态接入
- **🎯 意图识别**: 规则+LLM 双层意图分类与路由
- **📚 RAG 知识库**: 支持文档上传、向量检索、语义搜索
- **🖥️ Web 前端**: React + TypeScript 现代化界面
- **🔐 用户认证**: JWT 双 Token 机制，支持多用户
- **🐳 Docker 部署**: 完整的 docker-compose 一键部署方案

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     DV-Agent Core                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │
│  │  CLI/API    │──▶│ Orchestrator│──▶│  Worker Agents  │   │
│  └─────────────┘   └──────┬──────┘   └─────────────────┘   │
│                          │                                  │
│  ┌─────────────┐   ┌─────┴─────┐   ┌─────────────────┐     │
│  │ Intent      │◀──│  ReAct    │──▶│  Tool Registry  │     │
│  │ Router      │   │  Loop     │   │  + MCP Manager  │     │
│  └─────────────┘   └───────────┘   └─────────────────┘     │
│                          │                                  │
│  ┌─────────────┐   ┌─────┴─────┐   ┌─────────────────┐     │
│  │   Session   │◀──│    LLM    │──▶│  Remote Agents  │     │
│  │   Manager   │   │  Gateway  │   │  (via A2A)      │     │
│  └──────┬──────┘   └───────────┘   └─────────────────┘     │
│         │                                                   │
│  ┌──────┴──────┐                                            │
│  │    Redis    │                                            │
│  └─────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

## 📋 前置条件

### 必需软件

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Docker | 20.10+ | 容器运行环境 |
| Docker Compose | v2.0+ | 容器编排工具 |
| Git | 任意版本 | 代码版本控制 |

### 可选软件（本地开发）

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.10+ | 本地开发时需要 |
| Node.js | 18+ | 前端开发时需要 |
| Redis | 7.0+ | 本地开发可选 |

### LLM API Key（三选一）

- **OpenAI API Key** - 推荐，效果最好
- **DeepSeek API Key** - 国内可用，性价比高
- **本地 Ollama** - 完全离线，需要 GPU

---

## 🚀 快速开始

> **⚡ 最快上手方式（3 步）**
> ```bash
> # 1. 克隆并配置
> git clone https://github.com/your-org/dv-agent.git && cd dv-agent
> cp .env.production.example .env.production
> # 编辑 .env.production，设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY
> 
> # 2. 启动服务
> docker compose up -d
> 
> # 3. 验证运行
> curl http://localhost:8080/health
> ```
> 完成！后端已在 http://localhost:8080 运行。

### 环境准备

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/dv-agent.git
cd dv-agent

# 2. 检查 Docker 是否安装
docker --version
docker compose version
```

### 方式一：Docker 一键部署（推荐）

这是最简单的部署方式，适合快速体验和生产部署。

#### 步骤 1：配置环境变量

```bash
# Windows
copy .env.production.example .env.production

# Linux/Mac
cp .env.production.example .env.production
```

编辑 `.env.production` 文件，**必须设置** LLM API Key：

```bash
# 选择一个 LLM 提供商并配置 API Key

# 方案A：使用 OpenAI（推荐）
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-your-api-key-here

# 方案B：使用 DeepSeek（国内推荐）
LLM_PRIMARY_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-deepseek-api-key

# 方案C：使用本地 Ollama（离线使用）
LLM_PRIMARY_PROVIDER=ollama
```

#### 步骤 2：启动基础服务

```bash
# 启动核心服务（后端 + Redis + PostgreSQL）
docker compose up -d

# 查看启动状态
docker compose ps

# 查看日志（确认启动成功）
docker compose logs -f dv-agent
```

等待看到类似输出表示启动成功：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

#### 步骤 3：启动完整服务栈（可选）

```bash
# 启动带 API 网关和前端的完整服务
docker compose --profile gateway up -d

# 启动带监控的服务（Prometheus + Grafana）
docker compose --profile monitoring up -d

# 启动本地 Ollama（离线 LLM）
docker compose --profile ollama up -d

# 启动所有服务
docker compose --profile gateway --profile monitoring --profile ollama up -d
```

#### 步骤 4：验证部署

```bash
# 健康检查
curl http://localhost:8080/health

# 测试 API
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

#### 服务访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | http://localhost:8080 | A2A 协议接口 |
| 前端界面 | http://localhost:3080 | Web UI（需 gateway profile） |
| API 网关 | http://localhost:9080 | APISIX（需 gateway profile） |
| Redis | localhost:6379 | 会话存储 |
| PostgreSQL | localhost:5432 | 数据库 |
| Milvus | localhost:19530 | 向量数据库（需 memory profile） |
| Grafana | http://localhost:3000 | 监控面板（需 monitoring profile） |
| Prometheus | http://localhost:9090 | 指标收集（需 monitoring profile） |

---

### 方式二：本地开发环境

适合需要修改代码的开发者。

#### 步骤 1：安装 Python 依赖

```bash
# 克隆仓库
git clone https://github.com/dv-agent/dv-agent.git
cd dv-agent

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖（二选一）
pip install -e .                    # 使用 pyproject.toml（推荐）
pip install -r requirements.txt     # 或使用 requirements.txt

# 安装开发依赖（可选）
pip install -r requirements-dev.txt
```

#### 步骤 2：配置环境变量

```bash
# 复制环境变量模板
# Windows:
copy .env.example .env
# Linux/Mac:
cp .env.example .env
```

编辑 `.env` 文件，配置 LLM API Key：

```bash
# 必填：选择一个 LLM 提供商
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-your-api-key-here

# 或使用本地 Ollama（无需 API Key）
LLM_PRIMARY_PROVIDER=ollama
LLM_OLLAMA_BASE_URL=http://localhost:11434
LLM_OLLAMA_MODEL=llama3.2
```

#### 步骤 3：启动基础设施（Docker Compose）

本地开发需要 Redis 作为会话存储。使用以下 Docker Compose 命令启动依赖服务：

```bash
# ============ 开发环境 Docker Compose 命令速查 ============

# 【最小启动】仅 Redis（必需）
docker compose -f docker-compose.dev.yml up -d redis

# 【推荐启动】Redis + Ollama（本地 LLM）
docker compose -f docker-compose.dev.yml up -d redis ollama

# 【完整开发环境】Redis + Ollama + Redis Commander（可视化）
docker compose -f docker-compose.dev.yml up -d

# 查看服务状态
docker compose -f docker-compose.dev.yml ps

# 查看日志
docker compose -f docker-compose.dev.yml logs -f

# 停止所有服务
docker compose -f docker-compose.dev.yml down

# 停止并清除数据卷
docker compose -f docker-compose.dev.yml down -v
```

**各服务说明：**

| 服务 | 端口 | 说明 | 必需？ |
|------|------|------|--------|
| redis | 6379 | 会话存储 | ✅ 必需 |
| ollama | 11434 | 本地 LLM | 可选（使用云 API 时不需要） |
| redis-commander | 8081 | Redis 可视化工具 | 可选 |

**首次使用 Ollama 需要拉取模型：**

```bash
# 进入容器拉取模型
docker exec -it dv-agent-ollama ollama pull llama3.2

# 或本地安装的 Ollama
ollama pull llama3.2
```

#### 步骤 4：启动后端服务

有两种方式启动后端，根据需求选择：

**方式 A：热重载模式（开发推荐）⭐**

修改代码后自动重启，无需手动重启服务：

```bash
# 进入项目目录，确保虚拟环境已激活
cd dv-agent
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 使用 uvicorn 启动（支持热重载）
uvicorn dv_agent.server:app --host 0.0.0.0 --port 8080 --reload --reload-dir src

# 输出示例：
# INFO:     Will watch for changes in these directories: ['...\src']
# INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
# INFO:     Started reloader process [xxxxx] using WatchFiles
```

> 💡 **提示**：`--reload-dir src` 指定监控 `src` 目录，修改任何 `.py` 文件后服务会自动重启。

**方式 B：CLI 命令模式**

使用完整应用初始化流程（包含 Redis、LLM Gateway 等组件）：

```bash
# 使用 CLI 启动完整服务
python -m dv_agent.cli serve --host 0.0.0.0 --port 8080

# 或使用安装后的命令
dv-agent serve --port 8080

# 启用调试模式
dv-agent serve --port 8080 --debug
```

**两种方式的区别：**

| 对比项 | uvicorn 热重载 | CLI serve |
|--------|---------------|-----------|
| 代码修改后 | ✅ 自动重启 | ❌ 需手动重启 |
| 组件初始化 | 简化（仅 A2A Server） | 完整（Redis、LLM、Intent 等） |
| 适用场景 | 开发调试 | 生产/完整测试 |
| 启动速度 | 更快 | 较慢（初始化多） |

#### 步骤 5：验证服务

```bash
# 健康检查（Ping）
curl -X POST http://localhost:8080/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"agent.ping","id":"1"}'

# 期望返回：
# {"jsonrpc":"2.0","id":"1","result":{"pong":true,...},...}

# 获取 Agent 信息
curl -X POST http://localhost:8080/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"agent.info","id":"2"}'

# 访问 API 文档
# 浏览器打开: http://localhost:8080/docs
```

**PowerShell 用户：**

```powershell
# Ping 测试
Invoke-RestMethod -Uri "http://localhost:8080/a2a" -Method Post `
  -ContentType "application/json" `
  -Body '{"jsonrpc":"2.0","method":"agent.ping","id":"1"}'

# 获取 Agent 信息  
Invoke-RestMethod -Uri "http://localhost:8080/a2a" -Method Post `
  -ContentType "application/json" `
  -Body '{"jsonrpc":"2.0","method":"agent.info","id":"2"}'
```

#### 开发常用命令

```bash
# ============ 服务管理 ============
# 查看 Docker 服务状态
docker compose -f docker-compose.dev.yml ps

# 查看服务日志
docker compose -f docker-compose.dev.yml logs -f redis
docker compose -f docker-compose.dev.yml logs -f ollama

# 重启单个服务
docker compose -f docker-compose.dev.yml restart redis

# ============ 代码质量 ============
# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/ tests/

# 类型检查
mypy src/

# ============ CLI 工具 ============
# 交互式对话
dv-agent chat

# 单次提问
dv-agent ask "今天是什么日期？"

# 查看配置
dv-agent config

# 工具列表
dv-agent tools list
```

#### 常见开发问题

**Q: 端口 8080 被占用怎么办？**

```bash
# Windows - 查找占用进程
netstat -ano | findstr :8080
# 终止进程
taskkill /F /PID <进程ID>

# Linux/Mac
lsof -i :8080
kill -9 <PID>

# 或使用其他端口
uvicorn dv_agent.server:app --port 8081 --reload --reload-dir src
```

**Q: Redis 连接失败？**

```bash
# 检查 Redis 是否运行
docker compose -f docker-compose.dev.yml ps redis

# 查看 Redis 日志
docker compose -f docker-compose.dev.yml logs redis

# 重启 Redis
docker compose -f docker-compose.dev.yml restart redis
```

**Q: Ollama 模型下载失败？**

```bash
# 检查 Ollama 状态
docker compose -f docker-compose.dev.yml logs ollama

# 手动拉取模型（可能需要代理）
docker exec -it dv-agent-ollama ollama pull llama3.2

# 或使用国内镜像/更小的模型
docker exec -it dv-agent-ollama ollama pull qwen2:7b
```

---

## �️ 数据库初始化

### PostgreSQL 数据库

PostgreSQL 用于存储用户信息、长期记忆和 RAG 文档元数据。Docker 启动时会自动执行初始化脚本。

#### 自动初始化（推荐）

使用 Docker Compose 启动时，会自动执行 `scripts/init_postgres.sql`：

```bash
# 启动包含 PostgreSQL 的服务
docker compose up -d postgres

# 查看初始化日志
docker logs dv-agent-postgres
```

#### 手动初始化

如果需要手动初始化或重置数据库：

```bash
# 连接到 PostgreSQL 容器
docker exec -it dv-agent-postgres psql -U postgres -d dv_agent

# 或从主机连接（需要安装 psql）
psql -h localhost -U postgres -d dv_agent
```

执行初始化脚本：

```bash
# 核心表结构（用户记忆系统）
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < scripts/init_postgres.sql

# 用户认证表
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < scripts/init_users.sql

# RAG 文档表
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < scripts/init_rag_postgres.sql
```

#### 数据库迁移

当项目更新需要修改数据库结构时，需要运行迁移脚本：

**方式 1：使用 Python 脚本（推荐）**

```bash
# 进入项目目录，激活虚拟环境
cd dv-agent
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 运行迁移脚本（自动执行所有新迁移）
python scripts/run_migration.py
```

迁移脚本会自动：
- 连接数据库
- 查找 `migrations/` 目录下的所有 `.sql` 文件
- 按文件名顺序执行
- 跳过已存在的表/索引

**方式 2：手动执行 SQL**

```bash
# 在 Docker 中执行
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < migrations/003_add_collections_table.sql

# 或使用 psql 直接连接
psql -h localhost -U postgres -d dv_agent -f migrations/003_add_collections_table.sql
```

**迁移文件列表：**

| 文件 | 说明 |
|------|------|
| `003_add_collections_table.sql` | RAG 文档集合表 |
| `scripts/migrate_rag_documents.py` | RAG 文档和文档块表 |

> ⚠️ **注意**：每次 `git pull` 更新代码后，检查 `migrations/` 目录是否有新文件，如有则需要运行迁移。

#### RAG 文档表初始化

RAG 功能需要额外的文档存储表。首次使用 RAG 功能前，需要运行以下迁移：

**方式 1：使用 Python 脚本（推荐）**

```bash
# 进入项目目录，激活虚拟环境
cd dv-agent
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 运行 RAG 文档表迁移脚本
python scripts/migrate_rag_documents.py
```

脚本会自动：
- 创建 `documents` 表（存储文档元数据）
- 创建 `document_chunks` 表（存储文档分块）
- 创建必要的索引和触发器
- 跳过已存在的表

**方式 2：使用 SQL 脚本**

```bash
# 在 Docker 中执行
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < scripts/migrate_rag_documents.sql

# 或使用 psql 直接连接
psql -h localhost -U postgres -d dv_agent -f scripts/migrate_rag_documents.sql
```

**RAG 相关表结构：**

| 表名 | 说明 |
|------|------|
| `collections` | 文档集合（用于组织文档） |
| `documents` | 文档元数据（文件名、大小、状态等） |
| `document_chunks` | 文档分块（用于向量检索） |

> 💡 **提示**：如果前端创建集合后刷新页面看不到数据，可能是因为 `documents` 表未创建。运行上述迁移脚本即可修复。

### Milvus 向量数据库

Milvus 用于存储和检索向量嵌入。

```bash
# 启动 Milvus 服务（包含 etcd 和 minio）
docker compose --profile memory up -d

# 查看 Milvus 状态
docker logs dv-agent-milvus

# 访问 Milvus Web UI (Attu)
# 使用 RAG compose 文件时：http://localhost:8000
```

#### 初始化 Milvus Collection

```bash
# 进入项目目录
cd dv-agent

# 激活虚拟环境
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 运行初始化脚本
python scripts/init_milvus.py
python scripts/init_rag_milvus.py
```

### MinIO 对象存储

MinIO 用于存储上传的文档文件。

```bash
# 启动 MinIO
docker compose -f docker-compose.rag.yml up -d minio

# 访问 MinIO Console
# 地址: http://localhost:9001
# 用户名: minioadmin
# 密码: minioadmin123

# 初始化 Bucket
python scripts/init_minio.py
```

---

## 📚 RAG 知识库服务

RAG（检索增强生成）服务提供文档管理和语义搜索功能。

### 启动 RAG 服务栈

```bash
# 启动所有 RAG 相关服务
docker compose -f docker-compose.rag.yml up -d

# 查看服务状态
docker compose -f docker-compose.rag.yml ps
```

服务包含：
- **MinIO**: 文档存储（端口 9000/9001）
- **PostgreSQL**: 文档元数据（端口 5432）
- **Milvus**: 向量检索（端口 19530）
- **Redis**: 缓存（端口 6379）
- **Attu**: Milvus Web UI（端口 8000）

### 配置 RAG 环境变量

在 `.env` 文件中添加：

```bash
# RAG 开关
RAG_ENABLED=true

# Embedding 模型
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_DEVICE=cuda  # 或 cpu

# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# PostgreSQL 配置
RAG_POSTGRES_HOST=localhost
RAG_POSTGRES_PORT=5432
RAG_POSTGRES_DATABASE=dv_agent
RAG_POSTGRES_USER=postgres
RAG_POSTGRES_PASSWORD=postgres123
```

### 停止 RAG 服务

```bash
docker compose -f docker-compose.rag.yml down

# 如需删除数据卷
docker compose -f docker-compose.rag.yml down -v
```

---

## 🖥️ 前端部署

### 使用 Docker 部署（推荐）

前端已集成在 docker-compose 的 gateway profile 中：

```bash
# 启动前端和 API 网关
docker compose --profile gateway up -d

# 访问前端
# http://localhost:3080
```

### 本地开发前端

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 复制环境变量
copy .env.example .env.local  # Windows
cp .env.example .env.local    # Linux/Mac
```

编辑 `.env.local`，根据后端部署方式选择：

```bash
# 方式1: 使用 API 网关 (启用了 gateway profile)
VITE_API_URL=http://localhost:9080
VITE_WS_URL=ws://localhost:9080/ws

# 方式2: 直连后端 (仅基础服务，无 gateway)
VITE_API_URL=http://localhost:8080
VITE_WS_URL=ws://localhost:8080/ws
```

```bash
# 启动开发服务器
npm run dev

# 访问 http://localhost:5173
```

### 生产构建

```bash
# 构建前端
cd frontend
npm run build

# 构建产物在 dist/ 目录

# 构建 Docker 镜像
docker build -t dv-agent-frontend .
```

---

## �📖 CLI 命令

```bash
# 查看帮助
dv-agent --help

# 启动服务器
dv-agent serve [--host HOST] [--port PORT] [--debug]

# 交互式对话
dv-agent chat [--session SESSION_ID]

# 单次提问
dv-agent ask "今天是什么日期？"
dv-agent ask "计算 1+1" --json

# 查看配置
dv-agent config

# 健康检查
dv-agent health

# 工具管理
dv-agent tools list

# 会话管理
dv-agent session info <session_id>
dv-agent session delete <session_id>
```

## 🔧 配置说明

### 核心环境变量

#### LLM 配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_PRIMARY_PROVIDER` | 主 LLM 提供商 | `openai` |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - |
| `LLM_OLLAMA_BASE_URL` | Ollama 服务地址 | `http://localhost:11434` |
| `LLM_OLLAMA_MODEL` | Ollama 模型名称 | `llama3.2` |
| `LLM_DEFAULT_TEMPERATURE` | 生成温度 | `0.7` |
| `LLM_DEFAULT_MAX_TOKENS` | 最大 Token 数 | `4096` |

#### 服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `A2A_HOST` | A2A 服务主机 | `0.0.0.0` |
| `A2A_PORT` | A2A 服务端口 | `8080` |
| `REDIS_HOST` | Redis 主机 | `localhost` |
| `REDIS_PORT` | Redis 端口 | `6379` |

#### 数据库配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `POSTGRES_DB` | 数据库名 | `dv_agent` |
| `POSTGRES_USER` | 用户名 | `postgres` |
| `POSTGRES_PASSWORD` | 密码 | `postgres` |
| `MILVUS_HOST` | Milvus 主机 | `localhost` |
| `MILVUS_PORT` | Milvus 端口 | `19530` |

#### RAG 配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `RAG_ENABLED` | 启用 RAG | `true` |
| `RAG_EMBEDDING_MODEL` | Embedding 模型 | `BAAI/bge-m3` |
| `RAG_EMBEDDING_DEVICE` | 计算设备 | `cuda` |
| `MINIO_ENDPOINT` | MinIO 地址 | `localhost:9000` |
| `MINIO_ACCESS_KEY` | MinIO 访问密钥 | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO 密钥 | `minioadmin123` |

详细配置见 [.env.example](.env.example)

### 使用 Ollama（离线部署）

如果你想使用本地 LLM 而不是云 API：

```bash
# 方式一：使用 Docker（推荐）
docker compose --profile ollama up -d

# 拉取模型
docker exec -it dv-agent-ollama ollama pull llama3.2

# 方式二：本地安装 Ollama
# 1. 下载安装: https://ollama.ai/download
# 2. 拉取模型
ollama pull llama3.2
```

配置 `.env`：

```bash
LLM_PRIMARY_PROVIDER=ollama
LLM_OLLAMA_BASE_URL=http://localhost:11434  # 本地
# 或 Docker 环境
LLM_OLLAMA_BASE_URL=http://ollama:11434
LLM_OLLAMA_MODEL=llama3.2
```

## � 代码示例

### 基本使用

```python
import asyncio
from dv_agent import create_application

async def main():
    async with create_application() as app:
        # 发送消息
        result = await app.process_message("帮我计算 123 + 456")
        print(f"回复: {result['response']}")
        print(f"会话ID: {result['session_id']}")
        
        # 继续对话（使用同一会话）
        result = await app.process_message(
            "再乘以 2",
            session_id=result["session_id"]
        )
        print(f"回复: {result['response']}")

asyncio.run(main())
```

### 创建自定义Agent

```python
from dv_agent import BaseAgent
from dv_agent.agents.react_loop import ReActLoop

class MyCustomAgent(BaseAgent):
    def __init__(self, llm_gateway, tool_registry):
        super().__init__(
            agent_id="my-custom-agent",
            description="我的自定义Agent"
        )
        self.react = ReActLoop(llm_gateway, tool_registry)
    
    async def process(self, input_text, session, context=None):
        result = await self.react.run(input_text, context)
        return AgentResult(
            agent_id=self.agent_id,
            response=result.final_answer
        )
```

### 注册自定义工具

```python
from dv_agent import ToolRegistry, Tool

# 定义工具
my_tool = Tool(
    name="my_tool",
    description="我的自定义工具",
    parameters={"query": "搜索关键词"},
    handler=my_handler_function
)

# 注册到工具库
registry = ToolRegistry()
registry.register(my_tool)
```

### A2A 客户端调用

```python
from dv_agent import A2AClient

async def call_remote_agent():
    client = A2AClient(base_url="http://remote-agent:8080")
    
    response = await client.send_task(
        method="process",
        params={"message": "Hello from remote!"}
    )
    
    print(response.result)
```

## 📦 项目结构

```
dv-agent/
├── src/dv_agent/              # 后端源码
│   ├── __init__.py            # 主入口和导出
│   ├── app.py                 # 应用工厂
│   ├── main.py                # 主模块
│   ├── cli.py                 # CLI 接口
│   ├── config/                # 配置管理
│   ├── llm_gateway/           # LLM 统一网关
│   ├── agents/                # Agent 核心
│   ├── intent/                # 意图识别
│   ├── session/               # 会话管理
│   ├── memory/                # 记忆系统
│   ├── rag/                   # RAG 知识库
│   ├── auth/                  # 用户认证
│   ├── websocket/             # WebSocket 实时通信
│   ├── tools/                 # 工具系统
│   └── a2a/                   # A2A 协议
│
├── frontend/                  # 前端项目
│   ├── src/                   # React 源码
│   │   ├── api/               # API 客户端
│   │   ├── components/        # React 组件
│   │   ├── pages/             # 页面组件
│   │   ├── stores/            # Zustand 状态管理
│   │   └── hooks/             # 自定义 Hooks
│   ├── Dockerfile             # 前端镜像
│   └── package.json           # NPM 配置
│
├── scripts/                   # 脚本工具
│   ├── dev.bat                # Windows 开发脚本
│   ├── deploy.bat             # Windows 部署脚本
│   ├── init_postgres.sql      # PostgreSQL 初始化
│   ├── init_users.sql         # 用户表初始化
│   ├── init_rag_postgres.sql  # RAG 表初始化
│   ├── init_milvus.py         # Milvus 初始化
│   └── init_minio.py          # MinIO 初始化
│
├── deploy/                    # 部署配置
│   ├── apisix/                # APISIX 网关配置
│   ├── nginx.conf             # Nginx 配置
│   ├── redis.conf             # Redis 配置
│   └── prometheus.yml         # Prometheus 配置
│
├── config/                    # 应用配置文件
│   ├── agents.yaml            # Agent 配置
│   ├── llm.yaml               # LLM 配置
│   ├── mcp.yaml               # MCP 工具配置
│   ├── rag.yaml               # RAG 配置
│   └── memory.yaml            # 记忆配置
│
├── tests/                     # 测试文件
│
├── docker-compose.yml         # 生产部署
├── docker-compose.dev.yml     # 开发环境
├── docker-compose.rag.yml     # RAG 服务
├── Dockerfile                 # 后端镜像
├── Makefile                   # 构建命令
├── pyproject.toml             # Python 项目配置
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
└── README.md                  # 本文档
```

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_llm_gateway.py -v

# 测试覆盖率
pytest --cov=dv_agent --cov-report=html

# 打开覆盖率报告
# 浏览器打开 htmlcov/index.html
```

## ❓ 常见问题

### Q: Docker 容器启动失败怎么办？

A: 检查以下几点：
```bash
# 1. 查看容器日志
docker compose logs dv-agent

# 2. 检查端口是否被占用
netstat -an | findstr "8080"  # Windows
lsof -i :8080                  # Linux/Mac

# 3. 检查 Docker 资源
docker system df
docker system prune  # 清理未使用资源

# 4. 重新构建镜像
docker compose build --no-cache
docker compose up -d
```

### Q: 没有 Redis 可以运行吗？

A: 可以，但会话持久化功能将不可用。程序会使用内存存储，重启后会话数据会丢失。

### Q: 如何使用国内 LLM？

A: 配置 DeepSeek（推荐）：
```bash
DEEPSEEK_API_KEY=your-api-key
LLM_PRIMARY_PROVIDER=deepseek
```

### Q: 如何完全离线运行？

A: 使用 Ollama 本地部署：
```bash
# 使用 Docker 启动 Ollama
docker compose --profile ollama up -d

# 拉取模型
docker exec -it dv-agent-ollama ollama pull llama3.2

# 配置环境变量
LLM_PRIMARY_PROVIDER=ollama
LLM_OLLAMA_BASE_URL=http://ollama:11434
LLM_OLLAMA_MODEL=llama3.2
```

### Q: 报错 "No module named 'dv_agent'"？

A: 确保以开发模式安装了项目：
```bash
pip install -e .
```

### Q: PostgreSQL 连接失败？

A: 检查数据库状态：
```bash
# 查看容器状态
docker compose ps postgres

# 查看日志
docker compose logs postgres

# 手动测试连接
docker exec -it dv-agent-postgres psql -U postgres -d dv_agent -c "SELECT 1"
```

### Q: Milvus 启动很慢或失败？

A: Milvus 需要较多资源，确保：
```bash
# 1. 检查 Docker 内存限制（建议 4GB+）
# 2. 等待 etcd 和 minio 先启动
docker compose --profile memory up -d milvus-etcd milvus-minio
# 等待 30 秒
docker compose --profile memory up -d milvus

# 3. 查看日志
docker compose logs milvus
```

### Q: 前端无法连接后端？

A: 检查 API 网关配置：
```bash
# 1. 确保启动了 gateway profile
docker compose --profile gateway up -d

# 2. 检查 APISIX 状态
curl http://localhost:9080/apisix/status

# 3. 检查前端环境变量
# frontend/.env.local
VITE_API_URL=http://localhost:9080
```

### Q: 如何重置所有数据？

A: 删除 Docker 卷：
```bash
# 停止所有服务
docker compose down

# 删除数据卷（警告：会丢失所有数据！）
docker volume rm dv-agent_postgres_data dv-agent_redis_data dv-agent_milvus_data

# 或删除所有相关卷
docker compose down -v

# 重新启动
docker compose up -d
```

## 📝 开发计划

- [x] 核心 ReAct 循环
- [x] LLM Gateway 多提供商支持
- [x] A2A 协议实现
- [x] Redis 会话持久化
- [x] 意图识别与路由
- [x] CLI 工具
- [x] Docker 部署支持
- [x] RAG 知识库系统
- [x] Web 前端界面
- [x] 用户认证系统
- [ ] Embedding 意图识别
- [ ] Web 搜索技能
- [ ] 更多 Worker Agent
- [ ] 可视化 Dashboard

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

## 📈 扩展阅读

### 技术文档

- [LangGraph 文档](https://langgraph.readthedocs.io/) - 状态机框架
- [FastAPI 官方网站](https://fastapi.tiangolo.com/) - Python Web 框架
- [React 官方文档](https://react.dev/) - 前端框架
- [TailwindCSS 文档](https://tailwindcss.com/) - CSS 框架

### 基础设施

- [Docker Compose 文档](https://docs.docker.com/compose/) - 容器编排
- [Redis 官方网站](https://redis.io/) - 内存数据库
- [PostgreSQL 文档](https://www.postgresql.org/docs/) - 关系数据库
- [Milvus 文档](https://milvus.io/docs) - 向量数据库
- [APISIX 文档](https://apisix.apache.org/docs/) - API 网关

### LLM 服务

- [OpenAI API 文档](https://platform.openai.com/docs/) - OpenAI 接口
- [DeepSeek API](https://platform.deepseek.com/) - DeepSeek 接口
- [Ollama 官方网站](https://ollama.ai/) - 本地 LLM 部署

---

## 💬 获取帮助

- **GitHub Issues**: 提交 Bug 报告或功能请求
- **Discussions**: 参与社区讨论
- **Wiki**: 查看详细文档

---

> 📌 **提示**: 如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！
