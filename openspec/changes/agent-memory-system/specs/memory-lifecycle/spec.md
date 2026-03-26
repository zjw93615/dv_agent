# Spec: memory-lifecycle

记忆生命周期管理，提取/更新/遗忘机制。

## ADDED Requirements

### Requirement: 记忆自动提取

系统SHALL在对话结束后自动提取值得记忆的信息。

#### Scenario: 提取触发时机
- **WHEN** Agent返回最终响应后
- **THEN** 系统触发记忆提取流程
- **AND** 提取在后台异步执行，不阻塞响应

#### Scenario: 最小对话阈值
- **WHEN** 对话轮数少于配置阈值（默认3轮）
- **THEN** 系统跳过提取
- **AND** 避免短对话产生低质量记忆

#### Scenario: 提取Prompt调用
- **WHEN** 执行提取
- **THEN** 系统调用LLM（默认gpt-4o-mini）分析对话
- **AND** 返回结构化的记忆列表

#### Scenario: 提取结果格式
- **WHEN** LLM返回提取结果
- **THEN** 每条记忆包含：type, content, confidence, tags
- **AND** type为fact/preference/event/entity之一

#### Scenario: 提取结果存储
- **WHEN** 提取完成
- **THEN** 系统将记忆写入长期存储
- **AND** 关联source_session和source_turn

---

### Requirement: 记忆去重

系统SHALL避免存储重复或高度相似的记忆。

#### Scenario: 相似度检测
- **WHEN** 保存新记忆前
- **THEN** 系统检索该用户的相似记忆
- **AND** 使用向量相似度，阈值0.95

#### Scenario: 重复合并
- **WHEN** 发现高度相似的现有记忆
- **THEN** 系统更新现有记忆而非创建新记忆
- **AND** 提升现有记忆的confidence

#### Scenario: 冲突检测
- **WHEN** 发现内容矛盾的记忆
- **THEN** 系统保留新记忆
- **AND** 降低旧记忆的importance
- **AND** 在metadata中标记关系为"contradicts"

---

### Requirement: 记忆权重更新

系统SHALL基于交互频率动态调整记忆权重。

#### Scenario: 访问计数增加
- **WHEN** 记忆在检索结果中被返回
- **THEN** 系统增加该记忆的access_count
- **AND** 更新last_accessed时间戳

#### Scenario: 重要性重算
- **WHEN** 执行定期权重更新任务（每天凌晨）
- **THEN** 系统重新计算所有活跃记忆的importance
- **AND** 公式：importance = base × recency × access_factor × confidence

#### Scenario: 时间衰减
- **WHEN** 计算recency_factor
- **THEN** recency = e^(-decay_rate × days_since_created)
- **AND** 默认decay_rate=0.01

#### Scenario: 访问加成
- **WHEN** 计算access_factor
- **THEN** access_factor = 1 + log(1 + access_count) × 0.1
- **AND** 高访问记忆获得更高权重

---

### Requirement: 智能遗忘机制

系统SHALL实现三级渐进遗忘策略。

#### Scenario: 软遗忘触发
- **WHEN** 记忆importance低于soft_threshold（默认0.1）
- **THEN** 系统设置expired_at = NOW() + 30 days
- **AND** 记忆不再参与常规检索

#### Scenario: 遗忘豁免
- **WHEN** 记忆满足豁免条件
- **THEN** 系统不执行遗忘
- **AND** 豁免条件：type=entity且access_count>10，或被用户标记为permanent

#### Scenario: 归档执行
- **WHEN** 软遗忘30天后仍无访问
- **THEN** 系统将记忆移动到archive表
- **AND** 从Milvus删除向量

#### Scenario: 硬删除执行
- **WHEN** 归档180天后
- **THEN** 系统从archive表删除记录
- **AND** 符合数据保留政策

#### Scenario: 遗忘恢复
- **WHEN** 软遗忘的记忆被精确查询访问
- **THEN** 系统清除expired_at
- **AND** 重新计算importance

---

### Requirement: 后台任务调度

系统SHALL提供后台Worker执行生命周期任务。

#### Scenario: 权重更新任务
- **WHEN** 定时任务触发（每天02:00）
- **THEN** Worker批量更新所有活跃记忆的importance
- **AND** 分批处理，每批1000条

#### Scenario: 软遗忘扫描
- **WHEN** 定时任务触发（每天03:00）
- **THEN** Worker扫描importance低于阈值的记忆
- **AND** 执行软遗忘标记

#### Scenario: 归档执行任务
- **WHEN** 定时任务触发（每周日04:00）
- **THEN** Worker处理软遗忘超过30天的记忆
- **AND** 执行归档操作

#### Scenario: 一致性检查任务
- **WHEN** 定时任务触发（每周日05:00）
- **THEN** Worker对比PG和Milvus数据
- **AND** 报告并可选修复不一致

---

### Requirement: 记忆关系管理

系统SHALL支持记忆之间的关系存储。

#### Scenario: 关系创建
- **WHEN** 检测到记忆间存在关联
- **THEN** 系统在memory_relations表创建记录
- **AND** 包含source_id, target_id, relation_type, strength

#### Scenario: 关系类型
- **WHEN** 创建关系
- **THEN** relation_type为以下之一：related, contradicts, supersedes
- **AND** strength为0-1的浮点数

#### Scenario: 级联影响
- **WHEN** 删除一条记忆
- **THEN** 系统同时删除其所有关系记录
- **AND** 更新被关联记忆的metadata

---

### Requirement: 记忆手动管理

系统SHALL支持用户手动管理记忆。

#### Scenario: 标记永久保留
- **WHEN** 用户标记记忆为permanent
- **THEN** 系统在metadata中设置permanent=true
- **AND** 该记忆免于自动遗忘

#### Scenario: 手动删除
- **WHEN** 用户请求删除记忆
- **THEN** 系统执行硬删除
- **AND** 同时删除PG和Milvus中的数据

#### Scenario: 记忆编辑
- **WHEN** 用户编辑记忆内容
- **THEN** 系统更新content字段
- **AND** 重新生成embedding
