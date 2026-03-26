# Spec: a2a-protocol

Agent间A2A通信协议，包括Agent Card、Invoke、Status等标准接口。

## ADDED Requirements

### Requirement: Agent Card服务发现

系统SHALL为每个Agent提供Agent Card端点，支持服务发现。

#### Scenario: 获取Agent Card
- **WHEN** GET请求到达`/a2a/{agent_id}/card`
- **THEN** 返回Agent Card JSON，包含agent_id、name、description、capabilities、endpoints
- **AND** HTTP状态码为200

#### Scenario: Agent不存在
- **WHEN** 请求的agent_id不存在
- **THEN** 返回HTTP 404
- **AND** 错误信息包含"Agent not found"

---

### Requirement: A2A消息格式标准化

系统SHALL定义统一的A2A请求/响应消息格式。

#### Scenario: Invoke请求格式
- **WHEN** Orchestrator发起A2A调用
- **THEN** 请求体包含：protocol_version、task_id、session_id、capability、payload、context_ref、metadata
- **AND** metadata包含timeout_ms、priority、trace_id

#### Scenario: 成功响应格式
- **WHEN** Worker Agent执行成功
- **THEN** 响应体包含：status="success"、task_id、result、context_updates
- **AND** HTTP状态码为200

#### Scenario: 失败响应格式
- **WHEN** Worker Agent执行失败
- **THEN** 响应体包含：status="error"、task_id、error_code、error_message
- **AND** HTTP状态码为对应错误码（400/500等）

---

### Requirement: A2A Invoke调用

系统SHALL提供统一的Invoke端点处理Agent调用请求。

#### Scenario: 同步Invoke成功
- **WHEN** POST请求到达`/a2a/invoke`并携带有效payload
- **THEN** Agent执行对应capability
- **AND** 在timeout_ms内返回结果
- **AND** 更新共享上下文（如有context_updates）

#### Scenario: Invoke超时
- **WHEN** Agent执行超过timeout_ms
- **THEN** 返回HTTP 408 Request Timeout
- **AND** error_code为"TIMEOUT"

#### Scenario: Capability不支持
- **WHEN** 请求的capability不在Agent的capabilities列表中
- **THEN** 返回HTTP 400 Bad Request
- **AND** error_code为"UNSUPPORTED_CAPABILITY"

---

### Requirement: 共享上下文传递

系统SHALL支持通过context_ref在Agent间共享上下文。

#### Scenario: 读取共享上下文
- **WHEN** Invoke请求包含context_ref
- **THEN** Worker Agent从Redis读取指定key的上下文数据
- **AND** 将上下文注入到执行环境

#### Scenario: 写回上下文更新
- **WHEN** Worker Agent执行完成并产生context_updates
- **THEN** 系统将updates写回Redis对应key
- **AND** 在响应中返回context_updates摘要

---

### Requirement: 请求幂等性

系统SHALL基于task_id保证请求幂等性。

#### Scenario: 重复task_id请求
- **WHEN** 收到相同task_id的重复请求
- **THEN** 直接返回缓存的执行结果
- **AND** 不重复执行capability

#### Scenario: task_id缓存过期
- **WHEN** task_id对应的缓存已过期（默认1小时）
- **THEN** 作为新请求处理
- **AND** 重新执行capability