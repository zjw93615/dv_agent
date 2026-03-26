"""
LLM Gateway 核心数据模型
定义统一的消息格式和响应结构
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """工具调用"""
    id: str = Field(..., description="工具调用ID")
    name: str = Field(..., description="工具名称")
    arguments: str = Field(..., description="工具参数JSON字符串")


class Message(BaseModel):
    """统一消息格式"""
    role: MessageRole = Field(..., description="消息角色")
    content: Optional[str] = Field(None, description="消息内容")
    name: Optional[str] = Field(None, description="发送者名称（tool时使用）")
    tool_calls: Optional[list[ToolCall]] = Field(None, description="工具调用列表")
    tool_call_id: Optional[str] = Field(None, description="工具调用ID（tool角色时使用）")
    
    class Config:
        use_enum_values = True


class TokenUsage(BaseModel):
    """Token使用量"""
    prompt_tokens: int = Field(0, description="输入token数")
    completion_tokens: int = Field(0, description="输出token数")
    total_tokens: int = Field(0, description="总token数")
    
    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0


class LLMResponse(BaseModel):
    """LLM响应"""
    content: Optional[str] = Field(None, description="响应内容")
    tool_calls: Optional[list[ToolCall]] = Field(None, description="工具调用列表")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token使用量")
    model: str = Field("", description="使用的模型名称")
    provider: str = Field("", description="Provider名称")
    finish_reason: Optional[str] = Field(None, description="结束原因")
    
    # 元数据
    request_id: Optional[str] = Field(None, description="请求ID")
    latency_ms: Optional[float] = Field(None, description="响应延迟(毫秒)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
    
    def to_message(self) -> Message:
        """转换为Message格式"""
        return Message(
            role=MessageRole.ASSISTANT,
            content=self.content,
            tool_calls=self.tool_calls,
        )


class StreamChunk(BaseModel):
    """流式响应块"""
    content: Optional[str] = Field(None, description="增量内容")
    tool_calls: Optional[list[ToolCall]] = Field(None, description="工具调用增量")
    finish_reason: Optional[str] = Field(None, description="结束原因")
    
    # 元数据
    index: int = Field(0, description="块索引")
    model: str = Field("", description="模型名称")
    provider: str = Field("", description="Provider名称")
    
    @property
    def is_done(self) -> bool:
        return self.finish_reason is not None


class ToolDefinition(BaseModel):
    """工具定义（OpenAI Function Calling格式）"""
    type: str = Field("function", description="工具类型")
    function: dict = Field(..., description="函数定义")
    
    @classmethod
    def from_schema(
        cls,
        name: str,
        description: str,
        parameters: dict,
    ) -> "ToolDefinition":
        """从schema创建工具定义"""
        return cls(
            type="function",
            function={
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )


class LLMRequest(BaseModel):
    """LLM请求"""
    messages: list[Message] = Field(..., description="消息列表")
    tools: Optional[list[ToolDefinition]] = Field(None, description="可用工具")
    tool_choice: Optional[Union[str, dict]] = Field(None, description="工具选择策略")
    
    # 生成参数
    model: Optional[str] = Field(None, description="指定模型")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="温度")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大token数")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="Top-p采样")
    
    # 控制参数
    stream: bool = Field(False, description="是否流式")
    timeout: Optional[float] = Field(None, description="超时时间(秒)")
    
    # 元数据
    request_id: Optional[str] = Field(None, description="请求ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class ProviderConfig(BaseModel):
    """Provider配置"""
    type: str = Field(..., description="Provider类型")
    api_key: Optional[str] = Field(None, description="API密钥")
    base_url: Optional[str] = Field(None, description="API基础URL")
    model: str = Field(..., description="默认模型")
    timeout: int = Field(30, description="超时时间(秒)")
    max_retries: int = Field(3, description="最大重试次数")
    temperature: float = Field(0.7, description="默认温度")
    max_tokens: int = Field(4096, description="默认最大token数")
    
    # 额外配置
    extra: dict[str, Any] = Field(default_factory=dict, description="额外配置")


class RetryConfig(BaseModel):
    """重试配置"""
    max_retries: int = Field(3, description="最大重试次数")
    base_delay: float = Field(1.0, description="基础延迟(秒)")
    max_delay: float = Field(30.0, description="最大延迟(秒)")
    exponential_base: int = Field(2, description="指数退避基数")
    jitter: bool = Field(True, description="是否添加随机抖动")
    
    retryable_errors: list[str] = Field(
        default_factory=lambda: [
            "RateLimitError",
            "TimeoutError", 
            "ServiceUnavailableError",
            "ConnectionError",
        ],
        description="可重试的错误类型"
    )
    
    non_retryable_errors: list[str] = Field(
        default_factory=lambda: [
            "InvalidRequestError",
            "AuthenticationError",
            "ContentPolicyViolation",
        ],
        description="不可重试的错误类型"
    )
