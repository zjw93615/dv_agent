# Spec: session-management

扩展 Session 模型以关联短期记忆，新增 summary 字段和滑动窗口配置。

## MODIFIED Requirements

### Requirement: 对话历史存储

系统SHALL持久化存储会话的对话历史，并支持滑动窗口和摘要压缩。

#### Scenario: 消息追加
- **WHEN** 用户发送消息或Agent返回响应
- **THEN** 系统将消息追加到history:{session_id}列表
- **AND** 消息包含role、content、timestamp、token_count字段

#### Scenario: 历史读取
- **WHEN** Agent需要获取对话上下文
- **THEN** 系统返回滑动窗口内的消息（默认最近20条）
- **AND** 如存在摘要，将摘要作为上下文前缀
- **AND** 按时间顺序排列

#### Scenario: 历史滑动窗口
- **WHEN** 对话历史超过配置的窗口大小
- **THEN** 系统自动裁剪超出的旧消息
- **AND** 触发历史摘要生成
- **AND** 摘要存储到stm:summary:{session_id}

#### Scenario: Token限制检查
- **WHEN** 窗口内消息总Token数超过token_limit
- **THEN** 系统提前触发压缩流程
- **AND** 确保上下文不超过LLM限制

---

### Requirement: Session生命周期管理

系统SHALL管理Session的完整生命周期，包括记忆关联。

#### Scenario: Session挂起
- **WHEN** 用户长时间无交互（超过30分钟）
- **THEN** 系统将Session状态标记为"suspended"
- **AND** 保留所有状态数据
- **AND** 触发记忆提取流程

#### Scenario: Session恢复
- **WHEN** 用户在suspended状态的Session上发起请求
- **THEN** 系统将状态更新为"active"
- **AND** 恢复上下文继续执行
- **AND** 加载该用户的相关长期记忆

#### Scenario: Session过期清理
- **WHEN** Session超过TTL（默认24小时）无活动
- **THEN** 系统自动删除Session及关联数据
- **AND** 清理history、context、stm:window、stm:summary等所有相关key
- **AND** 长期记忆不受影响

#### Scenario: 主动关闭Session
- **WHEN** 用户请求关闭Session
- **THEN** 系统将状态标记为"closed"
- **AND** 触发最终记忆提取
- **AND** 保留数据直到TTL过期（用于审计）

## ADDED Requirements

### Requirement: Session记忆配置

系统SHALL支持Session级别的记忆配置。

#### Scenario: 创建Session时配置记忆
- **WHEN** 创建Session时指定memory_config参数
- **THEN** 系统保存配置到Session元数据
- **AND** 配置包含：window_size, token_limit, enable_extraction, enable_long_term

#### Scenario: 默认记忆配置
- **WHEN** 创建Session未指定memory_config
- **THEN** 系统应用全局默认配置
- **AND** 默认启用短期记忆，启用提取，启用长期记忆关联

#### Scenario: 禁用记忆功能
- **WHEN** 配置enable_long_term=false
- **THEN** 系统不为该Session执行记忆提取
- **AND** 不关联长期记忆到上下文

---

### Requirement: Session摘要查询

系统SHALL提供Session摘要查询能力。

#### Scenario: 获取Session摘要
- **WHEN** GET请求到达`/api/v1/session/{session_id}/summary`
- **THEN** 返回该Session的压缩摘要
- **AND** 包含摘要内容、生成时间、Token数

#### Scenario: 无摘要时的响应
- **WHEN** Session尚未生成摘要
- **THEN** 返回空摘要
- **AND** 附带状态说明"no_summary_yet"
