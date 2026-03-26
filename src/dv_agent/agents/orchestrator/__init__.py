"""
Orchestrator Agent
多 Agent 协调器，负责任务分发和结果整合
"""

from typing import Any, Optional
from datetime import datetime

from ..base_agent import BaseAgent, AgentConfig
from ...llm_gateway.gateway import LLMGateway
from ...llm_gateway.models import LLMRequest, Message, MessageRole
from ...tools.registry import ToolRegistry
from ...session.models import Session, AgentContext
from ...session.manager import SessionManager
from ...intent.models import IntentResult, IntentType
from ...intent.router import IntentRouter, get_intent_router
from ...a2a.client import A2AClient, A2AClientPool
from ...a2a.models import TaskResult, TaskState
from ...config.logging import get_logger

logger = get_logger(__name__)


class Orchestrator(BaseAgent):
    """
    Orchestrator Agent
    
    功能：
    - 接收用户请求
    - 意图识别和路由
    - 任务分发到 Worker Agent
    - 结果整合和返回
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        session_manager: Optional[SessionManager] = None,
        intent_router: Optional[IntentRouter] = None,
    ):
        super().__init__(config, llm_gateway, tool_registry, session_manager)
        
        # 意图路由器
        self.intent_router = intent_router or get_intent_router()
        
        # Worker Agent 注册表
        self._workers: dict[str, BaseAgent] = {}
        
        # A2A 客户端池（用于远程 Agent）
        self._a2a_pool = A2AClientPool(source_agent_id=config.agent_id)
        
        # 远程 Agent URL
        self._remote_agents: dict[str, str] = {}
    
    # ===== Worker 管理 =====
    
    def register_worker(self, agent: BaseAgent) -> None:
        """注册本地 Worker Agent"""
        self._workers[agent.agent_id] = agent
        logger.info(f"Worker registered", agent_id=agent.agent_id)
    
    def unregister_worker(self, agent_id: str) -> None:
        """注销 Worker Agent"""
        if agent_id in self._workers:
            del self._workers[agent_id]
            logger.info(f"Worker unregistered", agent_id=agent_id)
    
    def register_remote_agent(self, agent_id: str, url: str) -> None:
        """注册远程 Agent"""
        self._remote_agents[agent_id] = url
        logger.info(f"Remote agent registered", agent_id=agent_id, url=url)
    
    def get_worker(self, agent_id: str) -> Optional[BaseAgent]:
        """获取 Worker Agent"""
        return self._workers.get(agent_id)
    
    # ===== 核心处理 =====
    
    async def process(
        self,
        input_text: str,
        session: Optional[Session] = None,
        context: Optional[dict] = None,
    ) -> str:
        """处理用户请求"""
        await self.on_task_start(input_text, session)
        
        try:
            # 1. 意图识别和路由
            target_agent_id, intent_result = await self.intent_router.route(
                input_text,
                context,
            )
            
            logger.info(
                f"Intent routed",
                intent=intent_result.intent_type.value,
                confidence=intent_result.confidence,
                target=target_agent_id,
            )
            
            # 2. 分发任务
            result = await self._dispatch_task(
                target_agent_id,
                input_text,
                intent_result,
                session,
                context,
            )
            
            # 3. 记录到会话
            if session and self.session_manager:
                await self.session_manager.add_user_message(
                    session.session_id,
                    input_text,
                )
                await self.session_manager.add_assistant_message(
                    session.session_id,
                    result,
                    metadata={
                        "agent_id": target_agent_id,
                        "intent": intent_result.intent_type.value,
                    },
                )
            
            await self.on_task_complete(input_text, result, session)
            return result
            
        except Exception as e:
            await self.on_task_error(input_text, e, session)
            logger.exception(f"Orchestrator process failed")
            return f"处理请求时出错: {str(e)}"
    
    async def _dispatch_task(
        self,
        agent_id: str,
        input_text: str,
        intent_result: IntentResult,
        session: Optional[Session] = None,
        context: Optional[dict] = None,
    ) -> str:
        """分发任务到目标 Agent"""
        
        # 1. 检查是否是自己处理
        if agent_id == self.config.agent_id or agent_id == "orchestrator":
            return await self._handle_directly(input_text, intent_result, session)
        
        # 2. 本地 Worker
        if agent_id in self._workers:
            worker = self._workers[agent_id]
            return await worker.process(input_text, session, context)
        
        # 3. 远程 Agent（A2A）
        if agent_id in self._remote_agents:
            return await self._invoke_remote_agent(
                agent_id,
                input_text,
                intent_result,
            )
        
        # 4. 未找到 Agent，自己处理
        logger.warning(f"Agent not found, handling directly", agent_id=agent_id)
        return await self._handle_directly(input_text, intent_result, session)
    
    async def _handle_directly(
        self,
        input_text: str,
        intent_result: IntentResult,
        session: Optional[Session] = None,
    ) -> str:
        """Orchestrator 直接处理"""
        intent_type = intent_result.intent_type
        
        # 特殊意图处理
        if intent_type == IntentType.GREETING:
            return "你好！我是智能助手，有什么可以帮你的吗？"
        
        elif intent_type == IntentType.FAREWELL:
            return "再见！有问题随时找我。"
        
        elif intent_type == IntentType.HELP:
            return self._get_help_message()
        
        elif intent_type == IntentType.CANCEL:
            return "好的，已取消当前操作。"
        
        # 通用处理：使用 ReAct
        result, _ = await self.run_task(input_text, session)
        return result
    
    async def _invoke_remote_agent(
        self,
        agent_id: str,
        input_text: str,
        intent_result: IntentResult,
    ) -> str:
        """调用远程 Agent"""
        url = self._remote_agents.get(agent_id)
        if not url:
            return f"远程 Agent 未配置: {agent_id}"
        
        try:
            client = await self._a2a_pool.get_client(url)
            
            task_result = await client.invoke_task(
                task_type=intent_result.intent_type.value,
                input_data={
                    "text": input_text,
                    "intent": intent_result.model_dump(mode="json"),
                },
                timeout=self.config.timeout,
            )
            
            if task_result.state == TaskState.COMPLETED:
                return str(task_result.output)
            else:
                return f"远程任务执行失败: {task_result.error}"
                
        except Exception as e:
            logger.error(f"Remote agent invoke failed", agent_id=agent_id, error=str(e))
            return f"远程 Agent 调用失败: {str(e)}"
    
    def _get_help_message(self) -> str:
        """获取帮助信息"""
        worker_info = []
        for agent_id, worker in self._workers.items():
            worker_info.append(f"- {worker.name}: {worker.config.description}")
        
        workers_text = "\n".join(worker_info) if worker_info else "暂无专门的助手"
        
        return f"""我是智能助手，可以帮你完成各种任务：

**可用助手：**
{workers_text}

**支持的功能：**
- 搜索信息
- 代码编写和调试
- 文件操作
- 数据处理
- 文本创作和翻译
- 问答对话

直接告诉我你想做什么吧！"""
    
    # ===== 多任务处理 =====
    
    async def process_multi_turn(
        self,
        messages: list[dict],
        session: Optional[Session] = None,
    ) -> str:
        """处理多轮对话"""
        if not messages:
            return "请输入您的问题"
        
        # 获取最后一条用户消息
        last_user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break
        
        if not last_user_message:
            return "请输入您的问题"
        
        # 构建上下文
        context = {
            "history": messages[:-1],  # 排除最后一条
        }
        
        return await self.process(last_user_message, session, context)
    
    async def delegate_subtask(
        self,
        agent_id: str,
        subtask: str,
        parent_session: Optional[Session] = None,
    ) -> str:
        """委派子任务"""
        # 创建子任务的意图结果
        intent_result = IntentResult(
            primary_intent={"type": IntentType.TASK.value, "confidence": 1.0, "source": "delegation"},
            input_text=subtask,
            used_method="direct",
        )
        
        return await self._dispatch_task(
            agent_id,
            subtask,
            intent_result,
            parent_session,
        )
    
    # ===== 生命周期 =====
    
    async def start(self) -> None:
        """启动 Orchestrator"""
        await super().start()
        
        # 启动所有 Worker
        for worker in self._workers.values():
            await worker.start()
    
    async def stop(self) -> None:
        """停止 Orchestrator"""
        # 停止所有 Worker
        for worker in self._workers.values():
            await worker.stop()
        
        # 关闭 A2A 连接
        await self._a2a_pool.close()
        
        await super().stop()


def create_orchestrator(
    llm_gateway: LLMGateway,
    tool_registry: ToolRegistry,
    session_manager: Optional[SessionManager] = None,
    **kwargs,
) -> Orchestrator:
    """创建 Orchestrator 实例"""
    config = AgentConfig(
        agent_id="orchestrator",
        name="Orchestrator",
        description="多 Agent 协调器",
        capabilities=["routing", "delegation", "aggregation"],
        **kwargs,
    )
    
    return Orchestrator(
        config=config,
        llm_gateway=llm_gateway,
        tool_registry=tool_registry,
        session_manager=session_manager,
    )


# 导出
__all__ = ["Orchestrator", "create_orchestrator"]