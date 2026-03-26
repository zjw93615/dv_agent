# Design: dv-agent-core

## Context

本项目构建一个通用AI Agent核心决策层，支持多Agent协作系统。当前状态为全新项目，需要从零构建以下核心能力：

- **LLM统一适配层**：解决多Provider API差异问题
- **多Agent协作架构**：Orchestrator + Worker Agents分层架构
- **A2A通信协议**：Agent间标准化同步通信
- **Session状态管理**：Redis持久化与断点恢复

### 约束条件

- **技术栈**：Python 3.10+，LangChain/LangGraph框架
- **存储**：Redis作为唯一外部存储依赖
- **部署**：初期单进程多Worker，未来可演进为独立服务
- **通信**：A2A同步HTTP调用（无消息队列）

## Goals / Non-Goals

**Goals:**

1. 构建可扩展的LLM Provider适配层，支持OpenAI/DeepSeek/Ollama无缝切换
2. 实现Orchestrator + Worker Agent分层架构，支持任务路由和结果聚合
3. 基于LangGraph实现ReAct决策循环，支持工具调用和多轮推理
4. 设计A2A协议规范，实现Agent间标准化通信
5. 基于Redis实现Session持久化，支持对话恢复和状态断点续传
6. 统一Skill和MCP工具的注册与调用接口

**Non-Goals:**

1. 不实现消息队列异步通信（本版本仅支持A2A同步调用）
2. 不实现多租户隔离（单用户场景优先）
3. 不实现分布式部署（单进程启动，未来可扩展）
4. 不实现工具的可视化管理界面
5. 不实现Agent的动态热更新（需重启生效）

## Decisions

### Decision 1: Agent框架选型 - LangChain + LangGraph

**选择**：使用LangChain作为Agent基础框架，LangGraph处理ReAct决策循环。

**理由**：
- LangChain生态成熟，LLM适配、工具调用、Prompt管理能力完善
- LangGraph天然支持状态机编排，契合ReAct的Thought-Action-Observation循环
- LangSmith可选集成，提供生产级监控能力

**备选方案**：
| 方案 | 优点 | 缺点 | 
|------|------|------|
| AutoGen | 多Agent对话原生支持 | 控制流难预测，token消耗不可控 |
| LlamaIndex | RAG能力强 | Agent编排能力弱 |
| 自研 | 完全可控 | 开发成本高 |

---

### Decision 2: Agent通信协议 - A2A同步HTTP

**选择**：采用A2A协议规范，Agent间使用同步HTTP/JSON-RPC通信。

**理由**：
- 同步调用实现简单，调试方便
- A2A协议标准化，未来可接入第三方Agent
- 避免消息队列引入的额外复杂度

**设计细节**：

```
┌─────────────────────────────────────────────────────────┐
│                    A2A Message Flow                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Orchestrator                        Worker Agent       │
│      │                                    │             │
│      │ ──── GET /a2a/card ────────────▶  │             │
│      │ ◀─── Agent Card Response ─────── │             │
│      │                                    │             │
│      │ ──── POST /a2a/invoke ─────────▶  │             │
│      │      {task_id, session_id,        │             │
│      │       capability, payload,         │             │
│      │       context_ref}                │             │
│      │                                    │             │
│      │ ◀─── A2A Response ─────────────── │             │
│      │      {status, result,              │             │
│      │       context_updates}             │             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**备选方案**：
| 方案 | 优点 | 缺点 |
|------|------|------|
| 消息队列(Redis Stream) | 异步解耦，削峰填谷 | 复杂度高，调试困难 |
| gRPC | 性能好，类型安全 | 生态支持不如HTTP |

---

### Decision 3: Session存储 - Redis Hash + List

**选择**：使用Redis存储Session状态，采用Hash存储元数据，List存储对话历史。

**理由**：
- Redis读写速度快，满足实时性要求
- 原生TTL支持，自动过期清理
- Hash/List数据结构契合Session数据特点

**数据结构设计**：

```
# Session元数据 (Hash)
session:{session_id} = {
  id: "sess_xxx",
  user_id: "user_xxx",
  created_at: "2026-03-23T10:00:00Z",
  last_active: "2026-03-23T10:30:00Z",
  status: "active"  # active/suspended/closed
}

# 对话历史 (List) - 使用LPUSH/LRANGE
history:{session_id} = [
  {role: "user", content: "...", timestamp: "..."},
  {role: "assistant", content: "...", timestamp: "..."},
  {role: "tool", name: "web_search", result: "..."}
]

# Agent上下文 (Hash) - ReAct状态恢复关键
context:{session_id}:{agent_id} = {
  react_state: "observation",
  thought_chain: "[...]",
  pending_tools: "[...]",
  tool_results: "{...}",
  iteration: 3
}
```

**备选方案**：
| 方案 | 优点 | 缺点 |
|------|------|------|
| SQLite | 无额外依赖 | 不适合分布式 |
| PostgreSQL | 事务支持好 | 过重，引入额外依赖 |

---

### Decision 4: LLM适配层架构 - 适配器模式

**选择**：使用适配器模式，为每个Provider实现独立Adapter。

**理由**：
- 解耦Provider特定逻辑，新Provider只需实现Adapter接口
- 统一Message/Response格式，上层代码无需关心Provider差异
- 支持运行时动态切换Provider

**架构设计**：

```
┌────────────────────────────────────────────────────────┐
│                   LLM Gateway                          │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │               LLMGateway (统一入口)               │  │
│  │  - invoke(messages, tools, **kwargs)             │  │
│  │  - stream(messages, tools, **kwargs)             │  │
│  │  - invoke_with_tools(messages, tools)            │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                             │
│                          ▼                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │               Router (智能路由)                   │  │
│  │  - select_provider(task_type, priority)          │  │
│  │  - fallback_chain: [openai, deepseek, ollama]    │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                             │
│          ┌───────────────┼───────────────┐             │
│          ▼               ▼               ▼             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │
│  │ OpenAI     │ │ DeepSeek   │ │ Ollama      │      │
│  │ Adapter    │ │ Adapter    │ │ Adapter     │      │
│  └─────────────┘ └─────────────┘ └─────────────┘      │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

### Decision 5: Intent识别架构 - 三层识别 + 缓存

**选择**：实现规则匹配→Embedding检索→LLM分析三层识别，Redis缓存高频query。

**理由**：
- 规则层处理高频明确意图，延迟<10ms
- Embedding层处理语义相似意图，延迟<100ms
- LLM层兜底复杂/歧义意图，延迟<2s
- 缓存减少重复计算，降低LLM调用成本

**识别流程**：

```
用户输入
    │
    ▼
┌─────────────────────────┐
│ Layer 1: 规则匹配       │ 命中 → 直接返回
│ - 关键词/正则表达式     │─────────────────────▶ {intent, confidence=1.0}
│ - 延迟 < 10ms          │
└──────────┬──────────────┘
           │ 未命中
           ▼
┌─────────────────────────┐
│ Layer 2: Redis缓存检查  │ 命中 → 直接返回
│ - 相似query缓存         │─────────────────────▶ {intent, confidence}
│ - 延迟 < 5ms           │
└──────────┬──────────────┘
           │ 未命中
           ▼
┌─────────────────────────┐
│ Layer 3: Embedding检索  │ 相似度>0.9 → 返回
│ - 向量相似度匹配        │─────────────────────▶ {intent, confidence}
│ - 延迟 < 100ms         │
└──────────┬──────────────┘
           │ 相似度不足
           ▼
┌─────────────────────────┐
│ Layer 4: LLM分析        │
│ - Few-shot + CoT推理    │─────────────────────▶ {intent, slots, reasoning}
│ - 延迟 < 2s            │
└─────────────────────────┘
           │
           ▼
      写入Redis缓存
```

---

### Decision 6: Tool Registry设计 - 统一抽象

**选择**：Skill和MCP Tool统一继承BaseTool抽象，通过Registry统一管理。

**理由**：
- Agent调用时无需关心Tool来源（内置Skill或外部MCP）
- 统一input_schema格式，支持LLM Function Calling
- 动态注册/注销，支持MCP Server热连接

**类结构**：

```python
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

class SkillTool(BaseTool):
    """内置Python Skill"""
    def __init__(self, func: Callable):
        self._func = func
    
    async def execute(self, **kwargs) -> ToolResult:
        return await self._func(**kwargs)

class MCPTool(BaseTool):
    """MCP协议工具"""
    def __init__(self, server: str, tool_name: str, client: MCPClient):
        self._client = client
        self._server = server
        self._tool_name = tool_name
    
    async def execute(self, **kwargs) -> ToolResult:
        return await self._client.invoke(self._server, self._tool_name, kwargs)

class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool): ...
    def get(self, name: str) -> BaseTool: ...
    def list_for_llm(self) -> List[dict]: ...  # 生成LLM Function定义
```

---

### Decision 7: 单进程多Worker部署

**选择**：初期采用单进程部署，Orchestrator和Worker Agents作为内部模块运行。

**理由**：
- 开发调试简单，无需处理网络通信问题
- 避免过早引入分布式复杂度
- A2A协议设计支持未来拆分为独立服务

**演进路径**：

```
Phase 1 (当前): 单进程
┌─────────────────────────────────────────────────┐
│                 Single Process                  │
│  ┌─────────────┐  ┌─────────────┐              │
│  │ Orchestrator│──│Worker Agents│              │
│  │  (内部模块)  │  │ (内部模块)   │              │
│  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────┘

Phase 2 (未来): 独立服务
┌──────────────┐    A2A/HTTP    ┌──────────────┐
│ Orchestrator │◀──────────────▶│Worker Agent 1│
│   Service    │                │   Service    │
└──────────────┘                └──────────────┘
       ▲                               ▲
       │          A2A/HTTP             │
       └───────────────────────────────┘
                       │
               ┌───────┴───────┐
               │Worker Agent 2 │
               │   Service     │
               └───────────────┘
```

## Risks / Trade-offs

### Risk 1: A2A同步调用阻塞

**风险**：复杂任务执行时间长，同步等待可能导致用户体验差。

**缓解**：
- 实现流式响应，边执行边返回中间结果
- 设置合理的超时时间（默认30s）
- 返回task_id支持轮询查询进度

---

### Risk 2: LLM Provider依赖

**风险**：主Provider不可用时影响服务可用性。

**缓解**：
- 实现多Provider降级链
- Ollama本地模型作为最终兜底
- Provider健康检查与自动切换

---

### Risk 3: Session状态膨胀

**风险**：长对话Session历史过大，影响Redis性能和LLM上下文限制。

**缓解**：
- 对话历史滑动窗口（保留最近N轮）
- 超过阈值时触发LLM摘要压缩
- 设置Session最大TTL（24h）

---

### Risk 4: Intent识别准确率

**风险**：意图误判导致路由到错误的Agent。

**缓解**：
- confidence阈值过滤，低置信度走LLM兜底
- 持续收集badcase优化规则库
- 支持用户反馈纠正机制

---

### Risk 5: MCP Server连接稳定性

**风险**：外部MCP Server断连影响Tool调用。

**缓解**：
- 启动时健康检查，不健康的Server延迟重连
- Tool执行失败时返回错误让LLM决定下一步
- 可选配置Tool降级策略

## Migration Plan

本项目为新建项目，无需数据迁移。

**部署步骤**：

1. **环境准备**
   - 安装Redis >= 7.0
   - 配置LLM Provider API Keys

2. **配置文件**
   - 创建 `config/llm.yaml`
   - 创建 `config/agents.yaml`
   - 创建 `config/mcp.yaml`

3. **启动服务**
   ```bash
   # 启动Redis
   redis-server
   
   # 启动Agent服务
   python -m dv_agent.main
   ```

4. **验证**
   - 调用 `/api/v1/chat` 测试基础问答
   - 检查A2A端点 `/a2a/*/card` 响应
   - 验证Session持久化与恢复

## Open Questions

1. **Embedding模型选择**
   - Intent识别的Embedding层使用哪个模型？
   - 选项：OpenAI text-embedding-3-small / 本地sentence-transformers

2. **向量数据库选择**
   - Knowledge Agent的RAG需要向量存储，使用哪种？
   - 选项：Chroma（轻量本地）/ Milvus（生产级）/ Qdrant

3. **日志与监控**
   - 是否集成LangSmith进行链路追踪？
   - 日志格式与存储方案？

4. **API认证**
   - REST API是否需要认证？
   - 初期是否跳过认证简化开发？
