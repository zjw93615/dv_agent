"""
工具系统数据模型
定义统一的工具接口和结果格式
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, Type, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolResultStatus(str, Enum):
    """工具执行状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ToolResult(BaseModel):
    """工具执行结果"""
    tool_name: str = Field(..., description="工具名称")
    status: ToolResultStatus = Field(..., description="执行状态")
    output: Optional[Any] = Field(None, description="执行输出")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 执行信息
    execution_time_ms: Optional[float] = Field(None, description="执行耗时(毫秒)")
    tool_call_id: Optional[str] = Field(None, description="工具调用ID")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True
    
    @property
    def is_success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS
    
    @property
    def is_error(self) -> bool:
        return self.status == ToolResultStatus.ERROR
    
    def to_string(self) -> str:
        """转换为字符串（用于 LLM）"""
        if self.is_success:
            if isinstance(self.output, str):
                return self.output
            elif isinstance(self.output, dict):
                import json
                return json.dumps(self.output, ensure_ascii=False, indent=2)
            else:
                return str(self.output)
        else:
            return f"Error: {self.error}"
    
    @classmethod
    def success(
        cls,
        tool_name: str,
        output: Any,
        **kwargs,
    ) -> "ToolResult":
        """创建成功结果"""
        return cls(
            tool_name=tool_name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            **kwargs,
        )
    
    @classmethod
    def error(
        cls,
        tool_name: str,
        error: str,
        **kwargs,
    ) -> "ToolResult":
        """创建错误结果"""
        return cls(
            tool_name=tool_name,
            status=ToolResultStatus.ERROR,
            error=error,
            **kwargs,
        )


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str = Field(..., description="参数名")
    type: str = Field("string", description="参数类型")
    description: str = Field("", description="参数描述")
    required: bool = Field(False, description="是否必需")
    default: Optional[Any] = Field(None, description="默认值")
    enum: Optional[list[str]] = Field(None, description="枚举值")


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: list[ToolParameter] = Field(default_factory=list, description="参数列表")
    
    # 元数据
    category: str = Field("general", description="工具类别")
    version: str = Field("1.0.0", description="版本")
    author: Optional[str] = Field(None, description="作者")
    tags: list[str] = Field(default_factory=list, description="标签")
    
    # 约束
    timeout: float = Field(30.0, description="超时时间(秒)")
    requires_confirmation: bool = Field(False, description="是否需要用户确认")
    is_dangerous: bool = Field(False, description="是否为危险操作")
    
    def to_openai_schema(self) -> dict:
        """转换为 OpenAI Function Calling 格式"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class BaseTool(ABC):
    """
    工具基类
    
    所有工具都需要继承此类并实现 execute 方法
    """
    
    # 子类需要定义
    name: str = "base_tool"
    description: str = "Base tool"
    
    def __init__(self):
        self._definition: Optional[ToolDefinition] = None
    
    @property
    def definition(self) -> ToolDefinition:
        """获取工具定义"""
        if self._definition is None:
            self._definition = self._build_definition()
        return self._definition
    
    def _build_definition(self) -> ToolDefinition:
        """构建工具定义（子类可覆盖）"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self._get_parameters(),
        )
    
    def _get_parameters(self) -> list[ToolParameter]:
        """获取参数定义（子类可覆盖）"""
        return []
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        执行工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    async def validate_params(self, **kwargs) -> Optional[str]:
        """
        验证参数
        
        Returns:
            None 如果验证通过，否则返回错误信息
        """
        for param in self.definition.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            
            if param.name in kwargs and param.enum:
                if kwargs[param.name] not in param.enum:
                    return f"Invalid value for {param.name}: must be one of {param.enum}"
        
        return None
    
    async def __call__(self, **kwargs) -> ToolResult:
        """调用工具"""
        import time
        start_time = time.time()
        
        # 验证参数
        error = await self.validate_params(**kwargs)
        if error:
            return ToolResult.error(self.name, error)
        
        try:
            result = await self.execute(**kwargs)
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            return ToolResult.error(
                self.name,
                str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class FunctionTool(BaseTool):
    """
    函数包装工具
    
    将普通函数包装为工具
    """
    
    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[list[ToolParameter]] = None,
    ):
        super().__init__()
        self._func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or "No description"
        self._parameters = parameters or []
    
    def _get_parameters(self) -> list[ToolParameter]:
        return self._parameters
    
    async def execute(self, **kwargs) -> ToolResult:
        import asyncio
        import inspect
        
        try:
            if asyncio.iscoroutinefunction(self._func):
                output = await self._func(**kwargs)
            else:
                output = self._func(**kwargs)
            
            return ToolResult.success(self.name, output)
        except Exception as e:
            return ToolResult.error(self.name, str(e))


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[list[ToolParameter]] = None,
) -> Callable:
    """
    工具装饰器
    
    用法：
        @tool(name="search", description="Search the web")
        async def search(query: str) -> str:
            ...
    """
    def decorator(func: Callable) -> FunctionTool:
        return FunctionTool(
            func=func,
            name=name,
            description=description,
            parameters=parameters,
        )
    return decorator


class ToolCategory(str, Enum):
    """工具类别"""
    GENERAL = "general"
    WEB = "web"
    FILE = "file"
    CODE = "code"
    DATA = "data"
    SYSTEM = "system"
    CUSTOM = "custom"
