# Tasks: dv-agent-core

## 1. 项目初始化与基础设施

- [x] 1.1 创建项目目录结构（llm_gateway/、agents/、a2a/、intent_service/、session/、tools/、config/）
- [x] 1.2 创建 pyproject.toml 并配置依赖（langchain、langgraph、httpx、redis、pydantic）
- [x] 1.3 创建配置文件模板（config/llm.yaml、config/agents.yaml、config/mcp.yaml）
- [x] 1.4 配置 Redis 连接工具类和连接池
- [x] 1.5 创建日志配置和通用异常类

## 2. LLM Gateway - 统一适配层

- [ ] 2.1 定义 Message、LLMResponse、StreamChunk 等核心数据模型（Pydantic）
- [ ] 2.2 实现 BaseAdapter 抽象基类（invoke、stream、invoke_with_tools 接口）
- [ ] 2.3 实现 OpenAIAdapter（同步调用、流式调用、工具调用）
- [ ] 2.4 实现 DeepSeekAdapter（兼容OpenAI格式，处理差异点）
- [ ] 2.5 实现 OllamaAdapter（本地HTTP调用、流式响应处理）
- [ ] 2.6 实现 Router 智能路由（Provider选择、fallback链配置）
- [ ] 2.7 实现 RetryHandler 重试策略（指数退避、可重试错误判断、jitter）
- [ ] 2.8 实现 LLMGateway 统一入口（集成Router和Retry）
- [ ] 2.9 实现 Token计数与成本追踪
- [ ] 2.10 编写 LLM Gateway 单元测试

## 3. A2A Protocol - 通信协议

- [ ] 3.1 定义 A2A 消息格式数据模型（A2ARequest、A2AResponse、AgentCard）
- [ ] 3.2 实现 A2A Server 基础框架（FastAPI路由注册）
- [ ] 3.3 实现 /a2a/{agent_id}/card 端点（Agent Card 服务发现）
- [ ] 3.4 实现 /a2a/invoke 端点（同步调用处理）
- [ ] 3.5 实现共享上下文读取/写回机制（context_ref → Redis）
- [ ] 3.6 实现请求幂等性检查（task_id 缓存）
- [ ] 3.7 实现 A2A Client（供 Orchestrator 调用 Worker Agent）
- [ ] 3.8 编写 A2A Protocol 单元测试

## 4. Session Management - 会话管理

- [ ] 4.1 定义 Session 数据模型（SessionMeta、ConversationMessage）
- [ ] 4.2 实现 SessionStore（Redis Hash 存储 Session 元数据）
- [ ] 4.3 实现 HistoryStore（Redis List 存储对话历史）
- [ ] 4.4 实现 ContextStore（Redis Hash 存储 Agent 上下文）
- [ ] 4.5 实现 Session 创建、读取、更新、删除操作
- [ ] 4.6 实现对话历史滑动窗口（自动清理旧消息）
- [ ] 4.7 实现 ReAct 状态持久化（thought_chain、tool_results）
- [ ] 4.8 实现 Session 生命周期管理（active → suspended → closed）
- [ ] 4.9 实现 Session 恢复逻辑（检测未完成任务、询问用户）
- [ ] 4.10 实现 Session API 端点（/api/v1/session/...）
- [ ] 4.11 编写 Session Management 单元测试

## 5. Tool Registry - 工具注册

- [ ] 5.1 定义 BaseTool 抽象类和 ToolResult 数据模型
- [ ] 5.2 实现 SkillTool 类（内置 Python Skill 封装）
- [ ] 5.3 实现 @skill 装饰器（自动提取 schema）
- [ ] 5.4 实现 MCPTool 类（MCP 协议工具封装）
- [ ] 5.5 实现 MCPClient（MCP Server 连接与调用）
- [ ] 5.6 实现 ToolRegistry（工具注册、查询、列表、执行）
- [ ] 5.7 实现 list_for_llm() 方法（生成 OpenAI Function Calling 格式）
- [ ] 5.8 实现 MCP Server 启动时自动发现与注册
- [ ] 5.9 实现工具权限配置与过滤
- [ ] 5.10 编写 Tool Registry 单元测试

## 6. Intent Recognition - 意图识别

- [ ] 6.1 定义 IntentResult 数据模型（intent、confidence、slots、target_agents）
- [ ] 6.2 实现规则层识别器（关键词匹配、正则提取）
- [ ] 6.3 实现 Redis 缓存层（query → intent 缓存）
- [ ] 6.4 实现 Embedding 语义匹配层（向量相似度计算）
- [ ] 6.5 实现 LLM 分析层（Few-shot Prompt、槽位提取）
- [ ] 6.6 实现 IntentRecognizer 主类（三层流水线）
- [ ] 6.7 实现意图类型定义与 Agent 映射配置
- [ ] 6.8 实现 Intent API 端点（/intent/recognize）
- [ ] 6.9 编写 Intent Recognition 单元测试

## 7. Worker Agents - 专业Agent

- [ ] 7.1 实现 BaseWorkerAgent 抽象类（A2A接口、健康检查）
- [ ] 7.2 实现 QAAgent（通用问答、上下文关联）
- [ ] 7.3 实现 KnowledgeAgent（RAG 查询、文档分析）
- [ ] 7.4 实现 SearchAgent（网页搜索、信息聚合）
- [ ] 7.5 为每个 Agent 实现 Agent Card 生成
- [ ] 7.6 为每个 Agent 实现 capability 处理函数
- [ ] 7.7 集成 MCP 工具（KnowledgeAgent 使用 DeepWiki）
- [ ] 7.8 编写 Worker Agents 单元测试

## 8. Orchestrator Agent - 主控Agent

- [ ] 8.1 实现 Orchestrator 主类框架
- [ ] 8.2 实现 Intent 解析与任务分类
- [ ] 8.3 实现任务分解逻辑（复杂任务 → 子任务列表）
- [ ] 8.4 实现 Agent 路由决策（intent → target agent）
- [ ] 8.5 实现 A2A 调用 Worker Agent 逻辑
- [ ] 8.6 实现结果聚合（单Agent / 多Agent 结果合并）
- [ ] 8.7 基于 LangGraph 实现 ReAct 决策循环
- [ ] 8.8 实现 ReAct 循环中断检测（相似度检查、最大迭代）
- [ ] 8.9 实现错误恢复与降级策略
- [ ] 8.10 集成 Session 管理（状态持久化、恢复）
- [ ] 8.11 编写 Orchestrator Agent 单元测试

## 9. API Layer - 对外接口

- [ ] 9.1 实现 FastAPI 应用入口和路由配置
- [ ] 9.2 实现 /api/v1/chat 对话端点（接入 Orchestrator）
- [ ] 9.3 实现流式响应支持（SSE / WebSocket）
- [ ] 9.4 实现请求验证和错误处理中间件
- [ ] 9.5 实现健康检查端点 /health
- [ ] 9.6 编写 API 集成测试

## 10. 集成与部署

- [ ] 10.1 编写应用启动脚本（main.py）
- [ ] 10.2 实现启动时初始化流程（Redis连接、MCP连接、Agent注册）
- [ ] 10.3 编写 Docker Compose 配置（应用 + Redis）
- [ ] 10.4 编写 README.md（安装、配置、使用说明）
- [ ] 10.5 编写端到端集成测试
- [ ] 10.6 性能基准测试（响应延迟、并发处理）
