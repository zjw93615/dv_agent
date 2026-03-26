"""
ReAct 循环实现
基于 LangGraph 的 Thought-Action-Observation 状态机
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from ..llm_gateway.models import Message, MessageRole, LLMRequest, LLMResponse, ToolCall
from ..llm_gateway.gateway import LLMGateway
from ..tools.registry import ToolRegistry
from ..tools.models import ToolResult
from ..session.models import ReActStep, AgentContext
from ..config.exceptions import ReActLoopError, ReActMaxStepsError
from ..config.logging import get_logger

logger = get_logger(__name__)


class ReActPhase(str, Enum):
    """ReAct 阶段"""
    THINK = "think"
    ACT = "act"
    OBSERVE = "observe"
    DONE = "done"
    ERROR = "error"


class ReActState(TypedDict):
    """ReAct 状态（LangGraph 状态）"""
    # 消息历史
    messages: Annotated[list[dict], add_messages]
    
    # 当前阶段
    phase: str
    
    # 当前步骤
    step: int
    max_steps: int
    
    # 思考
    thought: Optional[str]
    
    # 动作
    action: Optional[str]
    action_input: Optional[dict]
    tool_calls: Optional[list[dict]]
    
    # 观察
    observation: Optional[str]
    
    # 最终答案
    final_answer: Optional[str]
    
    # 错误
    error: Optional[str]
    
    # 元数据
    agent_id: str
    task: str
    metadata: dict


@dataclass
class ReActConfig:
    """ReAct 配置"""
    max_steps: int = 10
    thinking_prompt: str = ""
    system_prompt: str = ""
    temperature: float = 0.7
    timeout_per_step: float = 30.0
    stop_on_error: bool = False


class ReActLoop:
    """
    ReAct 循环实现
    
    流程：
    Thought -> Action -> Observation -> (repeat) -> Final Answer
    
    使用 LangGraph 构建状态机
    """
    
    def __init__(
        self,
        agent_id: str,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        config: Optional[ReActConfig] = None,
    ):
        self.agent_id = agent_id
        self.llm_gateway = llm_gateway
        self.tool_registry = tool_registry
        self.config = config or ReActConfig()
        
        # 构建状态图
        self._graph = self._build_graph()
        self._compiled = self._graph.compile()
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        graph = StateGraph(ReActState)
        
        # 添加节点
        graph.add_node("think", self._think_node)
        graph.add_node("act", self._act_node)
        graph.add_node("observe", self._observe_node)
        graph.add_node("done", self._done_node)
        graph.add_node("error", self._error_node)
        
        # 添加边
        graph.add_conditional_edges(
            "think",
            self._route_after_think,
            {
                "act": "act",
                "done": "done",
                "error": "error",
            }
        )
        
        graph.add_edge("act", "observe")
        
        graph.add_conditional_edges(
            "observe",
            self._route_after_observe,
            {
                "think": "think",
                "done": "done",
                "error": "error",
            }
        )
        
        graph.add_edge("done", END)
        graph.add_edge("error", END)
        
        # 设置入口
        graph.set_entry_point("think")
        
        return graph
    
    async def run(
        self,
        task: str,
        context: Optional[AgentContext] = None,
        messages: Optional[list[Message]] = None,
    ) -> tuple[str, AgentContext]:
        """
        执行 ReAct 循环
        
        Args:
            task: 任务描述
            context: Agent 上下文（用于恢复）
            messages: 初始消息
            
        Returns:
            tuple[final_answer, updated_context]: 最终答案和更新的上下文
        """
        # 初始化上下文
        if context is None:
            context = AgentContext(
                agent_id=self.agent_id,
                current_task=task,
                max_steps=self.config.max_steps,
            )
        
        # 初始状态
        initial_state = self._create_initial_state(task, context, messages)
        
        logger.info(
            f"ReAct loop started",
            agent=self.agent_id,
            task=task[:100],
            max_steps=self.config.max_steps,
        )
        
        # 执行状态机
        try:
            final_state = await self._compiled.ainvoke(initial_state)
            
            # 更新上下文
            context.current_step = final_state["step"]
            
            final_answer = final_state.get("final_answer", "")
            
            logger.info(
                f"ReAct loop completed",
                agent=self.agent_id,
                steps=final_state["step"],
                phase=final_state["phase"],
            )
            
            return final_answer, context
            
        except Exception as e:
            logger.exception(f"ReAct loop failed", agent=self.agent_id)
            raise ReActLoopError(
                message=str(e),
                agent_id=self.agent_id,
                step=context.current_step,
            )
    
    def _create_initial_state(
        self,
        task: str,
        context: AgentContext,
        messages: Optional[list[Message]] = None,
    ) -> ReActState:
        """创建初始状态"""
        # 系统提示
        system_message = self._build_system_prompt(task)
        
        initial_messages = [
            {"role": "system", "content": system_message},
        ]
        
        # 添加历史消息
        if messages:
            for msg in messages:
                initial_messages.append({
                    "role": msg.role if isinstance(msg.role, str) else msg.role.value,
                    "content": msg.content,
                })
        
        # 添加任务
        initial_messages.append({
            "role": "user",
            "content": task,
        })
        
        return ReActState(
            messages=initial_messages,
            phase=ReActPhase.THINK.value,
            step=context.current_step,
            max_steps=self.config.max_steps,
            thought=None,
            action=None,
            action_input=None,
            tool_calls=None,
            observation=None,
            final_answer=None,
            error=None,
            agent_id=self.agent_id,
            task=task,
            metadata={},
        )
    
    def _build_system_prompt(self, task: str) -> str:
        """构建系统提示"""
        tools = self.tool_registry.get_definitions()
        tool_descriptions = []
        for t in tools:
            params_desc = ", ".join([
                f"{p.name}: {p.type}" + (" (required)" if p.required else "")
                for p in t.parameters
            ])
            tool_descriptions.append(f"- {t.name}: {t.description}\n  参数: {params_desc}")
        
        tools_text = "\n".join(tool_descriptions) if tool_descriptions else "无可用工具"
        
        base_prompt = self.config.system_prompt or """你是一个智能助手，使用 ReAct 方法解决问题。

对于每个任务：
1. 思考 (Thought): 分析问题，决定下一步行动
2. 行动 (Action): 调用工具执行操作
3. 观察 (Observation): 查看工具返回结果
4. 重复直到得到最终答案

如果你认为已经有了足够的信息来回答问题，直接给出最终答案，不要调用工具。
"""
        
        return f"""{base_prompt}

可用工具：
{tools_text}

记住：
- 每次只执行一个动作
- 仔细分析观察结果
- 如果工具调用失败，尝试其他方法
- 达到最大步数前给出答案
"""
    
    async def _think_node(self, state: ReActState) -> dict:
        """思考节点：决定下一步行动"""
        step = state["step"] + 1
        
        # 检查步数限制
        if step > state["max_steps"]:
            return {
                "phase": ReActPhase.ERROR.value,
                "error": f"Exceeded max steps ({state['max_steps']})",
                "step": step,
            }
        
        # 调用 LLM
        tools = self.tool_registry.get_openai_tools()
        
        request = LLMRequest(
            messages=[Message(**m) for m in state["messages"]],
            tools=tools if tools else None,
            temperature=self.config.temperature,
        )
        
        response = await self.llm_gateway.complete(request)
        
        # 解析响应
        if response.has_tool_calls:
            # 有工具调用
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in response.tool_calls
            ]
            
            return {
                "phase": ReActPhase.ACT.value,
                "thought": response.content,
                "tool_calls": tool_calls,
                "action": tool_calls[0]["name"] if tool_calls else None,
                "action_input": json.loads(tool_calls[0]["arguments"]) if tool_calls else None,
                "step": step,
                "messages": [response.to_message().model_dump()],
            }
        else:
            # 直接回答
            return {
                "phase": ReActPhase.DONE.value,
                "thought": response.content,
                "final_answer": response.content,
                "step": step,
                "messages": [response.to_message().model_dump()],
            }
    
    async def _act_node(self, state: ReActState) -> dict:
        """行动节点：执行工具"""
        tool_calls = state.get("tool_calls", [])
        
        if not tool_calls:
            return {
                "phase": ReActPhase.ERROR.value,
                "error": "No tool calls to execute",
            }
        
        # 执行所有工具调用
        results = []
        for tc in tool_calls:
            result = await self.tool_registry.execute(
                name=tc["name"],
                arguments=tc["arguments"],
                tool_call_id=tc["id"],
            )
            results.append(result)
        
        # 构建观察消息
        observation_messages = []
        observation_text = []
        
        for tc, result in zip(tool_calls, results):
            content = result.to_string()
            observation_messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": tc["id"],
            })
            observation_text.append(f"[{tc['name']}]: {content}")
        
        return {
            "phase": ReActPhase.OBSERVE.value,
            "observation": "\n".join(observation_text),
            "messages": observation_messages,
        }
    
    async def _observe_node(self, state: ReActState) -> dict:
        """观察节点：处理工具结果"""
        # 观察结果已经在 act 节点添加到消息
        # 这里只是一个过渡节点
        return {
            "phase": ReActPhase.THINK.value,
        }
    
    async def _done_node(self, state: ReActState) -> dict:
        """完成节点"""
        return {
            "phase": ReActPhase.DONE.value,
        }
    
    async def _error_node(self, state: ReActState) -> dict:
        """错误节点"""
        error = state.get("error", "Unknown error")
        logger.error(f"ReAct loop error", agent=self.agent_id, error=error)
        
        return {
            "phase": ReActPhase.ERROR.value,
            "final_answer": f"执行过程中出错: {error}",
        }
    
    def _route_after_think(self, state: ReActState) -> str:
        """思考后的路由"""
        phase = state.get("phase", "")
        
        if phase == ReActPhase.ACT.value:
            return "act"
        elif phase == ReActPhase.DONE.value:
            return "done"
        elif phase == ReActPhase.ERROR.value:
            return "error"
        else:
            return "done"
    
    def _route_after_observe(self, state: ReActState) -> str:
        """观察后的路由"""
        step = state.get("step", 0)
        max_steps = state.get("max_steps", 10)
        
        if step >= max_steps:
            return "done"
        
        phase = state.get("phase", "")
        
        if phase == ReActPhase.ERROR.value:
            return "error"
        
        return "think"
