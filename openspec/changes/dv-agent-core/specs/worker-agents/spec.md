# Spec: worker-agents

专业Worker Agents（Q&A、Knowledge、Search），处理特定领域任务。

## ADDED Requirements

### Requirement: Q&A Agent通用问答

系统SHALL提供Q&A Agent处理通用问答任务。

#### Scenario: 简单问答直接回答
- **WHEN** 用户提问"Python中list和tuple的区别"
- **THEN** Q&A Agent调用LLM生成回答
- **AND** 返回结构化响应

#### Scenario: 上下文关联问答
- **WHEN** 用户在Session中追问"它的性能如何"（指代前文提到的技术）
- **THEN** Q&A Agent从Session历史中获取上下文
- **AND** 结合上下文生成回答

---

### Requirement: Knowledge Agent知识检索

系统SHALL提供Knowledge Agent进行知识库检索和文档分析。

#### Scenario: RAG知识库查询
- **WHEN** 用户查询项目相关文档问题
- **THEN** Knowledge Agent从向量数据库检索相关文档片段
- **AND** 使用检索增强生成回答
- **AND** 标注答案来源

#### Scenario: 文档分析任务
- **WHEN** 用户请求"分析这个项目架构"
- **THEN** Knowledge Agent读取项目文件
- **AND** 使用LLM分析并输出结构化结果

#### Scenario: MCP工具集成
- **WHEN** Knowledge Agent需要查询GitHub仓库文档
- **THEN** Agent调用DeepWiki MCP工具
- **AND** 返回文档查询结果

---

### Requirement: Search Agent网页搜索

系统SHALL提供Search Agent执行网页搜索和信息聚合。

#### Scenario: 网页搜索并总结
- **WHEN** 用户请求"搜索最新的AI Agent框架对比"
- **THEN** Search Agent调用搜索工具获取结果
- **AND** 对搜索结果进行摘要和整理
- **AND** 返回结构化总结

#### Scenario: 多源信息聚合
- **WHEN** 用户需要综合多方信息
- **THEN** Search Agent从多个来源获取信息
- **AND** 去重和排序
- **AND** 输出综合报告

---

### Requirement: Worker Agent A2A通信

每个Worker Agent SHALL实现A2A协议，支持Orchestrator调用。

#### Scenario: 响应Agent Card请求
- **WHEN** Orchestrator请求GET /a2a/{agent_id}/card
- **THEN** Worker Agent返回Agent Card定义
- **AND** 包含capabilities、endpoints、input_schema等信息

#### Scenario: 处理Invoke请求
- **WHEN** Orchestrator POST /a2a/invoke 调用Worker Agent
- **THEN** Worker Agent解析请求参数
- **AND** 执行对应capability
- **AND** 返回A2A标准响应格式

#### Scenario: 共享上下文读取
- **WHEN** Worker Agent收到带有context_ref的请求
- **THEN** Agent从Redis读取共享上下文
- **AND** 将执行结果写回context_updates

---

### Requirement: Worker Agent健康检查

每个Worker Agent SHALL提供健康检查端点。

#### Scenario: 健康检查成功
- **WHEN** GET /health 请求到达
- **THEN** 返回200状态码和health: "healthy"

#### Scenario: 依赖服务不健康
- **WHEN** Agent依赖的LLM服务不可用
- **THEN** 返回503状态码
- **AND** 标注不健康的依赖服务

---

### Requirement: Worker Agent配置管理

系统SHALL支持通过配置文件定义Worker Agent。

#### Scenario: 加载Agent配置
- **WHEN** 系统启动时
- **THEN** 从`config/agents.yaml`加载Worker Agent配置
- **AND** 为每个Agent启动A2A服务端点
- **AND** 注册到Orchestrator的服务发现

#### Scenario: Agent能力声明
- **WHEN** Agent配置中声明capabilities
- **THEN** 系统自动生成Agent Card
- **AND** capability映射到具体的处理函数