"""
内置 Skills（技能）
提供常用的工具实现
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional

from .models import BaseTool, ToolResult, ToolParameter, ToolDefinition


class DateTimeTool(BaseTool):
    """获取当前日期时间"""
    
    name = "get_datetime"
    description = "获取当前的日期和时间"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="format",
                type="string",
                description="时间格式，如 '%Y-%m-%d %H:%M:%S'",
                required=False,
                default="%Y-%m-%d %H:%M:%S",
            ),
            ToolParameter(
                name="timezone",
                type="string",
                description="时区，如 'Asia/Shanghai'",
                required=False,
            ),
        ]
    
    async def execute(
        self,
        format: str = "%Y-%m-%d %H:%M:%S",
        timezone: Optional[str] = None,
    ) -> ToolResult:
        try:
            now = datetime.now()
            
            if timezone:
                try:
                    from zoneinfo import ZoneInfo
                    now = datetime.now(ZoneInfo(timezone))
                except ImportError:
                    pass
            
            formatted = now.strftime(format)
            
            return ToolResult.success(
                self.name,
                {
                    "datetime": formatted,
                    "timestamp": now.timestamp(),
                    "timezone": timezone or "local",
                },
            )
        except Exception as e:
            return ToolResult.error(self.name, str(e))


class CalculatorTool(BaseTool):
    """简单计算器"""
    
    name = "calculator"
    description = "执行数学计算，支持基本运算和常用数学函数"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="expression",
                type="string",
                description="数学表达式，如 '2 + 3 * 4' 或 'sqrt(16)'",
                required=True,
            ),
        ]
    
    async def execute(self, expression: str) -> ToolResult:
        import math
        
        # 安全的数学函数
        safe_functions = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
        }
        
        try:
            # 安全执行
            result = eval(expression, {"__builtins__": {}}, safe_functions)
            
            return ToolResult.success(
                self.name,
                {
                    "expression": expression,
                    "result": result,
                },
            )
        except Exception as e:
            return ToolResult.error(self.name, f"计算错误: {e}")


class JSONTool(BaseTool):
    """JSON 处理工具"""
    
    name = "json_tool"
    description = "解析、格式化或提取 JSON 数据"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型",
                required=True,
                enum=["parse", "format", "extract"],
            ),
            ToolParameter(
                name="data",
                type="string",
                description="JSON 字符串",
                required=True,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="JSONPath（用于 extract 操作）",
                required=False,
            ),
        ]
    
    async def execute(
        self,
        action: str,
        data: str,
        path: Optional[str] = None,
    ) -> ToolResult:
        try:
            parsed = json.loads(data)
            
            if action == "parse":
                return ToolResult.success(self.name, parsed)
            
            elif action == "format":
                formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
                return ToolResult.success(self.name, formatted)
            
            elif action == "extract":
                if not path:
                    return ToolResult.error(self.name, "需要指定 path 参数")
                
                # 简单的点号路径解析
                result = parsed
                for key in path.split("."):
                    if key.isdigit():
                        result = result[int(key)]
                    else:
                        result = result[key]
                
                return ToolResult.success(self.name, result)
            
            else:
                return ToolResult.error(self.name, f"未知操作: {action}")
                
        except json.JSONDecodeError as e:
            return ToolResult.error(self.name, f"JSON 解析错误: {e}")
        except (KeyError, IndexError) as e:
            return ToolResult.error(self.name, f"路径访问错误: {e}")
        except Exception as e:
            return ToolResult.error(self.name, str(e))


class TextTool(BaseTool):
    """文本处理工具"""
    
    name = "text_tool"
    description = "执行文本处理操作：统计、搜索、替换等"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型",
                required=True,
                enum=["count", "search", "replace", "split", "join"],
            ),
            ToolParameter(
                name="text",
                type="string",
                description="输入文本",
                required=True,
            ),
            ToolParameter(
                name="pattern",
                type="string",
                description="搜索/替换模式",
                required=False,
            ),
            ToolParameter(
                name="replacement",
                type="string",
                description="替换内容",
                required=False,
            ),
            ToolParameter(
                name="delimiter",
                type="string",
                description="分隔符",
                required=False,
            ),
        ]
    
    async def execute(
        self,
        action: str,
        text: str,
        pattern: Optional[str] = None,
        replacement: Optional[str] = None,
        delimiter: Optional[str] = None,
    ) -> ToolResult:
        try:
            if action == "count":
                result = {
                    "characters": len(text),
                    "words": len(text.split()),
                    "lines": len(text.splitlines()),
                }
                return ToolResult.success(self.name, result)
            
            elif action == "search":
                if not pattern:
                    return ToolResult.error(self.name, "需要指定 pattern")
                
                import re
                matches = re.findall(pattern, text)
                return ToolResult.success(self.name, {
                    "pattern": pattern,
                    "count": len(matches),
                    "matches": matches[:100],  # 限制返回数量
                })
            
            elif action == "replace":
                if not pattern or replacement is None:
                    return ToolResult.error(self.name, "需要指定 pattern 和 replacement")
                
                import re
                result = re.sub(pattern, replacement, text)
                return ToolResult.success(self.name, result)
            
            elif action == "split":
                delim = delimiter or "\n"
                parts = text.split(delim)
                return ToolResult.success(self.name, parts)
            
            elif action == "join":
                if not isinstance(text, str):
                    return ToolResult.error(self.name, "text 必须是字符串")
                # 假设 text 是 JSON 数组字符串
                parts = json.loads(text)
                delim = delimiter or "\n"
                result = delim.join(parts)
                return ToolResult.success(self.name, result)
            
            else:
                return ToolResult.error(self.name, f"未知操作: {action}")
                
        except Exception as e:
            return ToolResult.error(self.name, str(e))


class WaitTool(BaseTool):
    """等待/延迟工具"""
    
    name = "wait"
    description = "等待指定的时间"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="seconds",
                type="number",
                description="等待秒数（最大60秒）",
                required=True,
            ),
        ]
    
    async def execute(self, seconds: float) -> ToolResult:
        # 限制最大等待时间
        seconds = min(seconds, 60)
        
        await asyncio.sleep(seconds)
        
        return ToolResult.success(
            self.name,
            {"waited_seconds": seconds},
        )


class EnvTool(BaseTool):
    """环境变量工具"""
    
    name = "get_env"
    description = "获取环境变量值"
    
    def _get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="name",
                type="string",
                description="环境变量名",
                required=True,
            ),
            ToolParameter(
                name="default",
                type="string",
                description="默认值",
                required=False,
            ),
        ]
    
    async def execute(
        self,
        name: str,
        default: Optional[str] = None,
    ) -> ToolResult:
        # 安全检查：不允许获取敏感变量
        sensitive_patterns = ["password", "secret", "key", "token", "credential"]
        if any(p in name.lower() for p in sensitive_patterns):
            return ToolResult.error(self.name, "无法获取敏感环境变量")
        
        value = os.environ.get(name, default)
        
        return ToolResult.success(
            self.name,
            {"name": name, "value": value},
        )


# 所有内置工具
BUILTIN_TOOLS = [
    DateTimeTool,
    CalculatorTool,
    JSONTool,
    TextTool,
    WaitTool,
    EnvTool,
]


def register_builtin_tools(registry) -> list[str]:
    """注册所有内置工具到注册表"""
    registered = []
    for tool_class in BUILTIN_TOOLS:
        tool = tool_class()
        registry.register(tool)
        registered.append(tool.name)
    return registered
