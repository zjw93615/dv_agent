"""
A2A (Agent-to-Agent) 协议数据模型
基于 JSON-RPC 2.0 规范
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class A2AMethod(str, Enum):
    """A2A 请求方法"""
    # Agent 生命周期
    PING = "agent.ping"
    INFO = "agent.info"
    
    # 任务执行
    INVOKE = "task.invoke"
    CANCEL = "task.cancel"
    STATUS = "task.status"
    
    # 消息传递
    MESSAGE = "message.send"
    BROADCAST = "message.broadcast"
    
    # 能力查询
    CAPABILITIES = "agent.capabilities"
    TOOLS = "agent.tools"


class TaskState(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class A2ARequest(BaseModel):
    """
    A2A 请求（JSON-RPC 2.0 格式）
    
    示例：
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "method": "task.invoke",
        "params": {
            "task_type": "search",
            "input": {"query": "AI news"}
        }
    }
    """
    jsonrpc: str = Field("2.0", description="JSON-RPC 版本")
    id: str = Field(default_factory=lambda: str(uuid4()), description="请求ID")
    method: str = Field(..., description="请求方法")
    params: Optional[dict[str, Any]] = Field(None, description="请求参数")
    
    # 扩展字段
    source_agent: Optional[str] = Field(None, description="来源 Agent ID")
    target_agent: Optional[str] = Field(None, description="目标 Agent ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    timeout: Optional[float] = Field(None, description="超时时间(秒)")
    priority: int = Field(0, description="优先级（越大越高）")
    
    # 元数据
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


class A2AError(BaseModel):
    """A2A 错误"""
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    data: Optional[Any] = Field(None, description="错误详情")
    
    # 标准错误码 (JSON-RPC 2.0)
    PARSE_ERROR: ClassVar[int] = -32700
    INVALID_REQUEST: ClassVar[int] = -32600
    METHOD_NOT_FOUND: ClassVar[int] = -32601
    INVALID_PARAMS: ClassVar[int] = -32602
    INTERNAL_ERROR: ClassVar[int] = -32603
    
    # 自定义错误码
    AGENT_NOT_FOUND: ClassVar[int] = -32001
    AGENT_BUSY: ClassVar[int] = -32002
    TASK_NOT_FOUND: ClassVar[int] = -32003
    TASK_TIMEOUT: ClassVar[int] = -32004
    CAPABILITY_NOT_SUPPORTED: ClassVar[int] = -32005
    AUTHENTICATION_FAILED: ClassVar[int] = -32006


class A2AResponse(BaseModel):
    """
    A2A 响应（JSON-RPC 2.0 格式）
    
    成功示例：
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "result": {"status": "completed", "output": {...}}
    }
    
    错误示例：
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "error": {"code": -32603, "message": "Internal error"}
    }
    """
    jsonrpc: str = Field("2.0", description="JSON-RPC 版本")
    id: str = Field(..., description="对应的请求ID")
    result: Optional[Any] = Field(None, description="成功结果")
    error: Optional[A2AError] = Field(None, description="错误信息")
    
    # 扩展字段
    source_agent: Optional[str] = Field(None, description="响应 Agent ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = Field(None, description="处理耗时(毫秒)")
    
    @property
    def is_success(self) -> bool:
        return self.error is None
    
    @classmethod
    def success(
        cls,
        request_id: str,
        result: Any,
        source_agent: Optional[str] = None,
    ) -> "A2AResponse":
        """创建成功响应"""
        return cls(
            id=request_id,
            result=result,
            source_agent=source_agent,
        )
    
    @classmethod
    def failure(
        cls,
        request_id: str,
        code: int,
        message: str,
        data: Optional[Any] = None,
        source_agent: Optional[str] = None,
    ) -> "A2AResponse":
        """创建错误响应"""
        return cls(
            id=request_id,
            error=A2AError(code=code, message=message, data=data),
            source_agent=source_agent,
        )


class TaskInvokeParams(BaseModel):
    """任务调用参数"""
    task_type: str = Field(..., description="任务类型")
    input: dict[str, Any] = Field(default_factory=dict, description="任务输入")
    context: Optional[dict[str, Any]] = Field(None, description="上下文信息")
    
    # 执行控制
    async_mode: bool = Field(False, description="是否异步执行")
    callback_url: Optional[str] = Field(None, description="完成回调URL")
    max_steps: Optional[int] = Field(None, description="最大执行步数")
    timeout: Optional[float] = Field(None, description="任务超时(秒)")


class TaskResult(BaseModel):
    """任务执行结果"""
    task_id: str = Field(..., description="任务ID")
    state: TaskState = Field(..., description="任务状态")
    output: Optional[Any] = Field(None, description="任务输出")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 执行信息
    steps_executed: int = Field(0, description="已执行步数")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    
    # 资源使用
    tokens_used: int = Field(0, description="消耗的token数")
    tools_called: list[str] = Field(default_factory=list, description="调用的工具")
    
    class Config:
        use_enum_values = True
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


class AgentInfo(BaseModel):
    """Agent 信息"""
    agent_id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    description: Optional[str] = Field(None, description="Agent 描述")
    version: str = Field("1.0.0", description="版本号")
    
    # 能力
    capabilities: list[str] = Field(default_factory=list, description="支持的能力")
    supported_methods: list[str] = Field(default_factory=list, description="支持的方法")
    
    # 状态
    status: str = Field("ready", description="当前状态")
    active_tasks: int = Field(0, description="活跃任务数")
    max_concurrent_tasks: int = Field(10, description="最大并发任务数")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCapability(BaseModel):
    """Agent 能力定义"""
    name: str = Field(..., description="能力名称")
    description: str = Field("", description="能力描述")
    input_schema: Optional[dict] = Field(None, description="输入参数 schema")
    output_schema: Optional[dict] = Field(None, description="输出参数 schema")
    
    # 约束
    max_input_tokens: Optional[int] = Field(None, description="最大输入 token")
    estimated_latency_ms: Optional[int] = Field(None, description="预估延迟")
    requires_tools: list[str] = Field(default_factory=list, description="依赖的工具")
