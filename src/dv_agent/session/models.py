"""
Session 数据模型
定义会话、对话历史和 Agent 状态
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..memory.models import SessionMemoryConfig


class SessionState(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"


class MessageType(str, Enum):
    """消息类型"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THOUGHT = "thought"
    ERROR = "error"


class ConversationMessage(BaseModel):
    """对话消息"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="消息ID")
    type: MessageType = Field(..., description="消息类型")
    content: str = Field(..., description="消息内容")
    
    # 扩展字段
    role: Optional[str] = Field(None, description="角色（兼容 LLM 格式）")
    name: Optional[str] = Field(None, description="发送者名称")
    tool_call_id: Optional[str] = Field(None, description="工具调用ID")
    tool_name: Optional[str] = Field(None, description="工具名称")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class ConversationHistory(BaseModel):
    """对话历史"""
    session_id: str = Field(..., description="会话ID")
    messages: list[ConversationMessage] = Field(default_factory=list, description="消息列表")
    
    # 统计
    total_tokens: int = Field(0, description="总 token 数")
    message_count: int = Field(0, description="消息数量")
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def add_message(self, message: ConversationMessage) -> None:
        """添加消息"""
        self.messages.append(message)
        self.message_count = len(self.messages)
        self.updated_at = datetime.utcnow()
    
    def add_user_message(self, content: str, **kwargs) -> ConversationMessage:
        """添加用户消息"""
        msg = ConversationMessage(
            type=MessageType.USER,
            role="user",
            content=content,
            **kwargs,
        )
        self.add_message(msg)
        return msg
    
    def add_assistant_message(self, content: str, **kwargs) -> ConversationMessage:
        """添加助手消息"""
        msg = ConversationMessage(
            type=MessageType.ASSISTANT,
            role="assistant",
            content=content,
            **kwargs,
        )
        self.add_message(msg)
        return msg
    
    def add_tool_call(
        self,
        tool_name: str,
        arguments: str,
        tool_call_id: str,
        **kwargs,
    ) -> ConversationMessage:
        """添加工具调用"""
        msg = ConversationMessage(
            type=MessageType.TOOL_CALL,
            role="assistant",
            content=arguments,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            **kwargs,
        )
        self.add_message(msg)
        return msg
    
    def add_tool_result(
        self,
        tool_call_id: str,
        result: str,
        tool_name: Optional[str] = None,
        **kwargs,
    ) -> ConversationMessage:
        """添加工具结果"""
        msg = ConversationMessage(
            type=MessageType.TOOL_RESULT,
            role="tool",
            content=result,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            **kwargs,
        )
        self.add_message(msg)
        return msg
    
    def get_last_n(self, n: int) -> list[ConversationMessage]:
        """获取最后 n 条消息"""
        return self.messages[-n:] if n > 0 else []
    
    def get_messages_by_type(self, msg_type: MessageType) -> list[ConversationMessage]:
        """按类型过滤消息"""
        return [m for m in self.messages if m.type == msg_type]
    
    def to_llm_messages(self) -> list[dict]:
        """转换为 LLM 消息格式"""
        llm_messages = []
        for msg in self.messages:
            if msg.type in (MessageType.USER, MessageType.ASSISTANT, MessageType.SYSTEM):
                llm_messages.append({
                    "role": msg.role or msg.type.value,
                    "content": msg.content,
                })
            elif msg.type == MessageType.TOOL_RESULT:
                llm_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
        return llm_messages
    
    def clear(self) -> None:
        """清空历史"""
        self.messages = []
        self.message_count = 0
        self.total_tokens = 0
        self.updated_at = datetime.utcnow()


class ReActStep(BaseModel):
    """ReAct 循环步骤"""
    step_number: int = Field(..., description="步骤编号")
    thought: Optional[str] = Field(None, description="思考")
    action: Optional[str] = Field(None, description="动作（工具名）")
    action_input: Optional[dict[str, Any]] = Field(None, description="动作输入")
    observation: Optional[str] = Field(None, description="观察结果")
    
    # 状态
    status: str = Field("pending", description="步骤状态")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 时间
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None)
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


class AgentContext(BaseModel):
    """Agent 执行上下文"""
    agent_id: str = Field(..., description="Agent ID")
    current_task: Optional[str] = Field(None, description="当前任务描述")
    
    # ReAct 状态
    react_steps: list[ReActStep] = Field(default_factory=list, description="ReAct 步骤")
    current_step: int = Field(0, description="当前步骤")
    max_steps: int = Field(10, description="最大步骤数")
    
    # 工具状态
    available_tools: list[str] = Field(default_factory=list, description="可用工具")
    called_tools: list[str] = Field(default_factory=list, description="已调用工具")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # 时间
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def add_react_step(
        self,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        action_input: Optional[dict] = None,
    ) -> ReActStep:
        """添加 ReAct 步骤"""
        step = ReActStep(
            step_number=len(self.react_steps) + 1,
            thought=thought,
            action=action,
            action_input=action_input,
        )
        self.react_steps.append(step)
        self.current_step = len(self.react_steps)
        self.updated_at = datetime.utcnow()
        return step
    
    def complete_current_step(
        self,
        observation: str,
        error: Optional[str] = None,
    ) -> None:
        """完成当前步骤"""
        if self.react_steps:
            step = self.react_steps[-1]
            step.observation = observation
            step.status = "error" if error else "completed"
            step.error = error
            step.completed_at = datetime.utcnow()
            self.updated_at = datetime.utcnow()
    
    @property
    def is_complete(self) -> bool:
        """是否完成（达到最大步骤或最后步骤无 action）"""
        if self.current_step >= self.max_steps:
            return True
        if self.react_steps:
            last_step = self.react_steps[-1]
            return last_step.action is None and last_step.status == "completed"
        return False


class Session(BaseModel):
    """会话"""
    session_id: str = Field(default_factory=lambda: str(uuid4()), description="会话ID")
    user_id: Optional[str] = Field(None, description="用户ID")
    
    # 状态
    state: SessionState = Field(SessionState.ACTIVE, description="会话状态")
    
    # 对话历史
    history: ConversationHistory = Field(default_factory=lambda: ConversationHistory(session_id=""))
    
    # Agent 上下文（按 agent_id 存储）
    agent_contexts: dict[str, AgentContext] = Field(default_factory=dict)
    
    # 元数据
    title: Optional[str] = Field(None, description="会话标题")
    tags: list[str] = Field(default_factory=list, description="标签")
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    
    # TTL（秒）
    ttl: int = Field(3600 * 24, description="TTL（秒）")
    
    # 记忆系统配置
    memory_config: Optional[dict[str, Any]] = Field(None, description="记忆系统配置")
    
    # 短期记忆摘要（压缩后的历史）
    summary: Optional[str] = Field(None, description="对话历史摘要")
    summary_updated_at: Optional[datetime] = Field(None, description="摘要更新时间")
    
    class Config:
        use_enum_values = True
    
    def __init__(self, **data):
        super().__init__(**data)
        # 确保 history 的 session_id 正确
        if self.history.session_id != self.session_id:
            self.history.session_id = self.session_id
    
    def get_agent_context(self, agent_id: str) -> AgentContext:
        """获取或创建 Agent 上下文"""
        if agent_id not in self.agent_contexts:
            self.agent_contexts[agent_id] = AgentContext(agent_id=agent_id)
        return self.agent_contexts[agent_id]
    
    def touch(self) -> None:
        """更新活跃时间"""
        self.last_active_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def pause(self) -> None:
        """暂停会话"""
        self.state = SessionState.PAUSED
        self.updated_at = datetime.utcnow()
    
    def resume(self) -> None:
        """恢复会话"""
        self.state = SessionState.ACTIVE
        self.touch()
    
    def complete(self) -> None:
        """完成会话"""
        self.state = SessionState.COMPLETED
        self.updated_at = datetime.utcnow()
    
    @property
    def is_expired(self) -> bool:
        """是否过期"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @property
    def is_active(self) -> bool:
        """是否活跃"""
        return self.state == SessionState.ACTIVE and not self.is_expired
    
    def can_resume(self) -> bool:
        """是否可恢复"""
        return self.state in (SessionState.ACTIVE, SessionState.PAUSED) and not self.is_expired
    
    def get_resumable_context(self) -> Optional[dict]:
        """获取可恢复的上下文（用于恢复提示）"""
        if not self.can_resume():
            return None
        
        # 收集未完成的任务
        pending_tasks = []
        for agent_id, ctx in self.agent_contexts.items():
            if ctx.current_task and not ctx.is_complete:
                pending_tasks.append({
                    "agent_id": agent_id,
                    "task": ctx.current_task,
                    "steps_completed": ctx.current_step,
                    "last_action": ctx.react_steps[-1].action if ctx.react_steps else None,
                })
        
        return {
            "session_id": self.session_id,
            "title": self.title,
            "message_count": self.history.message_count,
            "pending_tasks": pending_tasks,
            "last_active": self.last_active_at.isoformat(),
        } if pending_tasks else None
