## 1. 基础设施准备

- [x] 1.1 创建 `src/dv_agent/rag/` 目录结构
- [x] 1.2 添加 RAG 相关依赖到 requirements.txt（unstructured、FlagEmbedding、sentence-transformers）
- [x] 1.3 创建 `config/rag.yaml` 配置文件模板
- [x] 1.4 创建 PostgreSQL 文档表迁移脚本（documents、document_chunks 表）
- [x] 1.5 创建 Milvus Collection 初始化脚本（doc_embeddings、doc_sparse_embeddings）
- [x] 1.6 配置 MinIO bucket 初始化脚本

## 2. 文档处理流水线 (document-pipeline)

- [x] 2.1 创建 `rag/pipeline/__init__.py` 模块结构
- [x] 2.2 实现格式检测器 `rag/pipeline/detector.py`（支持 PDF/Word/Excel/PPT/HTML/Markdown）
- [x] 2.3 实现文档提取器 `rag/pipeline/extractor.py`（基于 Unstructured）
- [x] 2.4 实现语义切分器 `rag/pipeline/chunker.py`（RecursiveCharacterTextSplitter）
- [x] 2.5 实现文本清洗器 `rag/pipeline/cleaner.py`（去噪、标准化）
- [x] 2.6 实现元数据提取器 `rag/pipeline/metadata.py`
- [x] 2.7 实现流水线编排器 `rag/pipeline/orchestrator.py`（整合各步骤）
- [x] 2.8 添加流水线单元测试 `tests/rag/test_pipeline.py`

## 3. BGE-M3 向量化服务 (rag-embedding)

- [x] 3.1 创建 `rag/embedding/__init__.py` 模块结构
- [x] 3.2 实现 BGE-M3 服务 `rag/embedding/bge_m3.py`（稠密+稀疏双向量）
- [x] 3.3 实现向量缓存管理（复用 Redis）
- [x] 3.4 实现延迟加载和 GPU/CPU 自动检测
- [x] 3.5 实现稀疏向量过滤（低权重过滤、Top-K）
- [x] 3.6 添加向量化服务单元测试 `tests/rag/test_embedding.py`

## 4. 文档存储管理 (document-store)

- [x] 4.1 创建 `rag/store/__init__.py` 模块结构
- [x] 4.2 实现 MinIO 存储适配器 `rag/store/minio_client.py`
- [x] 4.3 实现 PostgreSQL 文档元数据存储 `rag/store/pg_document.py`
- [x] 4.4 实现 Milvus 向量存储适配器 `rag/store/milvus_document.py`
- [x] 4.5 实现文档管理器 `rag/store/manager.py`（CRUD 操作）
- [x] 4.6 实现租户隔离和配额检查
- [x] 4.7 实现异步处理任务队列
- [x] 4.8 添加文档存储单元测试 `tests/rag/test_store.py`

## 5. RAG-Fusion 检索系统 (rag-fusion-retrieval)

- [x] 5.1 创建 `rag/retrieval/__init__.py` 模块结构
- [x] 5.2 实现多查询生成器 `rag/retrieval/query_generator.py`（LLM 调用）
- [x] 5.3 实现稠密向量检索 `rag/retrieval/dense_search.py`
- [x] 5.4 实现 BM25 检索 `rag/retrieval/bm25_search.py`
- [x] 5.5 实现稀疏向量检索 `rag/retrieval/sparse_search.py`
- [x] 5.6 实现 RRF 融合算法 `rag/retrieval/rrf_fusion.py`
- [x] 5.7 实现 Reranker 精排 `rag/retrieval/reranker.py`（bge-reranker-v2-m3）
- [x] 5.8 实现检索编排器 `rag/retrieval/retriever.py`（整合各步骤）
- [x] 5.9 实现检索结果缓存 `rag/retrieval/cache.py`
- [x] 5.10 添加检索系统单元测试 `tests/rag/test_retrieval.py`

## 6. Memory-Retrieval 扩展

- [x] 6.1 扩展 `memory/retrieval/unified_retriever.py` 支持 documents 源
- [x] 6.2 集成 RRF 融合到现有检索器（通过 HybridRetriever）
- [x] 6.3 升级 Reranker 模型为 bge-reranker-v2-m3
- [x] 6.4 实现文档-记忆统一检索结果格式（UnifiedResult）
- [x] 6.5 添加稀疏向量检索路径
- [x] 6.6 更新检索器单元测试 `tests/memory/test_unified_retriever.py`

## 7. API 接口层

- [x] 7.1 创建文档上传接口 `POST /rag/documents/upload`
- [x] 7.2 创建文档列表接口 `GET /rag/documents`
- [x] 7.3 创建文档详情接口 `GET /rag/documents/{id}`
- [x] 7.4 创建文档删除接口 `DELETE /rag/documents/{id}`
- [x] 7.5 创建文档处理状态接口（合并到文档详情接口）
- [x] 7.6 创建统一检索接口 `POST /rag/search`（支持记忆+文档）
- [x] 7.7 添加 API 接口文档（FastAPI 自动生成 OpenAPI/Swagger）

## 8. 配置与集成

- [x] 8.1 实现 RAG 配置加载 `rag/config.py`
- [x] 8.2 集成到主应用启动流程 `rag/bootstrap.py`
- [x] 8.3 添加 Docker Compose 服务配置 `docker-compose.rag.yml`
- [x] 8.4 更新环境变量示例 `.env.example`
- [x] 8.5 编写 RAG 模块 README 文档

## 9. 测试与验证

- [x] 9.1 编写端到端集成测试 `tests/test_rag_integration.py`
- [x] 9.2 编写性能基准测试 `tests/rag/test_benchmark.py`
- [x] 9.3 测试多格式文档处理 `tests/rag/test_benchmark.py::TestMultiFormatProcessing`
- [x] 9.4 测试检索召回率和精准率（通过 benchmark 测试覆盖）
- [x] 9.5 测试租户隔离功能 `tests/rag/test_benchmark.py::TestTenantIsolation`

---

## ✅ 完成状态

**所有 61 项任务已全部完成！**

### 实现的核心文件

```
src/dv_agent/rag/
├── __init__.py              # 模块入口
├── api.py                   # FastAPI 路由
├── bootstrap.py             # 服务启动器
├── config.py                # 配置管理
├── README.md                # 模块文档
├── embedding/
│   ├── __init__.py
│   └── bge_m3.py            # BGE-M3 嵌入器
├── pipeline/
│   ├── __init__.py
│   ├── detector.py          # 文档类型检测
│   ├── extractor.py         # 文本提取
│   ├── chunker.py           # 文本分块
│   ├── cleaner.py           # 文本清洗
│   ├── metadata.py          # 元数据提取
│   └── orchestrator.py      # 流水线编排
├── retrieval/
│   ├── __init__.py
│   ├── retriever.py         # 混合检索器
│   ├── dense_search.py      # 稠密检索
│   ├── sparse_search.py     # 稀疏检索
│   ├── bm25_search.py       # BM25 检索
│   ├── rrf_fusion.py        # RRF 融合
│   ├── reranker.py          # 重排序
│   ├── query_generator.py   # 查询扩展
│   └── cache.py             # 检索缓存
└── store/
    ├── __init__.py
    ├── manager.py           # 文档管理器
    ├── minio_client.py      # MinIO 客户端
    ├── pg_document.py       # PostgreSQL 存储
    └── milvus_document.py   # Milvus 存储

src/dv_agent/memory/retrieval/
└── unified_retriever.py     # 统一检索器

tests/
├── test_rag_integration.py  # 集成测试
├── rag/
│   ├── __init__.py
│   ├── test_store.py        # 存储测试
│   ├── test_retrieval.py    # 检索测试
│   └── test_benchmark.py    # 性能测试
└── memory/
    └── test_unified_retriever.py  # 统一检索器测试

配置文件:
├── docker-compose.rag.yml   # Docker 服务配置
├── .env.example             # 环境变量示例（已更新）
└── config/rag.yaml          # RAG 配置模板
```