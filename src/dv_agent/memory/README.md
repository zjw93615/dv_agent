# Memory System 记忆系统

dv-agent 的分层记忆系统，实现类似人类的短期/长期记忆管理。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      MemoryManager                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  ShortTermMemory │  │  LongTermMemory │  │  Retrieval  │  │
│  │    (Redis)       │  │  (PG + Milvus)  │  │  (Hybrid)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Lifecycle Management                  ││
│  │   Extractor  │  ImportanceUpdater  │  Forgetter        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install redis asyncpg pymilvus sentence-transformers
```

### 2. 配置环境变量

```bash
cp .env.memory.example .env
# 编辑 .env 填入实际配置
```

### 3. 启动基础设施

```bash
# Redis
docker run -d --name redis -p 6379:6379 redis:latest

# PostgreSQL
docker run -d --name postgres \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=memory_db \
  -p 5432:5432 postgres:15

# Milvus
docker-compose -f docker-compose.milvus.yml up -d
```

### 4. 基本使用

```python
from dv_agent.memory import MemoryManager, MemoryConfig

# 初始化
config = MemoryConfig.from_env()
manager = MemoryManager(config)
await manager.initialize()

# 添加对话消息
await manager.add_message(
    session_id="session_001",
    user_id="user_001",
    message={"role": "user", "content": "我是一名Python开发者"}
)

# 获取上下文（用于注入 LLM prompt）
context = await manager.get_context(
    session_id="session_001",
    user_id="user_001",
    query="用户的技能",
)

# 提取并存储长期记忆
memories = await manager.extract_and_store(
    user_id="user_001",
    session_id="session_001",
)

# 关闭
await manager.shutdown()
```

## 核心概念

### 短期记忆 (ShortTermMemory)

- **存储**: Redis List
- **特点**: 滑动窗口，自动 TTL 过期
- **内容**: 当前会话消息 + 压缩摘要

```python
# 添加消息
await stm.add_message(session_id, {"role": "user", "content": "..."})

# 获取消息（最近 N 条）
messages = await stm.get_messages(session_id, limit=20)

# 获取/保存摘要
summary = await stm.get_summary(session_id)
await stm.save_summary(session_id, "会话摘要...")
```

### 长期记忆 (LongTermMemory)

- **主存储**: PostgreSQL (关系数据 + 全文索引)
- **向量索引**: Milvus (语义搜索)
- **一致性**: PG 为主，Milvus 最终一致

```python
# 存储记忆
memory = Memory(
    user_id="user_001",
    memory_type=MemoryType.FACT,
    content="用户精通Python异步编程",
    embedding=[...],  # 384维向量
    confidence=0.9,
    importance=0.8,
)
await ltm.store(memory)

# 向量搜索
results = await ltm.search_by_vector(user_id, embedding, top_k=10)

# 关键词搜索
results = await ltm.search_by_keyword(user_id, "Python", top_k=10)
```

### 记忆类型 (MemoryType)

| 类型 | 说明 | 示例 |
|------|------|------|
| `FACT` | 事实信息 | "用户在北京工作" |
| `PREFERENCE` | 用户偏好 | "用户喜欢简洁的代码风格" |
| `EXPERIENCE` | 经历经验 | "用户曾开发过电商系统" |
| `SKILL` | 技能能力 | "用户精通Docker" |
| `RELATIONSHIP` | 关系信息 | "用户与张三是同事" |
| `GOAL` | 目标意图 | "用户想学习Rust" |

### 混合检索 (MemoryRetriever)

三路并行召回 + Cross-Encoder 重排序:

```
Query
  │
  ├── Vector Search (Milvus) ──┐
  │                            │
  ├── Keyword Search (PG FTS) ─┼── Score Fusion ── Reranker ── Results
  │                            │
  └── Recency (PG) ────────────┘
```

```python
from dv_agent.memory.retrieval import RetrievalQuery

query = RetrievalQuery(
    user_id="user_001",
    query="Python异步编程经验",
    top_k=10,
    weights={"vector": 0.5, "keyword": 0.3, "recency": 0.2},
    memory_types=[MemoryType.SKILL, MemoryType.EXPERIENCE],
)

results = await retriever.retrieve(query, use_reranker=True)
```

### 生命周期管理

#### 记忆提取 (MemoryExtractor)

从对话中自动提取结构化记忆:

```python
memories = await extractor.extract(
    user_id="user_001",
    session_id="session_001",
    messages=[...],
)
```

#### 重要性衰减 (ImportanceUpdater)

记忆重要性随时间衰减:

$$importance = base \times e^{-\lambda t} + \alpha(access) + \beta(relations)$$

#### 遗忘机制 (MemoryForgetter)

三阶段遗忘:
1. **Soft Forget**: 标记为隐藏，不参与检索
2. **Archive**: 移至归档表，可恢复
3. **Hard Delete**: 永久删除

豁免条件:
- 高重要性 (importance > 0.8)
- 高访问量 (access_count > 50)
- 永久标记 (metadata.permanent = true)

## API 端点

```python
from dv_agent.memory import create_memory_router

# 集成到 FastAPI
app = FastAPI()
memory_router = create_memory_router(memory_manager)
app.include_router(memory_router)
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/session/{session_id}/summary` | GET | 获取会话摘要 |
| `/api/v1/memory/user/{user_id}` | GET | 获取用户记忆列表 |
| `/api/v1/memory/{memory_id}` | DELETE | 删除记忆 |
| `/api/v1/memory/{memory_id}` | PATCH | 更新记忆 |
| `/api/v1/memory/search` | POST | 检索记忆 |
| `/api/v1/memory/maintenance` | POST | 触发维护任务 |

## 后台任务

```python
from dv_agent.memory.lifecycle import MaintenanceWorker

worker = MaintenanceWorker(memory_manager)
await worker.start()
```

定时任务:
- **重要性更新**: 每小时
- **遗忘周期**: 每天凌晨
- **一致性检查**: 每天

## 性能优化

### 缓存策略

- 检索结果缓存: Redis, TTL 5分钟
- 嵌入向量缓存: 内存 LRU

### 批量操作

```python
# 批量存储
await ltm.store_batch(memories)

# 批量嵌入
embeddings = model.encode(texts, batch_size=32)
```

### 索引优化

PostgreSQL:
```sql
CREATE INDEX idx_memories_user_type ON memories(user_id, memory_type);
CREATE INDEX idx_memories_importance ON memories(importance) WHERE NOT is_forgotten;
CREATE INDEX idx_memories_fts ON memories USING GIN(to_tsvector('chinese', content));
```

Milvus:
```python
index_params = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 1024}
}
```

## 测试

```bash
# 单元测试
pytest tests/memory/ -v

# 集成测试（需要基础设施）
pytest tests/memory/ -m integration --run-integration

# 覆盖率
pytest tests/memory/ --cov=dv_agent.memory --cov-report=html
```

## 故障排除

### Milvus 连接失败

```
检查 Milvus 服务状态:
docker logs milvus-standalone
```

### PostgreSQL 全文索引不工作

```sql
-- 安装中文分词扩展
CREATE EXTENSION IF NOT EXISTS pg_jieba;
-- 或使用默认分词
ALTER TEXT SEARCH CONFIGURATION simple ALTER MAPPING FOR word WITH simple;
```

### 记忆不同步

手动触发一致性检查:
```python
await manager.run_consistency_check()
```

## 设计决策

1. **PG 为主**: PostgreSQL 作为数据源头，Milvus 仅作为向量索引
2. **最终一致**: 向量索引异步同步，容忍短暂不一致
3. **渐进遗忘**: 仿人类记忆，重要信息保留更久
4. **混合检索**: 语义+关键词+时间综合排序
