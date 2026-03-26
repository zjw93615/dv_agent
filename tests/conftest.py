"""
Test configuration and fixtures for DV-Agent.
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mock Redis client."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=False)
    client.expire = AsyncMock(return_value=True)
    client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_llm_gateway() -> MagicMock:
    """Create a mock LLM gateway."""
    from dv_agent.llm_gateway.models import LLMResponse, Role
    
    gateway = MagicMock()
    gateway.chat = AsyncMock(return_value=LLMResponse(
        content="This is a mock response.",
        role=Role.ASSISTANT,
        model="mock-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    ))
    gateway.chat_stream = AsyncMock()
    return gateway


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    """Create a mock tool registry."""
    from dv_agent.tools.models import BaseTool, ToolResult
    
    registry = MagicMock()
    
    # Mock tool - use MagicMock instead of actual Tool for flexibility
    mock_tool = MagicMock()
    mock_tool.name = "mock_tool"
    mock_tool.description = "A mock tool for testing"
    mock_tool.category = "testing"
    
    registry.get = MagicMock(return_value=mock_tool)
    registry.list_tools = MagicMock(return_value=[mock_tool])
    registry.execute = AsyncMock(return_value=ToolResult(
        tool_name="mock_tool",
        success=True,
        output="Mock tool executed successfully"
    ))
    
    return registry


@pytest.fixture
def mock_session_manager(mock_redis_client) -> MagicMock:
    """Create a mock session manager."""
    from dv_agent.session.models import Session
    from datetime import datetime
    
    manager = MagicMock()
    
    mock_session = Session(
        session_id="test-session-123",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    manager.create_session = AsyncMock(return_value=mock_session)
    manager.get_session = AsyncMock(return_value=mock_session)
    manager.update_session = AsyncMock(return_value=mock_session)
    manager.delete_session = AsyncMock(return_value=True)
    
    return manager


@pytest.fixture
def mock_intent_router() -> MagicMock:
    """Create a mock intent router."""
    from dv_agent.intent.models import IntentResult, Intent
    
    router = MagicMock()
    
    mock_result = IntentResult(
        intent=Intent.GENERAL,
        confidence=0.9,
        entities={},
        raw_query="test query"
    )
    
    router.route = AsyncMock(return_value=("orchestrator", mock_result))
    
    return router


@pytest.fixture
def sample_messages():
    """Sample test messages."""
    return [
        "Hello, how are you?",
        "计算 1 + 1",
        "今天是什么日期？",
        "帮我搜索最新的AI新闻",
        "分析这段代码的问题",
    ]


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "app_name": "dv-agent-test",
        "debug": True,
        "environment": "test",
        "redis": {
            "host": "localhost",
            "port": 6379,
            "db": 15  # Use a different DB for testing
        },
        "llm": {
            "primary_provider": "ollama",
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.2"
        }
    }
