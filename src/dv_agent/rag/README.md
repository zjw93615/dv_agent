# DV-Agent RAG Module

## 概述

RAG（Retrieval-Augmented Generation）模块为 DV-Agent 提供文档检索增强生成能力，使 Agent 能够利用外部知识库来增强回答质量。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG Module                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Pipeline  │  │  Embedding  │  │    Store    │             │
│  │  ─────────  │  │  ─────────  │  │  ─────────  │             │
│  │  • Detector │  │  • BGE-M3   │  │  • MinIO    │             │
│  │  • Extractor│  │    Dense    │  │  • Postgres │             │
│  │  • Chunker  │  │    Sparse   │  │  • Milvus   │             │
│  │  • Cleaner  │  │    ColBERT  │  │             │             │
│  │  • Metadata │  │             │  │             │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Retrieval                             │   │
│  │  ─────────────────────────────────────────────────────   │   │
│  │  • Query Expansion (RAG-Fusion)                          │   │
│  │  • Multi-path Recall (Dense + Sparse + BM25)             │   │
│  │  • RRF Fusion                                            │   │
│  │  • Cross-Encoder Reranking                               │   │
│  │  • Two-tier Cache (LRU + Redis)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      API                                 │   │
│  │  ─────────────────────────────────────────────────────   │   │
│  │  • POST /rag/documents/upload                            │   │
│  │  • GET/DELETE /rag/documents/{id}                        │   │
│  │  • POST /rag/search                                      │   │
│  │  • GET /rag/collections                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 模块说明

### 1. Pipeline（文档处理流水线）

负责将原始文档转换为可检索的结构化数据。

- **DocumentDetector**: 检测文档类型（PDF, DOCX, TXT, MD, HTML）
- **DocumentExtractor**: 提取文档文本内容
- **TextChunker**: 智能文本分块（支持语义边界感知）
- **TextCleaner**: 文本清洗和标准化
- **MetadataExtractor**: 元数据提取

### 2. Embedding（向量化服务）

使用 BGE-M3 模型生成多粒度向量表示。

- **Dense Embedding**: 1024 维稠密向量（语义相似度）
- **Sparse Embedding**: 稀疏词汇向量（关键词匹配）
- **ColBERT Embedding**: 多向量表示（细粒度匹配）

### 3. Store（存储管理）

多后端存储架构支持高效的数据管理。

- **MinIO**: 原始文档文件存储
- **PostgreSQL**: 文档元数据 + BM25 全文索引
- **Milvus**: 向量索引（Dense + Sparse）

### 4. Retrieval（检索系统）

RAG-Fusion 混合检索实现高召回率和高精度。

- **Query Expansion**: LLM/规则驱动的查询扩展
- **Multi-path Recall**: Dense + Sparse + BM25 三路并行检索
- **RRF Fusion**: Reciprocal Rank Fusion 结果融合
- **Reranking**: Cross-Encoder 精排
- **Cache**: 本地 LRU + Redis 两级缓存

### 5. API（HTTP 接口）

FastAPI 实现的 RESTful 接口。

## 快速开始

### 安装依赖

```bash
pip install transformers sentence-transformers FlagEmbedding
pip install pymilvus minio asyncpg
pip install fastapi uvicorn
```

### 配置

创建配置文件 `config/rag.yaml`:

```yaml
embedding:
  model_name: BAAI/bge-m3
  model_path: ./models/bge-m3
  device: cuda
  batch_size: 32

milvus:
  host: localhost
  port: 19530

postgres:
  host: localhost
  port: 5432
  database: dv_agent
  user: postgres
  password: your_password

minio:
  endpoint: localhost:9000
  access_key: minioadmin
  secret_key: minioadmin

retrieval:
  default_top_k: 10
  use_reranking: true
  reranker_model: BAAI/bge-reranker-v2-m3
```

### 使用示例

```python
import asyncio
from dv_agent.rag import get_rag_config
from dv_agent.rag.embedding import BGEM3Embedder
from dv_agent.rag.store import DocumentManager
from dv_agent.rag.retrieval import HybridRetriever

async def main():
    # 加载配置
    config = get_rag_config("config/rag.yaml")
    
    # 初始化组件
    embedder = BGEM3Embedder(config.embedding.model_path)
    await embedder.initialize()
    
    # ... 初始化存储组件 ...
    
    # 创建检索器
    retriever = HybridRetriever(embedder=embedder, ...)
    
    # 执行检索
    response = await retriever.simple_search(
        query="什么是机器学习？",
        tenant_id="tenant_001",
        top_k=10,
    )
    
    for result in response.results:
        print(f"Score: {result.final_score:.4f}")
        print(f"Content: {result.content[:200]}...")
        print()

asyncio.run(main())
```

### FastAPI 集成

```python
from fastapi import FastAPI
from dv_agent.rag.api import router as rag_router, RAGDependencies

app = FastAPI()

@app.on_event("startup")
async def startup():
    # 初始化并注入依赖
    RAGDependencies.set_document_manager(document_manager)
    RAGDependencies.set_retriever(retriever)

app.include_router(rag_router)
```

## API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/rag/documents/upload` | 上传文档 |
| GET | `/rag/documents/{id}` | 获取文档详情 |
| DELETE | `/rag/documents/{id}` | 删除文档 |
| GET | `/rag/documents` | 列出文档 |
| POST | `/rag/search` | 高级检索 |
| GET | `/rag/search/simple` | 简单检索 |
| GET | `/rag/collections` | 列出集合 |
| POST | `/rag/collections` | 创建集合 |
| DELETE | `/rag/collections/{id}` | 删除集合 |

## 统一检索（Memory + RAG）

将对话记忆与知识文档整合为统一检索接口：

```python
from dv_agent.memory.retrieval import UnifiedRetriever, UnifiedQuery, SourceType

query = UnifiedQuery(
    user_id="user_001",
    tenant_id="tenant_001",
    query="关于机器学习的内容",
    sources=[SourceType.MEMORY, SourceType.DOCUMENT],
    memory_weight=0.3,
    document_weight=0.7,
)

response = await retriever.retrieve(query)
context = response.to_context(max_tokens=4000)
```

## 性能优化

1. **批量处理**: 支持批量文档处理和向量生成
2. **异步并行**: 多路检索并行执行
3. **两级缓存**: 本地 LRU 缓存 + Redis 分布式缓存
4. **向量量化**: Milvus IVF_FLAT 索引加速检索
5. **连接池**: 数据库连接池管理

## 多租户支持

所有操作都基于 `tenant_id` 进行隔离：

- 文档存储路径隔离
- 向量集合隔离
- 配额限制

## 测试

```bash
# 运行测试
pytest tests/test_rag_integration.py -v

# 运行特定测试
pytest tests/test_rag_integration.py::TestRRFFusion -v
```

## 文件结构

```
src/dv_agent/rag/
├── __init__.py          # 模块入口
├── api.py               # FastAPI 路由
├── config.py            # 配置管理
├── embedding/
│   ├── __init__.py
│   └── bge_m3.py        # BGE-M3 嵌入器
├── pipeline/
│   ├── __init__.py
│   ├── detector.py      # 文档类型检测
│   ├── extractor.py     # 文本提取
│   ├── chunker.py       # 文本分块
│   ├── cleaner.py       # 文本清洗
│   ├── metadata.py      # 元数据提取
│   └── orchestrator.py  # 流水线编排
├── retrieval/
│   ├── __init__.py
│   ├── retriever.py     # 混合检索器
│   ├── dense_search.py  # 稠密检索
│   ├── sparse_search.py # 稀疏检索
│   ├── bm25_search.py   # BM25 检索
│   ├── rrf_fusion.py    # RRF 融合
│   ├── reranker.py      # 重排序
│   ├── query_generator.py # 查询扩展
│   └── cache.py         # 检索缓存
└── store/
    ├── __init__.py
    ├── manager.py       # 文档管理器
    ├── minio_client.py  # MinIO 客户端
    ├── pg_document.py   # PostgreSQL 存储
    └── milvus_document.py # Milvus 存储
```
