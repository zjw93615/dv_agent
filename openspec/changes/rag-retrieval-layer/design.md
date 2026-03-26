## Context

当前 dv-agent 已具备完整的记忆系统，包括：
- 短期记忆：Redis 存储对话窗口
- 长期记忆：Milvus 向量存储 + PostgreSQL 元数据
- 检索系统：向量检索 + 关键词检索 + 时序检索的多路召回

现有架构的局限性：
1. **数据源单一**：仅支持对话记忆，不支持外部知识文档
2. **文档处理缺失**：无法解析 PDF/Word 等格式
3. **向量模型简单**：BGE-small-zh (512d) 语义理解能力有限
4. **检索召回率受限**：缺少 RAG-Fusion 多查询优化和 Reranker 精排

利益相关者：
- 企业用户：需要基于内部知识库进行问答
- 开发团队：需要可扩展的 RAG 架构

## Goals / Non-Goals

**Goals:**
- 构建多格式文档处理流水线（PDF/Word/Excel/PPT/HTML/Markdown）
- 实现 BGE-M3 稀疏+稠密双向量支持
- 实现 RAG-Fusion 多查询融合检索
- 实现 Reranker 精排提升检索精准率
- 与现有记忆系统共享基础设施（Milvus/PostgreSQL/Redis）
- 支持文档级权限控制和租户隔离

**Non-Goals:**
- 不实现实时网页爬取（仅支持上传文档）
- 不实现 OCR 手写识别（仅支持印刷体）
- 不实现文档自动分类（由用户指定类别）
- 不实现知识图谱构建（纯向量检索方案）

## Decisions

### Decision 1: 文档解析框架选型

**选择**: Unstructured.io

**备选方案**:
| 方案 | 优点 | 缺点 |
|-----|------|------|
| Unstructured.io | 统一API、支持结构化提取、开源 | 依赖较重 |
| LangChain Loaders | 与现有栈集成好 | 功能较弱、解析质量一般 |
| 纯 PyMuPDF + python-docx | 轻量 | 需自行处理多格式、维护成本高 |

**理由**: Unstructured 提供统一抽象层，自动识别表格/标题/段落结构，减少多格式适配工作量。

### Decision 2: 向量化模型选型

**选择**: BGE-M3 (BAAI/bge-m3)

**备选方案**:
| 模型 | 维度 | 稀疏向量 | 中文效果 | 部署成本 |
|-----|------|---------|---------|---------|
| BGE-M3 | 1024 | ✅ 支持 | ⭐⭐⭐⭐⭐ | 本地GPU/CPU |
| BGE-large-zh | 1024 | ❌ | ⭐⭐⭐⭐⭐ | 本地GPU/CPU |
| OpenAI Embeddings | 1536 | ❌ | ⭐⭐⭐⭐ | API调用费 |

**理由**: 
1. BGE-M3 原生支持稀疏+稠密双向量，天然适配混合检索
2. 中文效果顶级（MTEB中文榜单Top3）
3. 本地部署满足企业数据隐私要求

### Decision 3: 混合检索策略

**选择**: 向量 + BM25 + 稀疏向量 + RRF 融合

**架构**:
```
Query → [Query Rewriting] → [RAG-Fusion 多查询生成]
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
      [Dense Vector]          [BM25 Search]         [Sparse Vector]
      (Milvus HNSW)           (PG TSVECTOR)         (Milvus Sparse)
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    ▼
                          [RRF Score Fusion]
                                    │
                                    ▼
                         [BGE-Reranker-v2-m3]
                                    │
                                    ▼
                            [Top-K Results]
```

**理由**: 三路检索互补——向量捕获语义、BM25捕获关键词、稀疏向量兼顾两者，RRF无需调参即可有效融合。

### Decision 4: 语义切分策略

**选择**: RecursiveCharacterTextSplitter + 结构感知增强

**配置**:
- `chunk_size`: 500 字符
- `chunk_overlap`: 50 字符 (10%)
- `separators`: 段落 → 句号 → 逗号 → 空格

**增强**:
- 保留 chunk 与父文档的关联（Parent-Child Chunking）
- 检索返回相邻 chunk 扩展上下文

**理由**: 平衡检索精度与上下文完整性，避免关键信息被截断。

### Decision 5: 存储架构

**选择**: 复用现有基础设施 + 新增 Collection/Table

| 数据类型 | 存储 | 说明 |
|---------|------|------|
| 原始文档 | MinIO/S3 | 按 tenant_id/doc_id 存储 |
| 文档元数据 | PostgreSQL | documents 表 + TSVECTOR 全文索引 |
| 稠密向量 | Milvus | doc_embeddings Collection (HNSW索引) |
| 稀疏向量 | Milvus | doc_sparse_embeddings Collection |
| 向量缓存 | Redis | 减少重复 Embedding 计算 |

**理由**: 复用现有基础设施降低运维成本，分离存储职责便于独立扩展。

### Decision 6: Reranker 选型

**选择**: bge-reranker-v2-m3

**备选方案**:
| 模型 | 语言支持 | 效果 | 部署方式 |
|-----|---------|------|---------|
| bge-reranker-v2-m3 | 多语言 | ⭐⭐⭐⭐⭐ | 本地 |
| cohere-rerank | 多语言 | ⭐⭐⭐⭐⭐ | API |
| ms-marco-MiniLM | 英文为主 | ⭐⭐⭐⭐ | 本地 |

**理由**: 与 BGE-M3 同系列，中文效果优秀，可本地部署。

## Risks / Trade-offs

### R1: GPU 资源需求增加
**风险**: BGE-M3 (1024d) + Reranker 需要更多 GPU 显存
**缓解**: 
- 支持 CPU 推理（速度降级）
- 批量处理减少调用次数
- 向量缓存避免重复计算

### R2: 文档处理延迟
**风险**: 大型文档（>100页）处理时间较长
**缓解**:
- 异步任务队列处理
- 进度回调通知用户
- 支持增量更新避免全量重处理

### R3: 稀疏向量存储开销
**风险**: 稀疏向量存储空间较大
**缓解**:
- 设置最小权重阈值过滤低权重token
- 仅保留 Top-K 稀疏特征

### R4: 与现有记忆系统的边界
**风险**: RAG文档检索与记忆检索的混淆
**缓解**:
- 明确分离 Collection/Table
- 检索接口通过参数区分来源
- 未来可通过统一检索层抽象

## Migration Plan

### Phase 1: 基础设施准备
1. 创建 Milvus 新 Collection：`doc_embeddings`, `doc_sparse_embeddings`
2. 创建 PostgreSQL 新表：`documents`, `document_chunks`
3. 配置 MinIO bucket：`dv-agent-documents`

### Phase 2: 核心模块实现
1. 文档处理流水线 (`document-pipeline`)
2. BGE-M3 向量服务 (`rag-embedding`)
3. 文档存储管理 (`document-store`)

### Phase 3: 检索层实现
1. RAG-Fusion 检索器 (`rag-fusion-retrieval`)
2. 扩展 memory-retrieval 支持文档检索

### Phase 4: 集成与测试
1. API 接口暴露
2. 端到端测试
3. 性能基准测试

### Rollback Strategy
- 新模块独立于现有记忆系统，可直接移除
- 新 Collection/Table 可独立删除
- 配置开关控制是否启用 RAG 功能

## Open Questions

1. **Q: 是否需要支持实时文档更新？**
   - 当前设计为批量上传+异步处理
   - 如需实时更新，需引入增量索引机制

2. **Q: Reranker 推理延迟是否可接受？**
   - 预计 p99 增加 ~100ms
   - 可通过配置开关禁用精排

3. **Q: 是否需要支持多租户权限隔离？**
   - 当前设计通过 tenant_id 分区
   - 细粒度权限（文档级）待确认需求
