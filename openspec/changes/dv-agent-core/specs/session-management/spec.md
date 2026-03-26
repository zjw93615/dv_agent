# Spec: session-management

Session状态持久化与恢复，包括对话历史、Agent上下文、ReAct状态。

## ADDED Requirements

### Requirement: Session创建与标识

系统SHALL为每个用户会话创建唯一Session。

#### Scenario: 新Session创建
- **WHEN** 用户首次发起请求且未携带session_id
- **THEN** 系统生成唯一session_id（格式：sess_{uuid}）
- **AND** 在Redis中创建session元数据
- **AND** 返回session_id给客户端

#### Scenario: 已有Session识别
- **WHEN** 用户请求携带有效session_id
- **THEN** 系统加载该Session的状态
- **AND** 更新last_active时间戳

#### Scenario: 无效Session处理
- **WHEN** 用户请求携带的session_id不存在或已过期
- **THEN** 系统创建新Session
- **AND** 返回新的session_id

---

### Requirement: 对话历史存储

系统SHALL持久化存储会话的对话历史。

#### Scenario: 消息追加
- **WHEN** 用户发送消息或Agent返回响应
- **THEN** 系统将消息追加到history:{session_id}列表
- **AND** 消息包含role、content、timestamp字段

#### Scenario: 历史读取
- **WHEN** Agent需要获取对话上下文
- **THEN** 系统返回最近N条消息（默认20条）
- **AND** 按时间顺序排列

#### Scenario: 历史滑动窗口
- **WHEN** 对话历史超过配置的最大条数（默认100条）
- **THEN** 系统自动删除最旧的消息
- **AND** 可选触发历史摘要生成

---

### Requirement: Agent上下文存储

系统SHALL存储各Agent的执行上下文，支持断点恢复。

#### Scenario: 上下文保存
- **WHEN** Agent执行过程中更新状态
- **THEN** 系统将上下文写入context:{session_id}:{agent_id}
- **AND** 包含react_state、thought_chain、tool_results等字段

#### Scenario: 上下文读取
- **WHEN** Agent恢复执行
- **THEN** 系统读取该Agent的上下文
- **AND** Agent从断点继续执行

#### Scenario: 上下文清理
- **WHEN** Agent任务完成
- **THEN** 系统清理该Agent的临时上下文
- **AND** 保留最终结果到Session

---

### Requirement: ReAct状态持久化

系统SHALL保存ReAct决策循环的中间状态。

#### Scenario: 思考链保存
- **WHEN** ReAct循环执行Thought步骤
- **THEN** 系统将thought内容追加到thought_chain
- **AND** 更新react_state为"action"

#### Scenario: 工具结果保存
- **WHEN** ReAct循环执行Action并获得Observation
- **THEN** 系统将工具名称、参数、结果保存到tool_results
- **AND** 更新react_state为"observation"

#### Scenario: 循环状态恢复
- **WHEN** 用户中断后恢复Session
- **THEN** 系统检测到未完成的ReAct状态
- **AND** 询问用户是否继续上次任务

---

### Requirement: Session生命周期管理

系统SHALL管理Session的完整生命周期。

#### Scenario: Session挂起
- **WHEN** 用户长时间无交互（超过30分钟）
- **THEN** 系统将Session状态标记为"suspended"
- **AND** 保留所有状态数据

#### Scenario: Session恢复
- **WHEN** 用户在suspended状态的Session上发起请求
- **THEN** 系统将状态更新为"active"
- **AND** 恢复上下文继续执行

#### Scenario: Session过期清理
- **WHEN** Session超过TTL（默认24小时）无活动
- **THEN** 系统自动删除Session及关联数据
- **AND** 清理history、context等所有相关key

#### Scenario: 主动关闭Session
- **WHEN** 用户请求关闭Session
- **THEN** 系统将状态标记为"closed"
- **AND** 保留数据直到TTL过期（用于审计）

---

### Requirement: Session查询API

系统SHALL提供Session状态查询接口。

#### Scenario: 获取Session信息
- **WHEN** GET请求到达`/api/v1/session/{session_id}`
- **THEN** 返回Session元数据
- **AND** 包含id、status、created_at、last_active、message_count

#### Scenario: 获取对话历史
- **WHEN** GET请求到达`/api/v1/session/{session_id}/history`
- **THEN** 返回对话历史列表
- **AND** 支持分页参数（limit、offset）

#### Scenario: 恢复挂起任务
- **WHEN** POST请求到达`/api/v1/session/{session_id}/resume`
- **THEN** 检查是否有未完成任务
- **AND** 返回恢复信息或提示无待恢复任务