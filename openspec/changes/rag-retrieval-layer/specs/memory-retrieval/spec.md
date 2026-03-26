## MODIFIED Requirements

### Requirement: 统一检索接口

系统SHALL提供统一的记忆检索接口，支持多种记忆源。

#### Scenario: 基本检索调用
- **WHEN** 调用 retrieve(query, user_id, top_k)
- **THEN** 系统返回按相关性排序的记忆列表
- **AND** 每条记忆包含 content, score, source, memory_type

#### Scenario: 记忆源配置
- **WHEN** 调用检索时指定 sources 参数
- **THEN** 系统仅从指定的源检索
- **AND** 可选源包括：short_term, long_term, shared_knowledge, **documents**

#### Scenario: 默认检索全部源
- **WHEN** 调用检索时未指定 sources
- **THEN** 系统从所有可用源检索
- **AND** 合并结果后统一排序

#### Scenario: Document source retrieval
- **WHEN** 检索源包含 documents
- **THEN** 系统调用 RAG-Fusion 检索器检索相关文档 chunks
- **AND** 文档检索结果与记忆检索结果统一融合

---

### Requirement: 多路召回策略

系统SHALL实现多路并行召回以提升召回率。

#### Scenario: 向量检索路径
- **WHEN** 执行向量召回
- **THEN** 系统将query转换为embedding
- **AND** 在Milvus中执行COSINE相似度搜索
- **AND** 返回top_k个结果（默认20）

#### Scenario: 关键词检索路径
- **WHEN** 执行关键词召回
- **THEN** 系统使用PostgreSQL全文检索（tsvector/tsquery）
- **AND** 返回匹配的记忆（默认10条）

#### Scenario: 时序检索路径
- **WHEN** 执行时序召回
- **THEN** 系统查询最近访问的记忆
- **AND** 按last_accessed降序
- **AND** 返回最近7天内访问过的记忆（默认5条）

#### Scenario: 稀疏向量检索路径
- **WHEN** 执行稀疏向量召回
- **THEN** 系统使用 BGE-M3 稀疏向量在 Milvus 中检索
- **AND** 返回 top_k 个结果

#### Scenario: 并行召回执行
- **WHEN** 执行检索
- **THEN** 系统并行执行所有召回路径
- **AND** 等待所有路径完成后合并结果

---

### Requirement: Cross-Encoder重排序

系统SHALL使用Cross-Encoder对召回结果精排。

#### Scenario: 精排执行
- **WHEN** 召回结果超过精排阈值（默认5条）
- **THEN** 系统使用Cross-Encoder计算query与每条记忆的相关性
- **AND** 默认模型：**bge-reranker-v2-m3**（替换原 ms-marco-MiniLM）

#### Scenario: 精排候选限制
- **WHEN** 召回结果数超过max_rerank_candidates（默认30）
- **THEN** 系统仅对前30条执行精排
- **AND** 其余直接丢弃

#### Scenario: 最终排序
- **WHEN** 精排完成
- **THEN** 系统综合相关性分数和记忆重要性排序
- **AND** 公式：final_score = 0.7 * relevance + 0.3 * importance

#### Scenario: 精排可配置
- **WHEN** 配置关闭精排（enable_rerank=false）
- **THEN** 系统跳过Cross-Encoder步骤
- **AND** 直接使用召回分数排序

---

## ADDED Requirements

### Requirement: RRF score fusion support

系统SHALL支持使用 RRF 算法融合多路检索结果。

#### Scenario: Enable RRF fusion
- **WHEN** 配置 use_rrf=true
- **THEN** 系统使用 RRF 公式计算融合分数：score = Σ 1/(k + rank_i)

#### Scenario: RRF constant parameter
- **WHEN** 使用 RRF 融合
- **THEN** 系统使用可配置的 k 常数（默认60）

#### Scenario: Fallback to weighted fusion
- **WHEN** 配置 use_rrf=false
- **THEN** 系统使用原有的加权分数融合

### Requirement: Document-Memory unified retrieval

系统SHALL支持文档和记忆的统一检索。

#### Scenario: Mixed retrieval mode
- **WHEN** 检索源同时包含 long_term 和 documents
- **THEN** 系统分别执行记忆检索和文档检索
- **AND** 使用 RRF 统一融合两类结果

#### Scenario: Result type distinction
- **WHEN** 返回统一检索结果
- **THEN** 每条结果标注 source_type：memory 或 document
- **AND** 文档结果额外包含 document_id 和 chunk_id

#### Scenario: Document priority weighting
- **WHEN** 配置 document_weight 参数
- **THEN** 系统调整文档结果在最终排序中的权重
- **AND** 默认权重 1.0（与记忆等权）
