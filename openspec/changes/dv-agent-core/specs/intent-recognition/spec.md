# Spec: intent-recognition

独立意图识别服务，三层识别架构（规则+Embedding+LLM），Redis缓存。

## ADDED Requirements

### Requirement: 规则层意图匹配

系统SHALL提供基于关键词和正则表达式的快速意图匹配。

#### Scenario: 关键词命中
- **WHEN** 用户输入包含配置的关键词（如"帮我搜索"）
- **THEN** 直接返回对应intent（如"web_search"）
- **AND** confidence为1.0
- **AND** 延迟小于10ms

#### Scenario: 正则表达式匹配
- **WHEN** 用户输入匹配配置的正则模式
- **THEN** 返回对应intent和提取的slot参数
- **AND** 延迟小于10ms

#### Scenario: 规则层未命中
- **WHEN** 用户输入不匹配任何规则
- **THEN** 继续传递到下一层（缓存层）

---

### Requirement: Redis缓存层

系统SHALL缓存已识别的意图结果，减少重复计算。

#### Scenario: 缓存命中
- **WHEN** 用户输入与缓存中的query完全匹配
- **THEN** 直接返回缓存的intent结果
- **AND** 延迟小于5ms

#### Scenario: 缓存未命中
- **WHEN** 用户输入在缓存中不存在
- **THEN** 继续传递到Embedding层

#### Scenario: 识别结果写入缓存
- **WHEN** LLM层完成意图识别
- **THEN** 将query和识别结果写入Redis缓存
- **AND** 设置TTL为24小时

---

### Requirement: Embedding语义匹配层

系统SHALL基于向量相似度进行语义意图匹配。

#### Scenario: 高相似度命中
- **WHEN** 用户输入与意图库中某query的相似度超过0.9
- **THEN** 返回该query对应的intent
- **AND** confidence为相似度分数

#### Scenario: 相似度不足
- **WHEN** 最高相似度低于0.7
- **THEN** 继续传递到LLM层

#### Scenario: 中等相似度需确认
- **WHEN** 最高相似度在0.7-0.9之间
- **THEN** 返回intent并标记need_clarification=true

---

### Requirement: LLM分析层

系统SHALL使用LLM进行复杂意图识别和槽位提取。

#### Scenario: LLM意图识别
- **WHEN** 前置层都未能识别意图
- **THEN** 调用LLM进行Few-shot意图识别
- **AND** 返回intent、slots、confidence、reasoning

#### Scenario: 歧义意图处理
- **WHEN** LLM识别出多个可能意图
- **THEN** 返回最高置信度intent
- **AND** alternatives字段包含其他候选intent

#### Scenario: 意图无法识别
- **WHEN** LLM无法确定用户意图
- **THEN** 返回intent="unknown"
- **AND** need_clarification=true
- **AND** clarification_question包含澄清问题

---

### Requirement: 意图识别API

系统SHALL提供RESTful意图识别接口。

#### Scenario: 意图识别请求
- **WHEN** POST请求到达`/intent/recognize`
- **THEN** 执行三层意图识别流程
- **AND** 返回结构化意图结果

#### Scenario: 返回格式
- **WHEN** 意图识别成功
- **THEN** 响应包含：intent、confidence、slots、target_agents、need_clarification

---

### Requirement: 意图类型定义

系统SHALL预定义一组标准意图类型。

#### Scenario: 支持的意图类型
- **WHEN** 进行意图识别
- **THEN** 识别结果为以下类型之一：general_qa、knowledge_query、web_search、code_gen、code_explain、task_plan、unknown

#### Scenario: 意图到Agent映射
- **WHEN** 意图识别完成
- **THEN** target_agents字段包含推荐的Agent列表
- **AND** 映射关系：general_qa→Q&A Agent，knowledge_query→Knowledge Agent，web_search→Search Agent