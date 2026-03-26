## Context

本项目为 dv-agent 构建分层记忆系统，支持企业知识库助手场景。当前状态：

- **已有**：基于 Redis 的 SessionManager，支持对话历史和 Agent 上下文存储
- **缺失**：长期记忆、语义检索、知识提取、记忆生命周期管理

### 约束条件

- **技术栈**：Python 3.10+，现有 Redis 基础设施
- **新增依赖**：PostgreSQL 14+，Milvus 2.3+
- **一致性要求**：最终一致性（允许秒级延迟）
- **数据规模**：当前 <10万条，需支持扩展至百万级

## Goals / Non-Goals

**Goals:**

1. 实现短期记忆滑动窗口，支持 Token 压缩和摘要生成
2. 构建 PostgreSQL + Milvus 联动的长期记忆存储架构
3. 实现多路召回 + Cross-Encoder 重排序的检索策略
4. 支持记忆的自动提取、权重更新和智能遗忘
5. 分离私有用户记忆与企业共享知识库
6. 提供独立的 MemoryManager，与现有 SessionManager 解耦

**Non-Goals:**

1. 不实现实时知识图谱（本版本仅支持简单关系）
2. 不实现多模态记忆（仅文本）
3. 不实现跨租户记忆共享（企业隔离）
4. 不实现记忆的可视化管理界面
5. 不支持记忆的导入导出功能（未来版本）

## Decisions

### Decision 1: 短期记忆存储 - Redis 滑动窗口

**选择**：使用 Redis List 实现滑动窗口，Hash 存储压缩摘要。

**理由**：
- 复用现有 Redis 基础设施，无额外运维成本
- List 原生支持 LPUSH/LTRIM 实现滑动窗口
- 与现有 SessionManager 数据结构兼容

**数据结构**：
```
stm:window:{session_id}   # List - 最近N条完整消息
stm:summary:{session_id}  # String - 压缩后的历史摘要
stm:config:{session_id}   # Hash - 窗口配置(size, token_limit)
```

**备选方案**：
| 方案 | 优点 | 缺点 |
|------|------|------|
| 全量存储 | 无损失 | Token 超限，成本高 |
| 仅存摘要 | 节省空间 | 丢失细节上下文 |

---

### Decision 2: 长期记忆存储 - PostgreSQL + Milvus 联动

**选择**：PostgreSQL 存储结构化元数据，Milvus 存储向量，通过 ID 关联。

**理由**：
- PG 提供 ACID 事务、复杂查询、关系存储能力
- Milvus 专注向量检索，支持分区裁剪，性能优秀
- ID 关联保证数据一致性，支持独立扩展

**同步机制**：
```
写入流程:
1. BEGIN PG Transaction
2. INSERT INTO user_memories → 获取 id
3. INSERT INTO Milvus (使用相同 id)
4. COMMIT PG Transaction
5. 异步投递后处理任务 (去重、关系抽取)
```

**备选方案**：
| 方案 | 优点 | 缺点 |
|------|------|------|
| 纯 Milvus | 架构简单 | 缺乏复杂查询能力 |
| PG + pgvector | 单一存储 | 向量性能不如 Milvus |
| Weaviate | 一体化 | 生态不如 Milvus |

---

### Decision 3: 向量索引 - Milvus IVF_FLAT + 分区

**选择**：使用 IVF_FLAT 索引，按 user_id 分区。

**理由**：
- IVF_FLAT 在中等规模下精度和性能平衡好
- 分区裁剪显著减少检索范围（用户级隔离）
- 支持后续升级到 HNSW（更大规模时）

**配置**：
```yaml
collection: user_memory_vectors
index_type: IVF_FLAT
nlist: 1024
metric_type: COSINE
partition_key: user_id
```

---

### Decision 4: Embedding 模型 - 本地 sentence-transformers

**选择**：使用 `sentence-transformers/all-MiniLM-L6-v2`（384维）作为默认，可配置切换。

**理由**：
- 本地部署，无 API 调用成本和延迟
- 384 维平衡了精度和存储
- 支持中文可切换 `paraphrase-multilingual-MiniLM-L12-v2`

**备选方案**：
| 方案 | 优点 | 缺点 |
|------|------|------|
| OpenAI text-embedding-3 | 精度高 | API 成本，延迟 |
| BGE-M3 | 多语言优秀 | 模型较大 |

---

### Decision 5: 检索策略 - 多路召回 + Cross-Encoder

**选择**：向量检索 + 关键词检索 + 时序检索，Cross-Encoder 精排 Top 10。

**理由**：
- 多路召回提升召回率和多样性
- Cross-Encoder 显著提升精排精度
- Top 10 限制控制推理成本

**流程**：
```
Query → 并行3路召回(各20条) → 合并去重(~35条) → Cross-Encoder(取Top10) → 返回
```

**精排模型**：`cross-encoder/ms-marco-MiniLM-L-6-v2`

---

### Decision 6: 记忆提取 - 对话结束触发

**选择**：每轮对话结束后同步提取，异步写入存储。

**理由**：
- 实时性好，不会漏掉短会话
- 异步写入不阻塞响应
- 提取 prompt 调用轻量模型（gpt-4o-mini）

**触发点**：
- Agent 返回最终响应后
- Session 主动关闭时
- 对话超时挂起时

---

### Decision 7: 遗忘机制 - 三级渐进遗忘

**选择**：软遗忘 → 归档 → 硬删除 三级策略。

**理由**：
- 渐进式避免误删重要记忆
- 归档保留审计能力
- 符合企业数据合规要求

**阈值配置**：
```yaml
forget:
  soft_threshold: 0.1      # importance < 0.1 触发软遗忘
  archive_days: 30         # 软遗忘30天后归档
  delete_days: 180         # 归档180天后硬删除
  exempt_types: ["entity"] # 豁免类型
  exempt_access_count: 10  # 访问次数>10豁免
```

---

### Decision 8: 架构分层 - 独立 MemoryManager

**选择**：MemoryManager 作为独立模块，不扩展 SessionManager。

**理由**：
- 单一职责，避免 SessionManager 过度膨胀
- 可独立演进和测试
- 清晰的依赖边界

**模块结构**：
```
src/dv_agent/memory/
├── __init__.py
├── manager.py           # MemoryManager 主入口
├── models.py            # 数据模型
├── short_term/          # 短期记忆
│   ├── window.py        # 滑动窗口
│   └── compressor.py    # Token压缩
├── long_term/           # 长期记忆
│   ├── pg_store.py      # PostgreSQL存储
│   └── milvus_store.py  # Milvus存储
├── retrieval/           # 检索
│   ├── retriever.py     # 统一检索器
│   └── reranker.py      # Cross-Encoder重排序
├── lifecycle/           # 生命周期
│   ├── extractor.py     # 知识提取
│   ├── updater.py       # 权重更新
│   └── forgetter.py     # 遗忘机制
└── config.py            # 配置
```

## Risks / Trade-offs

### Risk 1: PostgreSQL + Milvus 数据不一致

**风险**：写入过程中一方失败导致数据不一致。

**缓解**：
- PG 事务包裹 Milvus 写入
- 定期一致性检查任务
- 不一致时以 PG 为准（Milvus 可重建）

---

### Risk 2: Cross-Encoder 推理延迟

**风险**：精排增加 50-100ms 延迟。

**缓解**：
- 限制候选数量（最多 30 条进精排）
- 使用轻量模型（MiniLM）
- 可配置关闭精排（降级模式）

---

### Risk 3: 记忆提取 LLM 成本

**风险**：每轮对话都调用 LLM 提取，成本累积。

**缓解**：
- 使用低成本模型（gpt-4o-mini）
- 设置最小对话轮数阈值（如 3 轮以上才提取）
- 提取结果缓存复用

---

### Risk 4: Milvus 冷启动延迟

**风险**：首次加载 Collection 较慢。

**缓解**：
- 服务启动时预加载常用 Collection
- 使用连接池保持连接
- 分区按需加载

---

### Risk 5: 向量维度与模型绑定

**风险**：切换 Embedding 模型需重建向量。

**缓解**：
- 配置中记录向量维度和模型版本
- 提供向量重建工具
- 新模型作为新 Collection 灰度

## Migration Plan

### 阶段 1: 基础设施准备

1. 部署 PostgreSQL 14+
2. 部署 Milvus 2.3+（单机或集群）
3. 更新 docker-compose.yml
4. 创建数据库 Schema

### 阶段 2: 核心模块实现

1. 实现 MemoryManager 基础框架
2. 实现短期记忆滑动窗口
3. 实现长期记忆 PG + Milvus 存储
4. 实现统一检索接口

### 阶段 3: 生命周期管理

1. 实现记忆提取器
2. 实现权重更新机制
3. 实现遗忘机制
4. 添加后台 Worker

### 阶段 4: 集成与测试

1. 集成到 Agent 流程
2. 添加 API 端点
3. 性能测试与调优
4. 文档更新

### 回滚策略

- 记忆系统作为可选模块，配置开关控制
- 回滚时禁用记忆功能，不影响核心对话
- 数据保留，恢复后可继续使用

## Open Questions

1. **企业知识库管理**
   - 知识库的更新流程？批量导入 vs 增量同步？
   - 需要版本管理吗？

2. **多租户隔离**
   - 当前设计按 user_id 隔离私有记忆
   - 是否需要 org_id 级别的隔离？

3. **监控指标**
   - 需要监控哪些记忆系统指标？
   - 召回率、延迟、存储用量？

4. **隐私合规**
   - 用户记忆是否需要支持"被遗忘权"？
   - 数据导出需求？
