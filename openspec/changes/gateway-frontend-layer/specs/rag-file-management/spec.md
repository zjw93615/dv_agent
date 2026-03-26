## ADDED Requirements

### Requirement: Frontend SHALL provide document upload interface

前端 SHALL 提供文档上传界面。

**支持的文件类型**: PDF, DOCX, TXT, MD, HTML
**最大文件大小**: 50MB

#### Scenario: 拖拽上传
- **WHEN** 用户将文件拖拽到上传区域
- **THEN** 界面 SHALL 高亮显示拖拽区域
- **AND** 释放后开始上传

#### Scenario: 点击选择上传
- **WHEN** 用户点击上传按钮
- **THEN** 系统 SHALL 打开文件选择器
- **AND** 选择文件后开始上传

#### Scenario: 上传进度展示
- **WHEN** 文件上传中
- **THEN** 界面 SHALL 显示上传进度条
- **AND** 显示上传速度和剩余时间

#### Scenario: 文件类型校验
- **WHEN** 用户选择不支持的文件类型
- **THEN** 界面 SHALL 显示错误提示
- **AND** 不启动上传

#### Scenario: 文件大小校验
- **WHEN** 用户选择超过 50MB 的文件
- **THEN** 界面 SHALL 显示错误提示
- **AND** 不启动上传

---

### Requirement: Frontend SHALL display document list

前端 SHALL 展示用户的文档列表。

#### Scenario: 文档列表展示
- **WHEN** 用户访问文档管理页面
- **THEN** 界面 SHALL 展示文档列表
- **AND** 每个文档显示文件名、类型图标、大小、分块数、状态

#### Scenario: 分页加载
- **WHEN** 文档数量超过单页容量
- **THEN** 界面 SHALL 提供分页或无限滚动加载

#### Scenario: 按集合筛选
- **WHEN** 用户选择某个集合
- **THEN** 列表 SHALL 只显示该集合的文档

---

### Requirement: Frontend SHALL display document processing status

前端 SHALL 实时展示文档处理状态。

**处理阶段**:
1. 排队中 (queued)
2. 文本提取 (extracting)
3. 分块处理 (chunking)
4. 向量化 (embedding)
5. 索引存储 (indexing)
6. 完成 (completed) / 失败 (failed)

#### Scenario: 处理中状态
- **WHEN** 文档正在处理
- **THEN** 界面 SHALL 显示当前阶段和进度百分比
- **AND** 显示旋转动画

#### Scenario: 处理完成状态
- **WHEN** 文档处理完成
- **THEN** 界面 SHALL 显示绿色完成图标
- **AND** 显示分块数量

#### Scenario: 处理失败状态
- **WHEN** 文档处理失败
- **THEN** 界面 SHALL 显示红色失败图标
- **AND** 显示错误信息
- **AND** 提供重试按钮

#### Scenario: WebSocket 状态更新
- **WHEN** 收到文档处理事件
- **THEN** 界面 SHALL 实时更新文档状态
- **AND** 无需手动刷新

---

### Requirement: Frontend SHALL support document deletion

前端 SHALL 支持删除文档。

#### Scenario: 单个删除
- **WHEN** 用户点击文档的删除按钮
- **THEN** 系统 SHALL 显示确认对话框
- **AND** 确认后删除文档及其向量索引

#### Scenario: 批量删除
- **WHEN** 用户选择多个文档并点击批量删除
- **THEN** 系统 SHALL 显示确认对话框
- **AND** 列出将被删除的文档数量
- **AND** 确认后批量删除

---

### Requirement: Frontend SHALL provide collection management

前端 SHALL 支持集合（文件夹）管理。

#### Scenario: 集合列表展示
- **WHEN** 用户访问文档管理页面
- **THEN** 左侧栏 SHALL 展示集合列表
- **AND** 每个集合显示名称和文档数量

#### Scenario: 创建集合
- **WHEN** 用户点击"新建集合"按钮
- **THEN** 界面 SHALL 显示创建表单
- **AND** 用户输入名称和描述后创建

#### Scenario: 删除集合
- **WHEN** 用户删除集合
- **THEN** 系统 SHALL 显示确认对话框
- **AND** 询问是否同时删除集合中的文档

---

### Requirement: Frontend SHALL provide document search

前端 SHALL 提供文档搜索功能。

#### Scenario: 搜索界面
- **WHEN** 用户访问搜索页面或点击搜索按钮
- **THEN** 界面 SHALL 显示搜索输入框
- **AND** 可选的集合筛选器

#### Scenario: 搜索结果展示
- **WHEN** 用户输入查询并搜索
- **THEN** 界面 SHALL 展示匹配的文档片段
- **AND** 高亮显示匹配文本
- **AND** 显示相关度分数
- **AND** 提供"查看来源"链接

#### Scenario: 搜索结果分页
- **WHEN** 搜索结果超过单页容量
- **THEN** 界面 SHALL 提供分页控件
