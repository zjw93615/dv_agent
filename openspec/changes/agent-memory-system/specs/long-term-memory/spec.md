# Spec: long-term-memory

长期记忆存储，PostgreSQL + Milvus 联动，支持私有记忆与共享知识。

## ADDED Requirements

### Requirement: 长期记忆数据模型

系统SHALL定义结构化的长期记忆数据模型。

#### Scenario: 记忆实体创建
- **WHEN** 创建新的长期记忆
- **THEN** 系统生成唯一ID（UUID格式）
- **AND** 记忆包含必填字段：id, user_id, memory_type, content, created_at
- **AND** 记忆包含可选字段：confidence, importance, access_count, metadata

#### Scenario: 记忆类型分类
- **WHEN** 存储记忆时
- **THEN** memory_type SHALL为以下之一：fact, preference, event, entity
- **AND** 不同类型有不同的默认 importance 权重

#### Scenario: 记忆元数据存储
- **WHEN** 记忆附带额外信息
- **THEN** 系统将其存储在 metadata JSONB 字段
- **AND** 支持 source_session, source_turn, tags 等扩展字段

---

### Requirement: PostgreSQL结构化存储

系统SHALL使用PostgreSQL存储记忆的结构化元数据。

#### Scenario: 记忆写入PG
- **WHEN** 保存新记忆
- **THEN** 系统INSERT到user_memories表
- **AND** 返回生成的ID

#### Scenario: 记忆查询
- **WHEN** 按条件查询记忆
- **THEN** 系统支持按user_id, memory_type, importance等字段过滤
- **AND** 支持分页（limit, offset）

#### Scenario: 记忆更新
- **WHEN** 更新记忆字段（如access_count, importance）
- **THEN** 系统执行UPDATE并更新updated_at时间戳

#### Scenario: 记忆软删除
- **WHEN** 标记记忆为软删除
- **THEN** 系统设置expired_at字段
- **AND** 软删除的记忆不参与常规查询

---

### Requirement: Milvus向量存储

系统SHALL使用Milvus存储记忆的向量表示。

#### Scenario: 向量写入
- **WHEN** 保存记忆的向量
- **THEN** 系统INSERT到user_memory_vectors Collection
- **AND** 使用与PG相同的ID作为主键
- **AND** 按user_id进行分区

#### Scenario: 向量检索
- **WHEN** 执行向量相似度搜索
- **THEN** 系统使用COSINE相似度
- **AND** 支持分区过滤（按user_id）
- **AND** 返回top_k个最相似结果

#### Scenario: 向量删除
- **WHEN** 删除记忆
- **THEN** 系统同时删除Milvus中的向量记录

---

### Requirement: PG与Milvus数据同步

系统SHALL保证PostgreSQL与Milvus数据一致性。

#### Scenario: 写入同步
- **WHEN** 创建新记忆
- **THEN** 系统在PG事务中完成PG写入
- **AND** 在事务提交前完成Milvus写入
- **AND** 任一失败则回滚整个操作

#### Scenario: 删除同步
- **WHEN** 删除记忆
- **THEN** 系统同时从PG和Milvus删除
- **AND** PG删除成功后再删除Milvus

#### Scenario: 一致性检查
- **WHEN** 执行一致性检查任务
- **THEN** 系统对比PG和Milvus的ID集合
- **AND** 报告不一致的记录
- **AND** 可选自动修复（以PG为准）

---

### Requirement: 私有记忆与共享知识分层

系统SHALL区分用户私有记忆和企业共享知识。

#### Scenario: 私有记忆存储
- **WHEN** 存储用户私有记忆
- **THEN** 系统在user_memories表中存储，关联user_id
- **AND** 在Milvus中使用user_{user_id}分区

#### Scenario: 共享知识存储
- **WHEN** 存储企业共享知识
- **THEN** 系统在enterprise_knowledge表中存储
- **AND** 在Milvus中使用enterprise_knowledge Collection
- **AND** 所有用户可访问

#### Scenario: 部门级知识
- **WHEN** 存储部门级知识
- **THEN** 系统关联dept_id字段
- **AND** 在Milvus中使用dept_{dept_id}分区
- **AND** 仅部门成员可访问

---

### Requirement: Embedding生成

系统SHALL为记忆内容生成向量表示。

#### Scenario: 文本Embedding
- **WHEN** 保存新记忆
- **THEN** 系统使用配置的Embedding模型生成向量
- **AND** 默认使用sentence-transformers/all-MiniLM-L6-v2（384维）

#### Scenario: 批量Embedding
- **WHEN** 批量导入记忆
- **THEN** 系统支持批量生成Embedding
- **AND** 批大小可配置（默认32）

#### Scenario: Embedding缓存
- **WHEN** 相同文本多次请求Embedding
- **THEN** 系统从缓存返回（cache:embed:{text_hash}）
- **AND** 缓存TTL为24小时
