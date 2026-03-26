## ADDED Requirements

### Requirement: System SHALL establish WebSocket connection with authentication

系统 SHALL 支持建立经过身份验证的 WebSocket 连接。

#### Scenario: 成功建立连接
- **WHEN** 客户端携带有效 JWT Token 请求 `/ws`
- **THEN** 系统 SHALL 升级连接为 WebSocket
- **AND** 关联连接与用户 ID

#### Scenario: 无效 Token 拒绝连接
- **WHEN** 客户端携带无效或过期 Token 请求 `/ws`
- **THEN** 系统 SHALL 返回 401 并拒绝升级

#### Scenario: 连接关联会话
- **WHEN** 连接建立后客户端发送订阅消息
- **THEN** 系统 SHALL 允许客户端订阅特定会话的事件

---

### Requirement: System SHALL manage connection lifecycle

系统 SHALL 管理 WebSocket 连接的完整生命周期。

**心跳配置**:
- 心跳间隔: 30 秒
- 超时时间: 60 秒

#### Scenario: 心跳保活
- **WHEN** 客户端每 30 秒发送 `ping` 消息
- **THEN** 服务器 SHALL 响应 `pong` 消息
- **AND** 重置连接超时计时器

#### Scenario: 超时断开
- **WHEN** 连接超过 60 秒未收到任何消息
- **THEN** 服务器 SHALL 关闭连接

#### Scenario: 客户端断开
- **WHEN** 客户端主动关闭连接
- **THEN** 服务器 SHALL 清理连接资源
- **AND** 取消所有该连接的订阅

#### Scenario: 连接数限制
- **WHEN** 单个用户的连接数超过 100
- **THEN** 系统 SHALL 拒绝新连接
- **AND** 返回错误消息 "Too many connections"

---

### Requirement: System SHALL push Agent execution status

系统 SHALL 通过 WebSocket 推送 Agent 执行状态更新。

**事件类型**:
| 事件 | 数据 | 描述 |
|------|------|------|
| `agent.thinking` | step, thought | Agent 正在思考 |
| `agent.tool_call` | tool, input | 调用工具 |
| `agent.tool_result` | tool, result | 工具返回结果 |
| `agent.response` | content, done | 流式响应内容 |
| `agent.error` | error | 执行错误 |

#### Scenario: 推送思考状态
- **WHEN** Agent 开始新的思考步骤
- **THEN** 系统 SHALL 推送 `agent.thinking` 事件
- **AND** 包含步骤编号和思考内容

#### Scenario: 推送工具调用
- **WHEN** Agent 调用工具
- **THEN** 系统 SHALL 推送 `agent.tool_call` 事件
- **AND** 包含工具名称和输入参数

#### Scenario: 推送工具结果
- **WHEN** 工具执行完成
- **THEN** 系统 SHALL 推送 `agent.tool_result` 事件
- **AND** 包含工具名称和执行结果

#### Scenario: 推送流式响应
- **WHEN** Agent 生成响应内容
- **THEN** 系统 SHALL 推送 `agent.response` 事件
- **AND** 逐块发送内容
- **AND** 最后一块包含 `done: true`

#### Scenario: 推送错误状态
- **WHEN** Agent 执行过程中发生错误
- **THEN** 系统 SHALL 推送 `agent.error` 事件
- **AND** 包含错误信息

---

### Requirement: System SHALL push document processing status

系统 SHALL 通过 WebSocket 推送文档处理进度。

**事件类型**:
| 事件 | 数据 | 描述 |
|------|------|------|
| `document.queued` | doc_id | 文档已入队 |
| `document.processing` | doc_id, stage, progress | 处理中 |
| `document.completed` | doc_id, chunk_count | 处理完成 |
| `document.failed` | doc_id, error | 处理失败 |

#### Scenario: 推送处理进度
- **WHEN** 文档处理进入新阶段
- **THEN** 系统 SHALL 推送 `document.processing` 事件
- **AND** 包含当前阶段（提取/分块/向量化/索引）和进度百分比

#### Scenario: 推送处理完成
- **WHEN** 文档处理成功完成
- **THEN** 系统 SHALL 推送 `document.completed` 事件
- **AND** 包含分块数量

#### Scenario: 推送处理失败
- **WHEN** 文档处理失败
- **THEN** 系统 SHALL 推送 `document.failed` 事件
- **AND** 包含错误信息

---

### Requirement: System SHALL support reconnection

系统 SHALL 支持客户端断线重连。

#### Scenario: 重连恢复订阅
- **WHEN** 客户端重新连接并发送之前的订阅列表
- **THEN** 系统 SHALL 恢复所有订阅
- **AND** 推送断线期间错过的关键事件（如有缓存）

#### Scenario: 重连不重复消息
- **WHEN** 客户端重连
- **THEN** 已确认收到的消息 SHALL NOT 重复推送

---

### Requirement: Message format SHALL be JSON

所有 WebSocket 消息 SHALL 使用 JSON 格式。

**消息结构**:
```json
{
  "type": "<event_type>",
  "sessionId": "<session_id>",
  "timestamp": <unix_timestamp_ms>,
  "data": { ... }
}
```

#### Scenario: 消息格式正确
- **WHEN** 服务器推送消息
- **THEN** 消息 SHALL 为有效 JSON
- **AND** 包含 type、timestamp 字段
- **AND** sessionId 在会话相关事件中必须存在

#### Scenario: 无效消息被忽略
- **WHEN** 客户端发送无效 JSON
- **THEN** 服务器 SHALL 忽略该消息
- **AND** 可选地发送错误通知
