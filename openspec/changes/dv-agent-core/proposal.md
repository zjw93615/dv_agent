# Proposal: dv-agent-core

## Why

当前需要一个通用AI Agent的核心决策层，以支持多Agent协作系统。该系统需要解决以下问题：

1. **LLM接入碎片化**：不同LLM Provider（OpenAI、DeepSeek、Ollama）的API差异大，缺乏统一适配层，导致切换成本高、代码重复。
2. **Agent协作复杂度高**：多Agent场景下缺乏标准化通信协议，Agent间协作需要从零构建。
3. **Session状态管理缺失**：用户中断任务后无法恢复，需要重新开始，用户体验差。
4. **意图识别能力不足**：简单关键词匹配无法准确理解用户意图，影响Agent路由准确性。

**现在做的理由**：Agent技术日趋成熟，A2A协议逐渐标准化，是构建可扩展Agent系统的最佳时机。

## What Changes

### 新增功能

- **LLM统一适配层**：兼容OpenAI API、DeepSeek、Ollama本地部署的统一接口，支持同步/流式调用、自动重试与降级路由。
- **Orchestrator Agent**：主控Agent，负责意图识别结果解析、任务分解与调度、Agent路由、结果聚合、Session管理。
- **Worker Agents**：专业Agent集合，包括Q&A Agent（通用问答）、Knowledge Agent（知识检索）、Search Agent（网页搜索与总结）。
- **A2A Protocol通信**：Agent间采用A2A协议进行同步HTTP/JSON-RPC通信，支持Agent Card服务发现与标准消息格式。
- **Intent Recognition Service**：独立意图识别服务，支持规则匹配+Embedding检索+LLM分析三层识别，Redis缓存相似query结果。
- **Session状态管理**：基于Redis的Session持久化，支持对话历史、Agent上下文、ReAct状态保存与恢复。
- **Skill & MCP统一注册**：内置Skill与MCP Tool的统一抽象与动态注册，支持启动时连接MCP Servers。

### 技术选型

- **框架**：LangChain + LangGraph（ReAct决策循环与Agent编排）
- **通信协议**：A2A（Agent-to-Agent）同步HTTP调用
- **存储**：Redis（Session、Message Queue、Context Cache）
- **部署**：单进程多Worker（可演进为独立进程部署）

## Capabilities

### New Capabilities

以下能力将创建对应的 `specs/<name>/spec.md` 文件：

| Capability | 描述 |
|------------|------|
| `llm-gateway` | LLM统一适配层，支持多Provider接入、自动重试、降级路由、流式响应 |
| `orchestrator-agent` | 主控Agent，负责任务分解、Agent调度、结果聚合、Session管理 |
| `worker-agents` | 专业Worker Agents（Q&A、Knowledge、Search），处理特定领域任务 |
| `a2a-protocol` | Agent间A2A通信协议，包括Agent Card、Invoke、Status等标准接口 |
| `intent-recognition` | 独立意图识别服务，三层识别架构（规则+Embedding+LLM），Redis缓存 |
| `session-management` | Session状态持久化与恢复，包括对话历史、Agent上下文、ReAct状态 |
| `tool-registry` | Skill与MCP工具统一注册与管理，支持动态发现与执行 |

### Modified Capabilities

无（本项目为新建项目，不存在已修改的能力）。

## Impact

### 新增代码模块

```
dv-agent/
├── llm_gateway/           # LLM统一适配层
│   ├── adapters/          # Provider适配器（OpenAI, DeepSeek, Ollama）
│   ├── router.py          # 智能路由与降级
│   └── retry.py           # 重试策略
├── agents/
│   ├── orchestrator/      # 主控Agent
│   ├── qa/                # Q&A Agent
│   ├── knowledge/         # Knowledge Agent
│   └── search/            # Search Agent
├── a2a/                   # A2A协议实现
│   ├── protocol.py        # 消息格式定义
│   ├── server.py          # A2A服务端
│   └── client.py          # A2A客户端
├── intent_service/        # 意图识别服务
├── session/               # Session管理
├── tools/
│   ├── skills/            # 内置Skill
│   └── mcp/               # MCP集成
└── config/                # 配置管理
```

### 外部依赖

| 依赖 | 用途 | 版本要求 |
|------|------|----------|
| Redis | Session存储、消息队列、缓存 | >= 7.0 |
| LangChain | Agent框架 | >= 0.3.0 |
| LangGraph | ReAct决策循环 | >= 0.2.0 |
| httpx | A2A HTTP通信 | >= 0.27.0 |
| pydantic | 数据验证 | >= 2.0 |

### API影响

- 新增REST API入口：`/api/v1/chat`、`/api/v1/session/{id}`
- 新增A2A端点：`/a2a/{agent_id}/card`、`/a2a/invoke`、`/a2a/status/{task_id}`
- 新增Intent Service API：`/intent/recognize`

### 配置文件

- 新增 `config/llm.yaml`：LLM Provider配置
- 新增 `config/agents.yaml`：Agent配置与A2A端点
- 新增 `config/mcp.yaml`：MCP Server连接配置
