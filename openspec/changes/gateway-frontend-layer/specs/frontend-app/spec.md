## ADDED Requirements

### Requirement: Frontend SHALL provide login and registration pages

前端 SHALL 提供用户登录和注册页面。

#### Scenario: 登录页面展示
- **WHEN** 用户访问 `/login`
- **THEN** 页面 SHALL 展示邮箱和密码输入框
- **AND** 提供"登录"按钮和"注册"链接

#### Scenario: 注册页面展示
- **WHEN** 用户访问 `/register`
- **THEN** 页面 SHALL 展示邮箱、密码、确认密码输入框
- **AND** 可选的名称输入框
- **AND** 提供"注册"按钮

#### Scenario: 登录成功跳转
- **WHEN** 用户成功登录
- **THEN** 页面 SHALL 跳转到聊天页面 `/chat`
- **AND** 保存 Access Token 到内存

#### Scenario: 表单验证
- **WHEN** 用户提交无效数据
- **THEN** 页面 SHALL 显示内联错误提示
- **AND** 不提交请求到服务器

---

### Requirement: Frontend SHALL provide session list

前端 SHALL 展示用户的会话列表。

#### Scenario: 会话列表展示
- **WHEN** 用户进入聊天页面
- **THEN** 左侧边栏 SHALL 展示会话列表
- **AND** 每个会话显示标题、消息数、最后更新时间

#### Scenario: 创建新会话
- **WHEN** 用户点击"新建会话"按钮
- **THEN** 系统 SHALL 创建新会话
- **AND** 自动选中新会话

#### Scenario: 切换会话
- **WHEN** 用户点击某个会话
- **THEN** 聊天窗口 SHALL 加载该会话的历史消息

#### Scenario: 删除会话
- **WHEN** 用户点击会话的删除按钮
- **THEN** 系统 SHALL 显示确认对话框
- **AND** 确认后删除会话

---

### Requirement: Frontend SHALL provide chat interface

前端 SHALL 提供聊天交互界面。

#### Scenario: 消息列表展示
- **WHEN** 用户选中会话
- **THEN** 聊天窗口 SHALL 展示历史消息
- **AND** 用户消息右对齐，助手消息左对齐

#### Scenario: 发送消息
- **WHEN** 用户在输入框输入并按回车或点击发送
- **THEN** 消息 SHALL 立即显示在消息列表
- **AND** 输入框清空

#### Scenario: 流式响应展示
- **WHEN** 助手生成响应
- **THEN** 响应内容 SHALL 逐字符显示
- **AND** 显示打字光标动画

#### Scenario: Markdown 渲染
- **WHEN** 助手消息包含 Markdown
- **THEN** 系统 SHALL 正确渲染格式
- **AND** 代码块支持语法高亮

---

### Requirement: Frontend SHALL display Agent execution status

前端 SHALL 实时展示 Agent 执行状态。

#### Scenario: 思考状态展示
- **WHEN** 收到 `agent.thinking` 事件
- **THEN** 界面 SHALL 显示"正在思考..."指示器
- **AND** 展示当前步骤编号

#### Scenario: 工具调用展示
- **WHEN** 收到 `agent.tool_call` 事件
- **THEN** 界面 SHALL 展示工具调用卡片
- **AND** 显示工具名称和输入参数

#### Scenario: 工具结果展示
- **WHEN** 收到 `agent.tool_result` 事件
- **THEN** 工具卡片 SHALL 更新显示执行结果
- **AND** 标记为完成状态

#### Scenario: 错误展示
- **WHEN** 收到 `agent.error` 事件
- **THEN** 界面 SHALL 显示错误提示
- **AND** 提供重试选项

---

### Requirement: Frontend SHALL manage authentication state

前端 SHALL 正确管理认证状态。

#### Scenario: Token 自动刷新
- **WHEN** Access Token 即将过期（剩余 2 分钟）
- **THEN** 前端 SHALL 自动调用刷新接口
- **AND** 更新内存中的 Token

#### Scenario: 未登录重定向
- **WHEN** 未认证用户访问受保护页面
- **THEN** 系统 SHALL 重定向到登录页面

#### Scenario: 登出清理
- **WHEN** 用户点击登出
- **THEN** 前端 SHALL 清除本地 Token
- **AND** 关闭 WebSocket 连接
- **AND** 跳转到登录页面

---

### Requirement: Frontend SHALL manage WebSocket connection

前端 SHALL 管理 WebSocket 连接状态。

#### Scenario: 自动连接
- **WHEN** 用户登录成功
- **THEN** 前端 SHALL 自动建立 WebSocket 连接

#### Scenario: 断线重连
- **WHEN** WebSocket 连接断开
- **THEN** 前端 SHALL 使用指数退避策略重连
- **AND** 显示连接状态指示器

#### Scenario: 心跳发送
- **WHEN** 连接建立后
- **THEN** 前端 SHALL 每 30 秒发送 ping 消息

---

### Requirement: Frontend SHALL be responsive

前端界面 SHALL 响应式适配不同屏幕尺寸。

#### Scenario: 桌面端布局
- **WHEN** 屏幕宽度 >= 1024px
- **THEN** 界面 SHALL 显示三栏布局（会话列表、聊天、详情）

#### Scenario: 平板端布局
- **WHEN** 屏幕宽度 768-1023px
- **THEN** 界面 SHALL 显示双栏布局（会话列表可折叠）

#### Scenario: 移动端提示
- **WHEN** 屏幕宽度 < 768px
- **THEN** 界面 SHALL 显示优化提示（当前版本不完全支持移动端）
