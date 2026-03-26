"""
工具注册表
管理工具的注册、发现和执行
"""

import json
import asyncio
from typing import Any, Callable, Optional, Type, Union

from .models import (
    BaseTool,
    ToolResult,
    ToolDefinition,
    ToolParameter,
    FunctionTool,
    ToolCategory,
    ToolResultStatus,
)
from ..config.exceptions import ToolNotFoundError, ToolExecutionError
from ..config.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """
    工具注册表
    
    功能：
    - 工具注册和管理
    - 工具发现和查询
    - 统一执行接口
    """
    
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}
    
    # ===== 注册 =====
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        name = tool.name
        
        if name in self._tools:
            logger.warning(f"Tool already registered, overwriting: {name}")
        
        self._tools[name] = tool
        
        # 分类索引
        category = tool.definition.category
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)
        
        logger.debug(f"Tool registered: {name}")
    
    def register_function(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[list[ToolParameter]] = None,
    ) -> FunctionTool:
        """注册函数作为工具"""
        tool = FunctionTool(
            func=func,
            name=name,
            description=description,
            parameters=parameters,
        )
        self.register(tool)
        return tool
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False
        
        tool = self._tools.pop(name)
        
        # 更新分类索引
        category = tool.definition.category
        if category in self._categories:
            if name in self._categories[category]:
                self._categories[category].remove(name)
        
        logger.debug(f"Tool unregistered: {name}")
        return True
    
    # ===== 查询 =====
    
    def get(self, name: str) -> BaseTool:
        """获取工具"""
        if name not in self._tools:
            raise ToolNotFoundError(
                message=f"Tool not found: {name}",
                tool_name=name,
            )
        return self._tools[name]
    
    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools
    
    def list_tools(
        self,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[str]:
        """列出工具名称"""
        if category:
            names = self._categories.get(category, [])
        else:
            names = list(self._tools.keys())
        
        if tags:
            # 按标签过滤
            filtered = []
            for name in names:
                tool = self._tools[name]
                if any(tag in tool.definition.tags for tag in tags):
                    filtered.append(name)
            names = filtered
        
        return names
    
    def get_definitions(
        self,
        names: Optional[list[str]] = None,
    ) -> list[ToolDefinition]:
        """获取工具定义列表"""
        if names is None:
            names = list(self._tools.keys())
        
        return [
            self._tools[name].definition
            for name in names
            if name in self._tools
        ]
    
    def get_openai_tools(
        self,
        names: Optional[list[str]] = None,
    ) -> list[dict]:
        """获取 OpenAI Function Calling 格式的工具列表"""
        definitions = self.get_definitions(names)
        return [d.to_openai_schema() for d in definitions]
    
    # ===== 执行 =====
    
    async def execute(
        self,
        name: str,
        arguments: Union[str, dict],
        tool_call_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """
        执行工具
        
        Args:
            name: 工具名称
            arguments: 参数（JSON 字符串或字典）
            tool_call_id: 工具调用ID
            timeout: 超时时间（秒）
            
        Returns:
            ToolResult: 执行结果
        """
        # 获取工具
        try:
            tool = self.get(name)
        except ToolNotFoundError as e:
            return ToolResult.error(
                name,
                str(e),
                tool_call_id=tool_call_id,
            )
        
        # 解析参数
        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError as e:
                return ToolResult.error(
                    name,
                    f"Invalid JSON arguments: {e}",
                    tool_call_id=tool_call_id,
                )
        else:
            kwargs = arguments or {}
        
        # 执行
        timeout = timeout or tool.definition.timeout
        
        try:
            result = await asyncio.wait_for(
                tool(**kwargs),
                timeout=timeout,
            )
            result.tool_call_id = tool_call_id
            
            logger.debug(
                f"Tool executed",
                tool=name,
                status=result.status,
                time_ms=result.execution_time_ms,
            )
            
            return result
            
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=name,
                status=ToolResultStatus.TIMEOUT,
                error=f"Tool execution timed out after {timeout}s",
                tool_call_id=tool_call_id,
            )
        except Exception as e:
            logger.exception(f"Tool execution failed: {name}")
            return ToolResult.error(
                name,
                str(e),
                tool_call_id=tool_call_id,
            )
    
    async def execute_batch(
        self,
        calls: list[tuple[str, Union[str, dict], Optional[str]]],
        parallel: bool = True,
    ) -> list[ToolResult]:
        """
        批量执行工具
        
        Args:
            calls: [(tool_name, arguments, tool_call_id), ...]
            parallel: 是否并行执行
            
        Returns:
            list[ToolResult]: 结果列表
        """
        if parallel:
            tasks = [
                self.execute(name, args, call_id)
                for name, args, call_id in calls
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for name, args, call_id in calls:
                result = await self.execute(name, args, call_id)
                results.append(result)
            return results
    
    # ===== 统计 =====
    
    @property
    def count(self) -> int:
        """工具数量"""
        return len(self._tools)
    
    @property
    def categories(self) -> dict[str, int]:
        """各分类工具数量"""
        return {
            cat: len(names)
            for cat, names in self._categories.items()
        }
    
    def __len__(self) -> int:
        return self.count
    
    def __contains__(self, name: str) -> bool:
        return self.has(name)
    
    def __iter__(self):
        return iter(self._tools.values())


# 全局工具注册表
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(tool: BaseTool) -> None:
    """注册工具到全局注册表"""
    get_tool_registry().register(tool)


def tool_decorator(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[list[ToolParameter]] = None,
    auto_register: bool = True,
) -> Callable:
    """
    工具装饰器（自动注册）
    
    用法：
        @tool_decorator(name="search", description="Search the web")
        async def search(query: str) -> str:
            ...
    """
    def decorator(func: Callable) -> FunctionTool:
        tool = FunctionTool(
            func=func,
            name=name,
            description=description,
            parameters=parameters,
        )
        if auto_register:
            register_tool(tool)
        return tool
    return decorator
