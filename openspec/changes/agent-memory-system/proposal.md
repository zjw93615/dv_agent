## Why

当前 dv-agent 仅支持基于 Redis 的 Session 级短期对话历史存储，缺乏长期记忆能力。在企业知识库助手场景中，Agent 无法记住用户的偏好、历史交互知识，也无法有效检索和利用企业共享知识库。这导致每次对话都是"零起点"，无法提供个性化、连贯的服务体验。

## What Changes

### 新增能力
- **短期记忆增强**：基于 Redis 的滑动窗口机制，支持 Token 压缩和对话摘要
- **长期记忆存储**：PostgreSQL（结构化元数据） + Milvus（向量检索）的联动存储架构
- **记忆检索优化**：多路召回 + Cross-Encoder 重排序的组合检索策略
- **记忆生命周期管理**：自动提取、权重更新、智能遗忘机制
- **共享知识库支持**：企业级知识的向量存储与多层级权限访问

### 新增组件
- `MemoryManager`：独立的记忆管理器，与现有 `SessionManager` 解耦
- `MemoryRetriever`：统一记忆检索接口，支持短期/长期/共享知识库的融合检索
- `MemoryExtractor`：对话结束后的知识提取器
- `MemoryLifecycleWorker`：后台任务处理记忆权重更新和遗忘

### 新增依赖
- PostgreSQL >= 14.0（长期记忆结构化存储）
- Milvus >= 2.3.0（向量存储与检索）
- sentence-transformers（Embedding 生成）
- cross-encoder（精排模型）

## Capabilities

### New Capabilities
- `short-term-memory`: 短期记忆管理，包括滑动窗口、Token压缩、会话摘要
- `long-term-memory`: 长期记忆存储，PostgreSQL + Milvus 联动，支持私有记忆与共享知识
- `memory-retrieval`: 统一记忆检索，多路召回 + Cross-Encoder 重排序
- `memory-lifecycle`: 记忆生命周期管理，提取/更新/遗忘机制

### Modified Capabilities
- `session-management`: 扩展 Session 模型以关联短期记忆，新增 summary 字段和滑动窗口配置

## Impact

### 代码影响
- `src/dv_agent/memory/` - 新增记忆系统模块
- `src/dv_agent/session/manager.py` - 扩展以支持短期记忆集成
- `src/dv_agent/agents/base_agent.py` - 集成记忆检索到 Agent 上下文

### API 影响
- 新增 `/api/v1/memory/*` 记忆管理 API
- 扩展 `/api/v1/session/*` 以包含记忆摘要信息

### 依赖影响
- 新增 PostgreSQL 服务依赖
- 新增 Milvus 服务依赖
- `requirements.txt` 新增 `pymilvus`, `psycopg`, `sentence-transformers` 等包

### 部署影响
- `docker-compose.yml` 新增 PostgreSQL、Milvus 服务配置
- 需要数据库初始化脚本
- 新增配置文件 `config/memory.yaml`
