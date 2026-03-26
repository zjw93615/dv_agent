# Tasks: agent-memory-system

基于设计文档和规格说明的实现任务清单。

## 完成状态摘要

| 任务组 | 状态 | 完成数 |
|--------|------|--------|
| 1. 基础设施与配置 | ✅ 完成 | 6/6 |
| 2. 数据模型与配置 | ✅ 完成 | 3/3 |
| 3. 短期记忆实现 | ✅ 完成 | 6/6 |
| 4. 长期记忆存储 | ✅ 完成 | 7/7 |
| 5. 记忆检索 | ✅ 完成 | 8/8 |
| 6. 记忆生命周期管理 | ✅ 完成 | 9/9 |
| 7. MemoryManager 主入口 | ✅ 完成 | 6/6 |
| 8. 后台任务 Worker | ✅ 完成 | 6/6 |
| 9. Session 集成 | ✅ 完成 | 4/4 |
| 10. Agent 集成 | ✅ 完成 | 3/3 |
| 11. API 端点 | ✅ 完成 | 6/6 |
| 12. 测试 | ✅ 完成 | 5/5 |
| 13. 文档与配置 | ✅ 完成 | 3/3 |

**总进度: 72/72 (100%) ✓**

### 主要功能
- ✅ 分层记忆系统（短期 Redis + 长期 PG/Milvus）
- ✅ 混合检索（向量 + 关键词 + 时间）+ Cross-Encoder 重排序
- ✅ LLM 驱动的记忆提取
- ✅ 渐进遗忘机制（软删除 → 归档 → 硬删除）
- ✅ 后台维护任务
- ✅ Agent 集成（自动上下文压缩 + 记忆提取）
- ✅ REST API 端点
- ✅ 完整测试套件

---

## 1. 基础设施与配置

- [x] 1.1 创建 `src/dv_agent/memory/` 模块目录结构
- [x] 1.2 创建 `config/memory.yaml` 配置文件模板
- [x] 1.3 更新 `requirements.txt` 添加依赖（pymilvus, psycopg, sentence-transformers, cross-encoder）
- [x] 1.4 更新 `docker-compose.yml` 添加 PostgreSQL 和 Milvus 服务
- [x] 1.5 创建 PostgreSQL 数据库初始化脚本（user_memories, memory_relations, user_memories_archive 表）
- [x] 1.6 创建 Milvus Collection 初始化脚本（user_memory_vectors, enterprise_knowledge）

## 2. 数据模型与配置

- [x] 2.1 实现 `memory/models.py` - Memory, MemoryType, MemoryRelation 数据模型
- [x] 2.2 实现 `memory/config.py` - MemoryConfig 配置类，加载 memory.yaml
- [x] 2.3 扩展 `session/models.py` - 添加 memory_config 字段到 Session 模型

## 3. 短期记忆实现

- [x] 3.1 实现 `memory/short_term/window.py` - SlidingWindow 类，管理消息窗口
- [x] 3.2 实现 `memory/short_term/compressor.py` - TokenCompressor 类，LLM摘要生成
- [x] 3.3 实现 `memory/short_term/__init__.py` - ShortTermMemory 统一接口
- [x] 3.4 实现滑动窗口 Redis 操作（LPUSH/LTRIM/LRANGE）
- [x] 3.5 实现摘要存储与读取（stm:summary:{session_id}）
- [x] 3.6 实现窗口配置管理（stm:config:{session_id}）

## 4. 长期记忆存储

- [x] 4.1 实现 `memory/long_term/pg_store.py` - PostgresMemoryStore 类
- [x] 4.2 实现 PG CRUD 操作（create, read, update, soft_delete）
- [x] 4.3 实现 `memory/long_term/milvus_store.py` - MilvusMemoryStore 类
- [x] 4.4 实现 Milvus 向量写入与检索
- [x] 4.5 实现 `memory/long_term/embedding.py` - EmbeddingService 类
- [x] 4.6 实现 Embedding 生成与缓存
- [x] 4.7 实现 `memory/long_term/__init__.py` - LongTermMemory 统一接口，PG+Milvus同步写入

## 5. 记忆检索

- [x] 5.1 实现 `memory/retrieval/retriever.py` - MemoryRetriever 类
- [x] 5.2 实现向量检索路径（Milvus search）
- [x] 5.3 实现关键词检索路径（PG tsvector）
- [x] 5.4 实现时序检索路径（按last_accessed查询）
- [x] 5.5 实现多路并行召回（asyncio.gather）
- [x] 5.6 实现结果合并与去重
- [x] 5.7 实现 `memory/retrieval/reranker.py` - CrossEncoderReranker 类
- [x] 5.8 实现检索结果缓存（cache:memory:{user_id}:{query_hash}）

## 6. 记忆生命周期管理

- [x] 6.1 实现 `memory/lifecycle/extractor.py` - MemoryExtractor 类
- [x] 6.2 实现提取 Prompt 模板与 LLM 调用
- [x] 6.3 实现提取结果解析与验证
- [x] 6.4 实现 `memory/lifecycle/updater.py` - ImportanceUpdater 类
- [x] 6.5 实现重要性权重计算公式
- [x] 6.6 实现 `memory/lifecycle/forgetter.py` - MemoryForgetter 类
- [x] 6.7 实现三级遗忘策略（软遗忘、归档、硬删除）
- [x] 6.8 实现遗忘豁免逻辑
- [x] 6.9 实现记忆去重与冲突检测

## 7. MemoryManager 主入口

- [x] 7.1 实现 `memory/manager.py` - MemoryManager 类
- [x] 7.2 实现 add_to_short_term() 方法
- [x] 7.3 实现 get_context() 方法（获取完整上下文含摘要和长期记忆）
- [x] 7.4 实现 retrieve() 方法（统一检索入口）
- [x] 7.5 实现 extract_and_store() 方法（触发提取并存储）
- [x] 7.6 实现 `memory/__init__.py` 导出公开接口

## 8. 后台任务 Worker

- [x] 8.1 实现 `memory/lifecycle/worker.py` - MemoryLifecycleWorker 类
- [x] 8.2 实现权重更新定时任务
- [x] 8.3 实现软遗忘扫描定时任务
- [x] 8.4 实现归档执行定时任务
- [x] 8.5 实现 PG-Milvus 一致性检查任务
- [x] 8.6 集成到应用启动流程（后台协程）

## 9. Session 集成

- [x] 9.1 更新 `session/manager.py` - 添加 memory_config 参数到 create_session()
  - 实现: `memory/session_integration.py` - MemoryEnabledSessionManager
- [x] 9.2 更新 `session/manager.py` - get_history() 支持返回摘要
  - 实现: MemoryEnabledSessionManager.get_history_with_context()
- [x] 9.3 添加 Session 关闭/挂起时触发记忆提取的钩子
  - 实现: close_session_with_extraction(), suspend_session_with_extraction()
- [x] 9.4 添加 Session 恢复时加载相关长期记忆的逻辑
  - 实现: resume_session_with_context()

## 10. Agent 集成

- [x] 10.1 更新 `agents/base_agent.py` - 注入 MemoryManager 依赖
  - 添加 `memory_manager` 参数到 BaseAgent 构造函数
  - 添加 `enable_memory`, `memory_top_k`, `auto_extract_memory` 等配置到 AgentConfig
  - 添加 `max_context_tokens`, `compress_threshold_ratio` 支持自动压缩
- [x] 10.2 更新 Agent 上下文构建逻辑，融合短期摘要和长期记忆
  - 实现 `get_memory_context()` 方法获取融合上下文
  - 实现 `build_memory_prompt_section()` 构建 prompt
  - 实现 `_update_context_token_count()` 估算 token 数
  - 实现 `compress_context_if_needed()` 自动压缩上下文
- [x] 10.3 在 Agent 响应完成后触发记忆提取
  - 实现 `extract_and_store_memory()` 方法
  - 创建 `MemoryEnabledAgent` 类，自动在任务完成后提取记忆

## 11. API 端点

- [x] 11.1 添加 GET `/api/v1/session/{session_id}/summary` - 获取会话摘要
  - 实现: `memory/api.py` - get_session_summary()
- [x] 11.2 添加 GET `/api/v1/memory/user/{user_id}` - 查询用户记忆列表
  - 实现: `memory/api.py` - get_user_memories()
- [x] 11.3 添加 DELETE `/api/v1/memory/{memory_id}` - 删除记忆
  - 实现: `memory/api.py` - delete_memory()
- [x] 11.4 添加 PATCH `/api/v1/memory/{memory_id}` - 更新记忆（编辑、标记永久）
  - 实现: `memory/api.py` - update_memory()
- [x] 11.5 添加 POST `/api/v1/memory/search` - 记忆检索接口
  - 实现: `memory/api.py` - search_memories()
- [x] 11.6 添加 POST `/api/v1/memory/maintenance` - 维护任务接口
  - 实现: `memory/api.py` - run_maintenance()

## 12. 测试

- [x] 12.1 添加 `tests/memory/test_short_term.py` - 短期记忆单元测试
- [x] 12.2 添加 `tests/memory/conftest.py` - 测试 Fixtures
- [x] 12.3 添加 `tests/memory/test_retrieval.py` - 检索单元测试
- [x] 12.4 添加 `tests/memory/test_lifecycle.py` - 生命周期单元测试
- [x] 12.5 添加 `tests/memory/test_integration.py` - 集成测试

## 13. 文档与配置

- [x] 13.1 更新 README.md 添加记忆系统说明
  - 实现: `memory/README.md` - 完整的系统文档
- [x] 13.2 更新 .env.example 添加 PG 和 Milvus 连接配置
  - 实现: `.env.memory.example` - 记忆系统配置模板
- [x] 13.3 创建详细文档
  - 实现: `memory/README.md` 包含架构、使用、API、故障排除等
