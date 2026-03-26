"""
Tests for Session Management.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from dv_agent.session.models import (
    Session, 
    ConversationHistory, 
    ConversationTurn,
    AgentContext,
    ReActStep
)
from dv_agent.session.manager import SessionManager


class TestSession:
    """Test suite for Session model."""
    
    def test_create_session(self):
        """Test creating a new session."""
        session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        assert session.session_id == "test-123"
        assert session.history is not None
        assert session.context is not None
    
    def test_session_with_metadata(self):
        """Test session with metadata."""
        session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"user_id": "user-456", "channel": "web"}
        )
        
        assert session.metadata["user_id"] == "user-456"
        assert session.metadata["channel"] == "web"
    
    def test_session_serialization(self):
        """Test session serialization."""
        session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        data = session.model_dump()
        
        assert data["session_id"] == "test-123"
        assert "created_at" in data
        assert "history" in data


class TestConversationHistory:
    """Test suite for ConversationHistory."""
    
    def test_create_empty_history(self):
        """Test creating empty conversation history."""
        history = ConversationHistory()
        
        assert len(history.turns) == 0
    
    def test_add_turn(self):
        """Test adding a conversation turn."""
        history = ConversationHistory()
        
        turn = ConversationTurn(
            role="user",
            content="Hello!",
            timestamp=datetime.now()
        )
        
        history.turns.append(turn)
        
        assert len(history.turns) == 1
        assert history.turns[0].content == "Hello!"
    
    def test_multiple_turns(self):
        """Test multiple conversation turns."""
        history = ConversationHistory()
        
        history.turns.append(ConversationTurn(
            role="user",
            content="What's 2+2?",
            timestamp=datetime.now()
        ))
        
        history.turns.append(ConversationTurn(
            role="assistant",
            content="2+2 equals 4.",
            timestamp=datetime.now()
        ))
        
        assert len(history.turns) == 2
        assert history.turns[0].role == "user"
        assert history.turns[1].role == "assistant"
    
    def test_get_last_n_turns(self):
        """Test getting last N turns."""
        history = ConversationHistory()
        
        for i in range(10):
            history.turns.append(ConversationTurn(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                timestamp=datetime.now()
            ))
        
        last_5 = history.turns[-5:]
        
        assert len(last_5) == 5
        assert last_5[0].content == "Message 5"


class TestAgentContext:
    """Test suite for AgentContext."""
    
    def test_create_empty_context(self):
        """Test creating empty agent context."""
        context = AgentContext()
        
        assert context.current_agent is None
        assert len(context.pending_tasks) == 0
    
    def test_context_with_pending_task(self):
        """Test context with pending task."""
        context = AgentContext(
            current_agent="orchestrator",
            pending_tasks=["task-1", "task-2"]
        )
        
        assert context.current_agent == "orchestrator"
        assert len(context.pending_tasks) == 2
    
    def test_context_with_react_steps(self):
        """Test context with ReAct steps."""
        step = ReActStep(
            step_number=1,
            thought="I need to calculate this",
            action="calculator",
            action_input={"expression": "2+2"},
            observation="4",
            timestamp=datetime.now()
        )
        
        context = AgentContext(
            current_agent="worker",
            react_steps=[step]
        )
        
        assert len(context.react_steps) == 1
        assert context.react_steps[0].action == "calculator"


class TestReActStep:
    """Test suite for ReActStep."""
    
    def test_create_react_step(self):
        """Test creating a ReAct step."""
        step = ReActStep(
            step_number=1,
            thought="I should search for this",
            action="search",
            action_input={"query": "AI news"},
            timestamp=datetime.now()
        )
        
        assert step.step_number == 1
        assert step.thought == "I should search for this"
        assert step.observation is None  # Not yet observed
    
    def test_react_step_with_observation(self):
        """Test ReAct step with observation."""
        step = ReActStep(
            step_number=1,
            thought="Let me calculate",
            action="calculator",
            action_input={"expression": "1+1"},
            observation="2",
            timestamp=datetime.now()
        )
        
        assert step.observation == "2"


class TestSessionManager:
    """Test suite for SessionManager."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=True)
        redis.expire = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=False)
        return redis
    
    @pytest.fixture
    def manager(self, mock_redis):
        """Create session manager with mock Redis."""
        return SessionManager(redis_client=mock_redis, default_ttl=3600)
    
    @pytest.mark.asyncio
    async def test_create_session(self, manager, mock_redis):
        """Test creating a new session."""
        session = await manager.create_session()
        
        assert session.session_id is not None
        assert len(session.session_id) > 0
        mock_redis.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_session_with_id(self, manager, mock_redis):
        """Test creating session with specific ID."""
        session = await manager.create_session(session_id="custom-id")
        
        assert session.session_id == "custom-id"
    
    @pytest.mark.asyncio
    async def test_get_existing_session(self, manager, mock_redis):
        """Test getting an existing session."""
        # Setup mock to return a session
        existing_session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        mock_redis.get = AsyncMock(return_value=existing_session.model_dump_json())
        
        session = await manager.get_session("test-123")
        
        assert session is not None
        assert session.session_id == "test-123"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, manager, mock_redis):
        """Test getting a session that doesn't exist."""
        mock_redis.get = AsyncMock(return_value=None)
        
        session = await manager.get_session("nonexistent")
        
        assert session is None
    
    @pytest.mark.asyncio
    async def test_update_session(self, manager, mock_redis):
        """Test updating a session."""
        session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        session.metadata = {"updated": True}
        
        updated = await manager.update_session(session)
        
        assert updated.metadata["updated"] is True
        mock_redis.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_delete_session(self, manager, mock_redis):
        """Test deleting a session."""
        result = await manager.delete_session("test-123")
        
        assert result is True
        mock_redis.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_conversation_turn(self, manager, mock_redis):
        """Test adding a conversation turn to session."""
        # Setup existing session
        existing_session = Session(
            session_id="test-123",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        mock_redis.get = AsyncMock(return_value=existing_session.model_dump_json())
        
        session = await manager.get_session("test-123")
        
        # Add turn
        session.history.turns.append(ConversationTurn(
            role="user",
            content="Hello!",
            timestamp=datetime.now()
        ))
        
        await manager.update_session(session)
        
        assert len(session.history.turns) == 1
    
    @pytest.mark.asyncio
    async def test_session_ttl(self, manager, mock_redis):
        """Test session TTL is set correctly."""
        await manager.create_session()
        
        # Check that expire was called with correct TTL
        mock_redis.expire.assert_called()


class TestConversationTurn:
    """Test suite for ConversationTurn."""
    
    def test_create_user_turn(self):
        """Test creating a user turn."""
        turn = ConversationTurn(
            role="user",
            content="Hello!",
            timestamp=datetime.now()
        )
        
        assert turn.role == "user"
        assert turn.content == "Hello!"
    
    def test_create_assistant_turn(self):
        """Test creating an assistant turn."""
        turn = ConversationTurn(
            role="assistant",
            content="Hi there!",
            timestamp=datetime.now()
        )
        
        assert turn.role == "assistant"
    
    def test_turn_with_metadata(self):
        """Test turn with metadata."""
        turn = ConversationTurn(
            role="assistant",
            content="Result is 42",
            timestamp=datetime.now(),
            metadata={
                "tool_used": "calculator",
                "tokens": 50
            }
        )
        
        assert turn.metadata["tool_used"] == "calculator"
