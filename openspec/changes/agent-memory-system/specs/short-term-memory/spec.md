# Spec: short-term-memory

短期记忆管理，包括滑动窗口、Token压缩、会话摘要。

## ADDED Requirements

### Requirement: 滑动窗口消息管理

系统SHALL实现基于滑动窗口的短期记忆管理，保持最近N条对话消息。

#### Scenario: 消息追加到窗口
- **WHEN** 新消息（用户或助手）产生
- **THEN** 系统将消息追加到窗口头部（LPUSH）
- **AND** 消息包含 role、content、timestamp、token_count 字段

#### Scenario: 窗口自动裁剪
- **WHEN** 窗口消息数超过配置的 window_size（默认20条）
- **THEN** 系统自动裁剪超出的旧消息（LTRIM）
- **AND** 被裁剪的消息触发压缩流程

#### Scenario: 窗口读取
- **WHEN** Agent 需要获取对话上下文
- **THEN** 系统返回窗口内所有消息（LRANGE）
- **AND** 按时间正序排列（最旧在前）

---

### Requirement: Token压缩与摘要生成

系统SHALL在对话历史超出Token限制时自动生成摘要。

#### Scenario: Token超限触发压缩
- **WHEN** 窗口内消息总Token数超过 token_limit（默认4000）
- **THEN** 系统调用LLM生成历史摘要
- **AND** 摘要存储到 stm:summary:{session_id}

#### Scenario: 摘要累积更新
- **WHEN** 新的消息被压缩
- **THEN** 系统将新摘要与现有摘要合并
- **AND** 合并后摘要不超过 max_summary_tokens（默认1000）

#### Scenario: 摘要纳入上下文
- **WHEN** Agent 构建 LLM 上下文时
- **THEN** 系统将摘要作为 system message 插入
- **AND** 摘要位于 system prompt 之后、窗口消息之前

---

### Requirement: 窗口配置管理

系统SHALL支持Session级别的窗口配置。

#### Scenario: 默认配置应用
- **WHEN** 新Session创建时未指定窗口配置
- **THEN** 系统应用全局默认配置
- **AND** 默认配置包含 window_size=20, token_limit=4000, compress_model="gpt-4o-mini"

#### Scenario: 自定义配置
- **WHEN** Session创建时指定窗口配置
- **THEN** 系统保存配置到 stm:config:{session_id}
- **AND** 后续操作使用自定义配置

#### Scenario: 配置动态更新
- **WHEN** 调用配置更新接口
- **THEN** 系统更新 stm:config:{session_id}
- **AND** 立即生效（下次操作使用新配置）

---

### Requirement: 短期记忆数据隔离

系统SHALL确保短期记忆的Session级隔离。

#### Scenario: 跨Session隔离
- **WHEN** 读取Session A的短期记忆
- **THEN** 系统仅返回Session A的数据
- **AND** 不包含任何其他Session的数据

#### Scenario: TTL自动过期
- **WHEN** Session过期（超过TTL）
- **THEN** 系统自动删除关联的短期记忆数据
- **AND** 包括 stm:window、stm:summary、stm:config
