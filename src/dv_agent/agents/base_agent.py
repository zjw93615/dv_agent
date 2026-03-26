"""
BaseAgent 抽象类
定义 Agent 的统一接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING
from datetime import datetime

from ..llm_gateway.gateway import LLMGateway
from ..tools.registry import ToolRegistry
from ..session.models import Session, AgentContext
from ..session.manager import SessionManager
from ..a2a.models import AgentInfo, AgentCapability, TaskResult, TaskState
from .react_loop import ReActLoop, ReActConfig
from ..config.logging import get_logger

if TYPE_CHECKING:
    from ..memory import MemoryManager, MemoryContext

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """Agent 配置"""
    agent_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    
    # ReAct 配置
    max_steps: int = 10
    temperature: float = 0.7
    system_prompt: str = ""
    
    # 能力
    capabilities: list[str] = field(default_factory=list)
    supported_intents: list[str] = field(default_factory=list)
    
    # 限制
    max_concurrent_tasks: int = 10
    timeout: float = 300.0
    
    # 工具
    allowed_tools: Optional[list[str]] = None  # None 表示全部
    
    # 记忆系统配置
    enable_memory: bool = False
    memory_top_k: int = 10
    auto_extract_memory: bool = True  # 任务完成后自动提取记忆
    max_context_tokens: int = 8000  # 上下文最大 token 数，超过时触发压缩
    compress_threshold_ratio: float = 0.8  # 达到 max_context_tokens 的 80% 时开始压缩
    
    # 元数据
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Agent 基类
    
    所有 Agent 都需要继承此类并实现 process 方法
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        session_manager: Optional[SessionManager] = None,
        memory_manager: Optional["MemoryManager"] = None,
    ):
        self.config = config
        self.llm_gateway = llm_gateway
        self.tool_registry = tool_registry
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        
        # 创建 ReAct 循环
        self._react_loop = self._create_react_loop()
        
        # 活跃任务
        self._active_tasks: dict[str, TaskResult] = {}
        
        # 状态
        self._status = "ready"
        
        # 上下文 token 计数（简化估算）
        self._context_token_count: int = 0
        
        logger.info(
            f"Agent initialized",
            agent_id=config.agent_id,
            name=config.name,
            memory_enabled=config.enable_memory and memory_manager is not None,
        )
    
    def _create_react_loop(self) -> ReActLoop:
        """创建 ReAct 循环"""
        react_config = ReActConfig(
            max_steps=self.config.max_steps,
            temperature=self.config.temperature,
            system_prompt=self.config.system_prompt,
        )
        
        # 过滤工具
        registry = self.tool_registry
        if self.config.allowed_tools is not None:
            # 创建子注册表
            registry = ToolRegistry()
            for tool_name in self.config.allowed_tools:
                if self.tool_registry.has(tool_name):
                    registry.register(self.tool_registry.get(tool_name))
        
        return ReActLoop(
            agent_id=self.config.agent_id,
            llm_gateway=self.llm_gateway,
            tool_registry=registry,
            config=react_config,
        )
    
    # ===== 核心方法 =====
    
    @abstractmethod
    async def process(
        self,
        input_text: str,
        session: Optional[Session] = None,
        context: Optional[dict] = None,
    ) -> str:
        """
        处理用户输入
        
        Args:
            input_text: 用户输入
            session: 会话
            context: 额外上下文
            
        Returns:
            str: 响应
        """
        pass
    
    async def run_task(
        self,
        task: str,
        session: Optional[Session] = None,
        context: Optional[AgentContext] = None,
    ) -> tuple[str, AgentContext]:
        """
        执行任务（使用 ReAct 循环）
        
        Args:
            task: 任务描述
            session: 会话
            context: Agent 上下文
            
        Returns:
            tuple[result, context]: 结果和更新的上下文
        """
        # 获取或创建上下文
        if context is None and session:
            context = session.get_agent_context(self.config.agent_id)
        
        # 执行 ReAct 循环
        result, updated_context = await self._react_loop.run(
            task=task,
            context=context,
        )
        
        # 更新会话
        if session and self.session_manager:
            await self.session_manager.update_agent_context(
                session.session_id,
                self.config.agent_id,
                updated_context,
            )
        
        return result, updated_context
    
    # ===== 生命周期 =====
    
    async def start(self) -> None:
        """启动 Agent"""
        self._status = "running"
        logger.info(f"Agent started", agent_id=self.config.agent_id)
    
    async def stop(self) -> None:
        """停止 Agent"""
        self._status = "stopped"
        logger.info(f"Agent stopped", agent_id=self.config.agent_id)
    
    async def pause(self) -> None:
        """暂停 Agent"""
        self._status = "paused"
    
    async def resume(self) -> None:
        """恢复 Agent"""
        self._status = "running"
    
    # ===== 信息 =====
    
    def get_info(self) -> AgentInfo:
        """获取 Agent 信息"""
        return AgentInfo(
            agent_id=self.config.agent_id,
            name=self.config.name,
            description=self.config.description,
            version=self.config.version,
            capabilities=self.config.capabilities,
            supported_methods=["process", "run_task"],
            status=self._status,
            active_tasks=len(self._active_tasks),
            max_concurrent_tasks=self.config.max_concurrent_tasks,
            metadata=self.config.metadata,
        )
    
    def get_capabilities(self) -> list[AgentCapability]:
        """获取能力列表"""
        # 子类可覆盖
        return [
            AgentCapability(
                name="process",
                description="处理用户输入",
            ),
        ]
    
    @property
    def agent_id(self) -> str:
        return self.config.agent_id
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def status(self) -> str:
        return self._status
    
    @property
    def is_ready(self) -> bool:
        return self._status in ("ready", "running")
    
    # ===== 钩子方法 =====
    
    async def on_task_start(
        self,
        task: str,
        session: Optional[Session] = None,
    ) -> None:
        """任务开始钩子"""
        pass
    
    async def on_task_complete(
        self,
        task: str,
        result: str,
        session: Optional[Session] = None,
    ) -> None:
        """任务完成钩子"""
        pass
    
    async def on_task_error(
        self,
        task: str,
        error: Exception,
        session: Optional[Session] = None,
    ) -> None:
        """任务错误钩子"""
        pass
    
    async def on_tool_call(
        self,
        tool_name: str,
        arguments: dict,
    ) -> Optional[dict]:
        """
        工具调用钩子
        
        Returns:
            None 正常执行，dict 覆盖参数
        """
        return None
    
    async def on_tool_result(
        self,
        tool_name: str,
        result: Any,
    ) -> Optional[Any]:
        """
        工具结果钩子
        
        Returns:
            None 正常返回，Any 覆盖结果
        """
        return None
    
    # ===== 记忆系统方法 =====
    
    @property
    def memory_enabled(self) -> bool:
        """检查记忆系统是否启用"""
        return self.config.enable_memory and self.memory_manager is not None
    
    async def get_memory_context(
        self,
        session: Session,
        query: Optional[str] = None,
    ) -> Optional["MemoryContext"]:
        """
        获取记忆上下文
        
        融合短期摘要和长期记忆，用于注入到 LLM prompt 中
        
        Args:
            session: 当前会话
            query: 可选的查询文本，用于检索相关长期记忆
            
        Returns:
            MemoryContext 或 None（如果记忆系统未启用）
        """
        if not self.memory_enabled:
            return None
        
        try:
            context = await self.memory_manager.get_context(
                session_id=session.session_id,
                user_id=session.user_id,
                query=query,
                top_k=self.config.memory_top_k,
            )
            
            # 更新 token 计数估算
            self._update_context_token_count(context)
            
            return context
        except Exception as e:
            logger.error(
                f"Failed to get memory context",
                error=str(e),
                agent_id=self.config.agent_id,
            )
            return None
    
    def _update_context_token_count(self, context: "MemoryContext") -> None:
        """
        更新上下文 token 计数估算
        
        简化估算：1 个字符约 0.5-1 个 token（中英混合）
        """
        total_chars = 0
        
        # 统计短期消息
        for msg in context.short_term_messages:
            total_chars += len(msg.get("content", ""))
        
        # 统计摘要
        if context.summary:
            total_chars += len(context.summary)
        
        # 统计长期记忆
        for memory in context.long_term_memories:
            total_chars += len(memory.content)
        
        # 估算 token 数（保守估计）
        self._context_token_count = int(total_chars * 0.7)
    
    def _should_compress_context(self) -> bool:
        """
        检查是否需要压缩上下文
        
        当上下文 token 数超过阈值时返回 True
        """
        threshold = int(
            self.config.max_context_tokens * 
            self.config.compress_threshold_ratio
        )
        return self._context_token_count > threshold
    
    async def compress_context_if_needed(
        self,
        session: Session,
    ) -> bool:
        """
        如果需要，压缩上下文
        
        当上下文 token 数超过阈值时，触发短期记忆压缩
        
        Args:
            session: 当前会话
            
        Returns:
            bool: 是否执行了压缩
        """
        if not self.memory_enabled:
            return False
        
        if not self._should_compress_context():
            return False
        
        try:
            logger.info(
                f"Context token count exceeds threshold, compressing",
                token_count=self._context_token_count,
                threshold=int(self.config.max_context_tokens * self.config.compress_threshold_ratio),
                agent_id=self.config.agent_id,
                session_id=session.session_id,
            )
            
            # 触发压缩
            await self.memory_manager.compress_short_term(
                session_id=session.session_id,
            )
            
            # 重新计算 token 数
            context = await self.get_memory_context(session)
            
            logger.info(
                f"Context compressed",
                new_token_count=self._context_token_count,
                agent_id=self.config.agent_id,
            )
            
            return True
        except Exception as e:
            logger.error(
                f"Failed to compress context",
                error=str(e),
                agent_id=self.config.agent_id,
            )
            return False
    
    async def extract_and_store_memory(
        self,
        session: Session,
        messages: Optional[list[dict]] = None,
    ) -> int:
        """
        从对话中提取并存储长期记忆
        
        Args:
            session: 当前会话
            messages: 可选的消息列表，不提供则从短期记忆获取
            
        Returns:
            int: 提取的记忆数量
        """
        if not self.memory_enabled:
            return 0
        
        try:
            memories = await self.memory_manager.extract_and_store(
                user_id=session.user_id,
                session_id=session.session_id,
                messages=messages,
            )
            
            if memories:
                logger.info(
                    f"Extracted and stored memories",
                    count=len(memories),
                    agent_id=self.config.agent_id,
                    session_id=session.session_id,
                )
            
            return len(memories)
        except Exception as e:
            logger.error(
                f"Failed to extract memories",
                error=str(e),
                agent_id=self.config.agent_id,
            )
            return 0
    
    def build_memory_prompt_section(
        self,
        context: "MemoryContext",
    ) -> str:
        """
        构建记忆相关的 prompt 部分
        
        Args:
            context: 记忆上下文
            
        Returns:
            格式化的 prompt 文本
        """
        sections = []
        
        # 添加长期记忆
        if context.long_term_memories:
            memory_texts = []
            for memory in context.long_term_memories:
                memory_texts.append(f"- {memory.content}")
            
            sections.append(
                "## User Background (from long-term memory)\n" +
                "\n".join(memory_texts)
            )
        
        # 添加摘要
        if context.summary:
            sections.append(
                f"## Previous Conversation Summary\n{context.summary}"
            )
        
        return "\n\n".join(sections) if sections else ""


class MemoryEnabledAgent(BaseAgent):
    """
    带记忆系统的 Agent 实现
    
    自动在任务开始时获取记忆上下文，
    任务完成后自动提取记忆，
    上下文过大时自动压缩。
    """
    
    async def process(
        self,
        input_text: str,
        session: Optional[Session] = None,
        context: Optional[dict] = None,
    ) -> str:
        """处理用户输入，带记忆系统集成"""
        await self.on_task_start(input_text, session)
        
        try:
            # 获取记忆上下文
            memory_context = None
            if session and self.memory_enabled:
                memory_context = await self.get_memory_context(session, input_text)
                
                # 检查并压缩上下文
                await self.compress_context_if_needed(session)
            
            # 构建增强的上下文
            enhanced_context = context or {}
            if memory_context:
                enhanced_context["memory_prompt"] = self.build_memory_prompt_section(
                    memory_context
                )
                enhanced_context["memory_context"] = memory_context
            
            # 执行任务
            result, _ = await self.run_task(input_text, session)
            
            # 任务完成后提取记忆
            if session and self.config.auto_extract_memory:
                await self.extract_and_store_memory(session)
            
            await self.on_task_complete(input_text, result, session)
            return result
            
        except Exception as e:
            await self.on_task_error(input_text, e, session)
            raise


class SimpleAgent(BaseAgent):
    """
    简单 Agent 实现
    
    直接使用 ReAct 循环处理请求
    """
    
    async def process(
        self,
        input_text: str,
        session: Optional[Session] = None,
        context: Optional[dict] = None,
    ) -> str:
        """处理用户输入"""
        await self.on_task_start(input_text, session)
        
        try:
            result, _ = await self.run_task(input_text, session)
            await self.on_task_complete(input_text, result, session)
            return result
        except Exception as e:
            await self.on_task_error(input_text, e, session)
            raise
