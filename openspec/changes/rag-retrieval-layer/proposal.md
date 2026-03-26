## Why

当前 dv-agent 的记忆系统仅支持用户对话记忆的存储和检索，缺乏对外部知识文档的处理能力。为了让 AI Agent 能够基于企业知识库、技术文档等多格式文档提供精准回答，需要构建一个高性能的 RAG（检索增强生成）检索层。这将显著提升 Agent 在知识问答场景下的回答质量和准确性。

## What Changes

- **新增文档处理流水线**：支持 PDF、Word、Excel、PPT、HTML、Markdown 等多格式文档的解析、语义切分和文本清洗
- **升级向量化服务**：从 BGE-small-zh (512d) 升级到 BGE-M3 (1024d)，支持稀疏+稠密双向量
- **新增 RAG-Fusion 检索**：实现多查询融合、RRF 结果合并、Reranker 精排
- **新增混合检索优化**：向量检索 + BM25 关键词检索 + 稀疏向量检索三路并行
- **新增文档存储管理**：支持文档上传、版本管理、增量更新

## Capabilities

### New Capabilities

- `document-pipeline`: 多格式文档处理流水线，包括格式检测、内容提取、语义切分、文本清洗
- `rag-embedding`: BGE-M3 向量化服务，支持稀疏+稠密双向量生成与缓存
- `rag-fusion-retrieval`: RAG-Fusion 混合检索系统，包括多查询生成、三路检索、RRF融合、Reranker精排
- `document-store`: 文档存储管理，支持原始文档存储、chunk索引、元数据管理

### Modified Capabilities

- `memory-retrieval`: 扩展现有检索器以支持文档检索路径，复用混合检索和结果融合逻辑

## Impact

- **新增模块**: `src/dv_agent/rag/` 目录
- **依赖新增**: 
  - `unstructured[all-docs]` - 文档解析
  - `FlagEmbedding` - BGE-M3 模型
  - `sentence-transformers` - Reranker
- **存储扩展**: 
  - Milvus 新增文档向量 Collection
  - PostgreSQL 新增文档元数据表和全文索引
  - MinIO/S3 存储原始文档
- **API 新增**: 文档上传、检索、管理接口
- **配置扩展**: `config/rag.yaml` 新增 RAG 相关配置
