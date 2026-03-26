"""
Tests for LLM Gateway.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dv_agent.llm_gateway.gateway import LLMGateway
from dv_agent.llm_gateway.models import Message, LLMResponse, Role
from dv_agent.llm_gateway.base_adapter import BaseLLMAdapter


class MockAdapter(BaseLLMAdapter):
    """Mock adapter for testing."""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0
    
    async def chat(self, messages, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self.should_fail:
            raise Exception("Mock adapter failed")
        return LLMResponse(
            content=f"Mock response {self.call_count}",
            role=Role.ASSISTANT,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        )
    
    async def chat_stream(self, messages, **kwargs):
        if self.should_fail:
            raise Exception("Mock adapter failed")
        yield "Mock "
        yield "stream "
        yield "response"


class TestLLMGateway:
    """Test suite for LLM Gateway."""
    
    def test_register_adapter(self):
        """Test adapter registration."""
        gateway = LLMGateway()
        adapter = MockAdapter()
        
        gateway.register_adapter("mock", adapter)
        
        assert "mock" in gateway._adapters
        assert gateway._adapters["mock"] == adapter
    
    def test_set_primary(self):
        """Test setting primary adapter."""
        gateway = LLMGateway()
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        
        gateway.set_primary("mock")
        
        assert gateway._primary == "mock"
    
    def test_set_primary_not_registered(self):
        """Test setting primary to unregistered adapter."""
        gateway = LLMGateway()
        
        with pytest.raises(ValueError):
            gateway.set_primary("nonexistent")
    
    def test_set_fallback_chain(self):
        """Test setting fallback chain."""
        gateway = LLMGateway()
        gateway.register_adapter("mock1", MockAdapter())
        gateway.register_adapter("mock2", MockAdapter())
        
        gateway.set_fallback_chain(["mock1", "mock2"])
        
        assert gateway._fallback_chain == ["mock1", "mock2"]
    
    @pytest.mark.asyncio
    async def test_chat_success(self):
        """Test successful chat request."""
        gateway = LLMGateway()
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        gateway.set_primary("mock")
        
        messages = [Message(role=Role.USER, content="Hello")]
        response = await gateway.chat(messages)
        
        assert response.content == "Mock response 1"
        assert response.role == Role.ASSISTANT
        assert adapter.call_count == 1
    
    @pytest.mark.asyncio
    async def test_chat_fallback(self):
        """Test fallback when primary fails."""
        gateway = LLMGateway()
        
        failing_adapter = MockAdapter(should_fail=True)
        working_adapter = MockAdapter()
        
        gateway.register_adapter("failing", failing_adapter)
        gateway.register_adapter("working", working_adapter)
        gateway.set_primary("failing")
        gateway.set_fallback_chain(["working"])
        
        messages = [Message(role=Role.USER, content="Hello")]
        response = await gateway.chat(messages)
        
        assert response.content == "Mock response 1"
        assert failing_adapter.call_count == 1
        assert working_adapter.call_count == 1
    
    @pytest.mark.asyncio
    async def test_chat_all_fail(self):
        """Test when all adapters fail."""
        gateway = LLMGateway()
        
        gateway.register_adapter("fail1", MockAdapter(should_fail=True))
        gateway.register_adapter("fail2", MockAdapter(should_fail=True))
        gateway.set_primary("fail1")
        gateway.set_fallback_chain(["fail2"])
        
        messages = [Message(role=Role.USER, content="Hello")]
        
        with pytest.raises(Exception):
            await gateway.chat(messages)
    
    @pytest.mark.asyncio
    async def test_chat_with_specific_provider(self):
        """Test chat with specific provider."""
        gateway = LLMGateway()
        gateway.register_adapter("mock1", MockAdapter())
        gateway.register_adapter("mock2", MockAdapter())
        gateway.set_primary("mock1")
        
        messages = [Message(role=Role.USER, content="Hello")]
        response = await gateway.chat(messages, provider="mock2")
        
        # Should use mock2 directly
        assert response.content == "Mock response 1"


class TestMessage:
    """Test suite for Message model."""
    
    def test_create_user_message(self):
        """Test creating a user message."""
        msg = Message(role=Role.USER, content="Hello")
        
        assert msg.role == Role.USER
        assert msg.content == "Hello"
    
    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        msg = Message(role=Role.ASSISTANT, content="Hi there!")
        
        assert msg.role == Role.ASSISTANT
        assert msg.content == "Hi there!"
    
    def test_create_system_message(self):
        """Test creating a system message."""
        msg = Message(role=Role.SYSTEM, content="You are a helpful assistant.")
        
        assert msg.role == Role.SYSTEM
        assert msg.content == "You are a helpful assistant."
    
    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(role=Role.USER, content="Test")
        data = msg.model_dump()
        
        assert data["role"] == "user"
        assert data["content"] == "Test"


class TestLLMResponse:
    """Test suite for LLMResponse model."""
    
    def test_create_response(self):
        """Test creating a response."""
        response = LLMResponse(
            content="Hello!",
            role=Role.ASSISTANT,
            model="gpt-4",
            usage={"total_tokens": 10}
        )
        
        assert response.content == "Hello!"
        assert response.role == Role.ASSISTANT
        assert response.model == "gpt-4"
    
    def test_response_with_tool_calls(self):
        """Test response with tool calls."""
        response = LLMResponse(
            content="",
            role=Role.ASSISTANT,
            model="gpt-4",
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": '{"a": 1, "b": 2}'
                }
            }]
        )
        
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "calculator"
