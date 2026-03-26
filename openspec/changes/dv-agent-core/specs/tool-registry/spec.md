# Spec: tool-registry

Skill与MCP工具统一注册与管理，支持动态发现与执行。

## ADDED Requirements

### Requirement: 统一工具抽象

系统SHALL提供统一的工具抽象层，屏蔽Skill和MCP Tool的差异。

#### Scenario: 工具定义标准化
- **WHEN** 注册一个工具（Skill或MCP Tool）
- **THEN** 工具包含name、description、input_schema、output_schema属性
- **AND** 提供统一的execute方法接口

#### Scenario: LLM工具描述生成
- **WHEN** Agent需要工具列表供LLM选择
- **THEN** Registry生成符合OpenAI Function Calling格式的工具描述
- **AND** 包含function.name、function.description、function.parameters

---

### Requirement: Skill注册

系统SHALL支持注册内置Python Skill。

#### Scenario: 函数装饰器注册
- **WHEN** 使用@skill装饰器标注函数
- **THEN** 系统自动注册该函数为Skill
- **AND** 从函数签名和docstring提取schema

#### Scenario: 手动注册Skill
- **WHEN** 调用registry.register_skill(name, func, schema)
- **THEN** 系统注册该Skill到Registry
- **AND** 验证schema格式正确

#### Scenario: Skill执行
- **WHEN** Agent调用Skill
- **THEN** 系统执行对应Python函数
- **AND** 返回ToolResult对象

---

### Requirement: MCP工具集成

系统SHALL支持动态加载MCP Server提供的工具。

#### Scenario: MCP Server连接
- **WHEN** 系统启动时
- **THEN** 根据config/mcp.yaml连接配置的MCP Servers
- **AND** 进行健康检查确认Server可用

#### Scenario: MCP工具发现
- **WHEN** MCP Server连接成功
- **THEN** 系统获取该Server的工具列表
- **AND** 为每个工具创建MCPTool包装器并注册

#### Scenario: MCP工具执行
- **WHEN** Agent调用MCP Tool
- **THEN** 系统通过MCP Client向Server发送调用请求
- **AND** 等待并返回执行结果

#### Scenario: MCP Server断连处理
- **WHEN** MCP Server连接中断
- **THEN** 系统标记该Server的工具为不可用
- **AND** 尝试定期重连

---

### Requirement: 工具Registry管理

系统SHALL提供统一的工具注册表管理。

#### Scenario: 工具注册
- **WHEN** 调用registry.register(tool)
- **THEN** 系统将工具添加到注册表
- **AND** 如果name冲突则抛出错误

#### Scenario: 工具查询
- **WHEN** 调用registry.get(name)
- **THEN** 返回对应的工具实例
- **AND** 如果不存在返回None

#### Scenario: 工具列表
- **WHEN** 调用registry.list()
- **THEN** 返回所有已注册工具的名称列表

#### Scenario: 按Agent筛选工具
- **WHEN** 调用registry.list_for_agent(agent_id)
- **THEN** 返回该Agent可用的工具列表
- **AND** 根据配置过滤工具权限

---

### Requirement: 工具执行封装

系统SHALL提供统一的工具执行入口。

#### Scenario: 工具调用成功
- **WHEN** 调用registry.execute(name, params)
- **THEN** 系统查找工具并执行
- **AND** 返回ToolResult{success=True, result=...}

#### Scenario: 工具调用失败
- **WHEN** 工具执行抛出异常
- **THEN** 返回ToolResult{success=False, error=...}
- **AND** 记录错误日志

#### Scenario: 工具不存在
- **WHEN** 调用的工具名不在Registry中
- **THEN** 返回ToolResult{success=False, error="Tool not found"}

#### Scenario: 参数验证
- **WHEN** 调用工具前
- **THEN** 系统根据input_schema验证参数
- **AND** 参数无效时返回错误

---

### Requirement: 工具配置管理

系统SHALL支持通过配置文件管理工具。

#### Scenario: 加载MCP配置
- **WHEN** 系统启动时
- **THEN** 从config/mcp.yaml加载MCP Server配置
- **AND** 配置包含server_name、endpoint、timeout等

#### Scenario: 工具权限配置
- **WHEN** 配置Agent的工具访问权限
- **THEN** 在config/agents.yaml中指定allowed_tools列表
- **AND** Registry根据配置过滤工具

#### Scenario: 动态刷新配置
- **WHEN** 调用registry.reload()
- **THEN** 重新加载配置文件
- **AND** 更新工具注册（不中断现有调用）