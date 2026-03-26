"""
工具模块
提供统一的工具注册、发现和执行接口
"""

from .models import (
    BaseTool,
    FunctionTool,
    ToolResult,
    ToolResultStatus,
    ToolDefinition,
    ToolParameter,
    ToolCategory,
    tool,
)
from .registry import (
    ToolRegistry,
    get_tool_registry,
    register_tool,
    tool_decorator,
)
from .mcp_manager import (
    MCPManager,
    MCPTool,
    MCPServerConfig,
    get_mcp_manager,
)
from .builtin_skills import (
    BUILTIN_TOOLS,
    register_builtin_tools,
    DateTimeTool,
    CalculatorTool,
    JSONTool,
    TextTool,
    WaitTool,
    EnvTool,
)

__all__ = [
    # Models
    "BaseTool",
    "FunctionTool",
    "ToolResult",
    "ToolResultStatus",
    "ToolDefinition",
    "ToolParameter",
    "ToolCategory",
    "tool",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    "tool_decorator",
    # MCP
    "MCPManager",
    "MCPTool",
    "MCPServerConfig",
    "get_mcp_manager",
    # Builtin
    "BUILTIN_TOOLS",
    "register_builtin_tools",
    "DateTimeTool",
    "CalculatorTool",
    "JSONTool",
    "TextTool",
    "WaitTool",
    "EnvTool",
]