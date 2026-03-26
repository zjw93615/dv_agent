## ADDED Requirements

### Requirement: RAG-Fusion multi-query generation
系统 SHALL 使用 LLM 生成多个查询变体以提高召回率。

#### Scenario: Generate query variants
- **WHEN** 系统收到用户查询
- **THEN** 系统使用 LLM 生成 3-5 个语义相似但表述不同的查询变体

#### Scenario: Include original query
- **WHEN** 系统执行多查询检索
- **THEN** 原始用户查询作为第一个查询，与生成的变体一起检索

#### Scenario: Query generation timeout
- **WHEN** LLM 响应超时（>3秒）
- **THEN** 系统仅使用原始查询继续检索，不阻塞流程

### Requirement: Three-way parallel retrieval
系统 SHALL 并行执行向量检索、BM25 检索和稀疏向量检索。

#### Scenario: Dense vector search
- **WHEN** 系统执行检索
- **THEN** 系统在 Milvus 中使用稠密向量进行 HNSW 近似搜索

#### Scenario: BM25 keyword search
- **WHEN** 系统执行检索
- **THEN** 系统在 PostgreSQL 中使用 TSVECTOR 进行全文检索

#### Scenario: Sparse vector search
- **WHEN** 系统执行检索
- **THEN** 系统在 Milvus 中使用稀疏向量进行检索

#### Scenario: Parallel execution
- **WHEN** 系统同时发起三路检索
- **THEN** 三路检索并行执行，总延迟取决于最慢的一路

### Requirement: Reciprocal Rank Fusion (RRF)
系统 SHALL 使用 RRF 算法融合多路检索结果。

#### Scenario: Calculate RRF score
- **WHEN** 同一文档出现在多个检索结果中
- **THEN** 系统使用 RRF 公式计算最终分数：score = Σ 1/(k + rank_i)，k 默认为 60

#### Scenario: Handle missing results
- **WHEN** 某文档仅出现在部分检索结果中
- **THEN** 该文档仅计算其出现的检索路径的 RRF 分数

#### Scenario: Deduplicate results
- **WHEN** 同一文档从多个查询变体中被检索到
- **THEN** 系统去重，保留最高的 RRF 分数

### Requirement: Cross-encoder reranking
系统 SHALL 使用 Cross-Encoder 模型对候选结果进行精排。

#### Scenario: Rerank top candidates
- **WHEN** RRF 融合产生 Top-N 候选结果（默认 N=20）
- **THEN** 系统使用 bge-reranker-v2-m3 模型对候选进行重排序

#### Scenario: Return reranked results
- **WHEN** 精排完成
- **THEN** 系统返回按相关性得分排序的 Top-K 结果（默认 K=5）

#### Scenario: Reranker disabled
- **WHEN** 配置禁用精排（use_reranker=false）
- **THEN** 系统直接返回 RRF 融合结果，跳过精排步骤

### Requirement: Retrieval result formatting
系统 SHALL 返回结构化的检索结果。

#### Scenario: Result structure
- **WHEN** 检索完成
- **THEN** 每个结果包含：document_id、chunk_id、content、score、metadata

#### Scenario: Score normalization
- **WHEN** 系统返回检索分数
- **THEN** 分数归一化到 [0, 1] 范围，1 表示最相关

### Requirement: Retrieval filtering
系统 SHALL 支持按条件过滤检索结果。

#### Scenario: Filter by tenant
- **WHEN** 请求指定 tenant_id
- **THEN** 检索结果仅包含该租户的文档

#### Scenario: Filter by document type
- **WHEN** 请求指定 document_types 列表
- **THEN** 检索结果仅包含指定类型的文档

#### Scenario: Filter by date range
- **WHEN** 请求指定 date_from 和 date_to
- **THEN** 检索结果仅包含该时间范围内创建的文档

### Requirement: Retrieval caching
系统 SHALL 缓存检索结果以提高重复查询的响应速度。

#### Scenario: Cache identical queries
- **WHEN** 相同用户在短时间内发起相同查询
- **THEN** 系统返回缓存结果，缓存 TTL 为 5 分钟

#### Scenario: Skip cache option
- **WHEN** 请求指定 skip_cache=true
- **THEN** 系统绕过缓存执行实时检索

### Requirement: Retrieval performance requirements
系统 SHALL 满足性能要求。

#### Scenario: Latency requirement
- **WHEN** 系统执行检索（包含精排）
- **THEN** p99 延迟应小于 500ms

#### Scenario: Throughput requirement
- **WHEN** 系统处于正常负载
- **THEN** 单节点 QPS 应大于 50
