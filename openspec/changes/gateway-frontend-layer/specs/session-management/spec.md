## MODIFIED Requirements

### Requirement: Session创建与标识

系统 SHALL 为每个用户会话创建唯一 Session，并关联用户 ID。

#### Scenario: 新Session创建
- **WHEN** 已认证用户首次发起请求且未携带 session_id
- **THEN** 系统生成唯一 session_id（格式：sess_{uuid}）
- **AND** 在 Redis 中创建 session 元数据
- **AND** 关联 session 与当前用户的 user_id
- **AND** 返回 session_id 给客户端

#### Scenario: 已有Session识别
- **WHEN** 用户请求携带有效 session_id
- **THEN** 系统验证 session 属于当前用户
- **AND** 加载该 Session 的状态
- **AND** 更新 last_active 时间戳

#### Scenario: 无效Session处理
- **WHEN** 用户请求携带的 session_id 不存在或已过期
- **THEN** 系统创建新 Session
- **AND** 返回新的 session_id

#### Scenario: Session归属验证
- **WHEN** 用户请求访问不属于自己的 session_id
- **THEN** 系统 SHALL 返回 403 Forbidden
- **AND** 不加载该 Session 数据

---

### Requirement: Session查询API

系统 SHALL 提供 Session 状态查询接口，限制用户只能查询自己的会话。

#### Scenario: 获取Session信息
- **WHEN** GET 请求到达 `/api/v1/sessions/{session_id}`
- **THEN** 系统验证 session 属于请求用户
- **AND** 返回 Session 元数据
- **AND** 包含 id、status、created_at、last_active、message_count

#### Scenario: 获取对话历史
- **WHEN** GET 请求到达 `/api/v1/sessions/{session_id}/history`
- **THEN** 系统验证 session 属于请求用户
- **AND** 返回对话历史列表
- **AND** 支持分页参数（limit、offset）

#### Scenario: 列出用户会话
- **WHEN** GET 请求到达 `/api/v1/sessions`
- **THEN** 系统返回当前用户的所有会话列表
- **AND** 按最后活跃时间倒序排列
- **AND** 支持分页参数

#### Scenario: 恢复挂起任务
- **WHEN** POST 请求到达 `/api/v1/sessions/{session_id}/resume`
- **THEN** 系统验证 session 属于请求用户
- **AND** 检查是否有未完成任务
- **AND** 返回恢复信息或提示无待恢复任务

---

## ADDED Requirements

### Requirement: Session关联用户

系统 SHALL 支持 Session 与用户 ID 的关联管理。

#### Scenario: 用户会话索引
- **WHEN** 创建新 Session
- **THEN** 系统 SHALL 将 session_id 添加到 `user:{user_id}:sessions` 集合

#### Scenario: 用户会话统计
- **WHEN** 查询用户会话列表
- **THEN** 系统 SHALL 返回该用户的会话总数

#### Scenario: 删除会话时更新索引
- **WHEN** Session 被删除（过期或手动删除）
- **THEN** 系统 SHALL 从 `user:{user_id}:sessions` 集合中移除该 session_id

---

### Requirement: Session从网关获取用户身份

系统 SHALL 从网关注入的请求头中获取用户身份。

#### Scenario: 从Header获取用户ID
- **WHEN** 请求包含 `X-User-ID` 头
- **THEN** 系统 SHALL 使用该值作为当前用户 ID
- **AND** 不依赖其他认证机制

#### Scenario: 缺少用户ID头
- **WHEN** 请求不包含 `X-User-ID` 头
- **THEN** 系统 SHALL 返回 401 Unauthorized
- **AND** 不创建或访问任何 Session
