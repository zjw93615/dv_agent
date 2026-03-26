# Spec: memory-retrieval

统一记忆检索，多路召回 + Cross-Encoder 重排序。

## ADDED Requirements

### Requirement: 统一检索接口

系统SHALL提供统一的记忆检索接口，支持多种记忆源。

#### Scenario: 基本检索调用
- **WHEN** 调用 retrieve(query, user_id, top_k)
- **THEN** 系统返回按相关性排序的记忆列表
- **AND** 每条记忆包含 content, score, source, memory_type

#### Scenario: 记忆源配置
- **WHEN** 调用检索时指定 sources 参数
- **THEN** 系统仅从指定的源检索
- **AND** 可选源包括：short_term, long_term, shared_knowledge

#### Scenario: 默认检索全部源
- **WHEN** 调用检索时未指定 sources
- **THEN** 系统从所有可用源检索
- **AND** 合并结果后统一排序

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

#### Scenario: 并行召回执行
- **WHEN** 执行检索
- **THEN** 系统并行执行所有召回路径
- **AND** 等待所有路径完成后合并结果

---

### Requirement: 结果合并与去重

系统SHALL合并多路召回结果并去重。

#### Scenario: ID去重
- **WHEN** 多路召回返回重复的记忆ID
- **THEN** 系统保留分数最高的那条
- **AND** 去重后结果数通常为30-40条

#### Scenario: 分数归一化
- **WHEN** 合并不同来源的结果
- **THEN** 系统将各路径分数归一化到0-1范围
- **AND** 向量相似度直接使用，关键词和时序分数需转换

---

### Requirement: Cross-Encoder重排序

系统SHALL使用Cross-Encoder对召回结果精排。

#### Scenario: 精排执行
- **WHEN** 召回结果超过精排阈值（默认5条）
- **THEN** 系统使用Cross-Encoder计算query与每条记忆的相关性
- **AND** 默认模型：cross-encoder/ms-marco-MiniLM-L-6-v2

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

### Requirement: 检索结果返回

系统SHALL返回结构化的检索结果。

#### Scenario: 结果格式
- **WHEN** 检索完成
- **THEN** 系统返回top_k条记忆（默认10）
- **AND** 每条包含：id, content, score, memory_type, source, metadata

#### Scenario: 空结果处理
- **WHEN** 没有找到相关记忆
- **THEN** 系统返回空列表
- **AND** 不抛出异常

#### Scenario: 访问计数更新
- **WHEN** 返回检索结果
- **THEN** 系统异步更新结果记忆的access_count
- **AND** 更新last_accessed时间戳

---

### Requirement: 检索缓存

系统SHALL缓存高频检索结果。

#### Scenario: 缓存命中
- **WHEN** 相同query和user_id在缓存有效期内再次检索
- **THEN** 系统直接返回缓存结果
- **AND** 缓存key：cache:memory:{user_id}:{query_hash}

#### Scenario: 缓存失效
- **WHEN** 用户记忆发生更新
- **THEN** 系统清除该用户的检索缓存
- **AND** 下次检索重新执行

#### Scenario: 缓存TTL
- **WHEN** 缓存写入
- **THEN** 设置TTL为5分钟
- **AND** 5分钟后自动过期

---

### Requirement: Query扩展

系统SHALL支持检索前的Query扩展。

#### Scenario: 关键词提取
- **WHEN** 执行检索
- **THEN** 系统从query中提取关键词
- **AND** 用于关键词检索路径

#### Scenario: 同义词扩展（可选）
- **WHEN** 配置启用同义词扩展
- **THEN** 系统扩展query中的关键词
- **AND** 提升召回覆盖面
