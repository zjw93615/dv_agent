"""
Tests for Tools and Skills.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from dv_agent.tools.registry import ToolRegistry
from dv_agent.tools.models import BaseTool as Tool, ToolResult
from dv_agent.tools.builtin_skills import CalculatorTool, DateTimeTool


class TestToolRegistry:
    """Test suite for Tool Registry."""
    
    def test_register_tool(self):
        """Test tool registration."""
        registry = ToolRegistry()
        tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters={"input": "string"}
        )
        
        registry.register(tool)
        
        assert registry.get("test_tool") == tool
    
    def test_register_duplicate_tool(self):
        """Test registering duplicate tool."""
        registry = ToolRegistry()
        tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters={}
        )
        
        registry.register(tool)
        
        # Should raise or overwrite
        registry.register(tool)  # No error, just overwrites
        
        assert len(registry.list_tools()) == 1
    
    def test_get_nonexistent_tool(self):
        """Test getting a tool that doesn't exist."""
        registry = ToolRegistry()
        
        result = registry.get("nonexistent")
        
        assert result is None
    
    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        
        tool1 = Tool(name="tool1", description="Tool 1", parameters={})
        tool2 = Tool(name="tool2", description="Tool 2", parameters={})
        
        registry.register(tool1)
        registry.register(tool2)
        
        tools = registry.list_tools()
        
        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools
    
    def test_list_tools_by_category(self):
        """Test listing tools by category."""
        registry = ToolRegistry()
        
        tool1 = Tool(name="tool1", description="Tool 1", parameters={}, category="math")
        tool2 = Tool(name="tool2", description="Tool 2", parameters={}, category="text")
        tool3 = Tool(name="tool3", description="Tool 3", parameters={}, category="math")
        
        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)
        
        math_tools = registry.list_tools(category="math")
        
        assert len(math_tools) == 2
        assert tool1 in math_tools
        assert tool3 in math_tools
    
    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        tool = Tool(name="test_tool", description="Test", parameters={})
        
        registry.register(tool)
        registry.unregister("test_tool")
        
        assert registry.get("test_tool") is None


class TestCalculatorTool:
    """Test suite for Calculator Tool."""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator tool instance."""
        return CalculatorTool()
    
    @pytest.mark.asyncio
    async def test_simple_addition(self, calculator):
        """Test simple addition."""
        result = await calculator.execute(expression="2 + 3")
        
        assert result.success
        assert result.result == 5
    
    @pytest.mark.asyncio
    async def test_simple_subtraction(self, calculator):
        """Test simple subtraction."""
        result = await calculator.execute(expression="10 - 4")
        
        assert result.success
        assert result.result == 6
    
    @pytest.mark.asyncio
    async def test_multiplication(self, calculator):
        """Test multiplication."""
        result = await calculator.execute(expression="6 * 7")
        
        assert result.success
        assert result.result == 42
    
    @pytest.mark.asyncio
    async def test_division(self, calculator):
        """Test division."""
        result = await calculator.execute(expression="20 / 4")
        
        assert result.success
        assert result.result == 5
    
    @pytest.mark.asyncio
    async def test_complex_expression(self, calculator):
        """Test complex expression."""
        result = await calculator.execute(expression="(2 + 3) * 4 - 10 / 2")
        
        assert result.success
        assert result.result == 15
    
    @pytest.mark.asyncio
    async def test_power(self, calculator):
        """Test power operation."""
        result = await calculator.execute(expression="2 ** 10")
        
        assert result.success
        assert result.result == 1024
    
    @pytest.mark.asyncio
    async def test_invalid_expression(self, calculator):
        """Test invalid expression."""
        result = await calculator.execute(expression="2 + + 3")
        
        assert not result.success
        assert "error" in result.result.lower() or result.error is not None
    
    @pytest.mark.asyncio
    async def test_division_by_zero(self, calculator):
        """Test division by zero."""
        result = await calculator.execute(expression="10 / 0")
        
        assert not result.success


class TestDateTimeTool:
    """Test suite for DateTime Tool."""
    
    @pytest.fixture
    def datetime_tool(self):
        """Create datetime tool instance."""
        return DateTimeTool()
    
    @pytest.mark.asyncio
    async def test_get_current_time(self, datetime_tool):
        """Test getting current time."""
        result = await datetime_tool.execute(action="now")
        
        assert result.success
        assert "date" in result.result or "time" in result.result.lower()
    
    @pytest.mark.asyncio
    async def test_format_date(self, datetime_tool):
        """Test date formatting."""
        result = await datetime_tool.execute(
            action="format",
            date="2024-01-15",
            format="%Y年%m月%d日"
        )
        
        assert result.success
        assert "2024年01月15日" in result.result
    
    @pytest.mark.asyncio
    async def test_get_weekday(self, datetime_tool):
        """Test getting weekday."""
        result = await datetime_tool.execute(
            action="weekday",
            date="2024-01-15"  # This is a Monday
        )
        
        assert result.success
    
    @pytest.mark.asyncio
    async def test_date_diff(self, datetime_tool):
        """Test date difference calculation."""
        result = await datetime_tool.execute(
            action="diff",
            date1="2024-01-01",
            date2="2024-01-15"
        )
        
        assert result.success
        assert "14" in str(result.result)


class TestToolModel:
    """Test suite for Tool model."""
    
    def test_create_tool(self):
        """Test creating a tool."""
        tool = Tool(
            name="my_tool",
            description="My custom tool",
            parameters={"query": "string", "limit": "integer"},
            category="custom"
        )
        
        assert tool.name == "my_tool"
        assert tool.description == "My custom tool"
        assert "query" in tool.parameters
        assert tool.category == "custom"
    
    def test_tool_with_handler(self):
        """Test tool with handler function."""
        async def my_handler(**kwargs):
            return ToolResult(
                tool_name="my_tool",
                success=True,
                result="Handler executed"
            )
        
        tool = Tool(
            name="my_tool",
            description="Tool with handler",
            parameters={},
            handler=my_handler
        )
        
        assert tool.handler is not None


class TestToolResult:
    """Test suite for ToolResult model."""
    
    def test_successful_result(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_name="calculator",
            success=True,
            result=42
        )
        
        assert result.success
        assert result.result == 42
        assert result.error is None
    
    def test_failed_result(self):
        """Test failed tool result."""
        result = ToolResult(
            tool_name="calculator",
            success=False,
            result=None,
            error="Division by zero"
        )
        
        assert not result.success
        assert result.error == "Division by zero"
    
    def test_result_with_metadata(self):
        """Test tool result with metadata."""
        result = ToolResult(
            tool_name="search",
            success=True,
            result=["item1", "item2"],
            metadata={"total": 2, "page": 1}
        )
        
        assert result.metadata["total"] == 2
