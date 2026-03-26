"""
Tests for ShortTermMemory
短期记忆单元测试
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from dv_agent.memory.short_term import ShortTermMemory
from dv_agent.memory.config import MemoryConfig


class TestShortTermMemory:
    """短期记忆测试"""
    
    @pytest.fixture
    def short_term_memory(self, memory_config, mock_redis):
        """Create ShortTermMemory with mocked Redis"""
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            stm = ShortTermMemory(memory_config)
            stm._redis = mock_redis
            return stm
    
    # ========== Message Tests ==========
    
    @pytest.mark.asyncio
    async def test_add_message(self, short_term_memory, mock_redis):
        """Test adding a message"""
        session_id = "test_session"
        message = {
            "role": "user",
            "content": "Hello, world!",
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await short_term_memory.add_message(session_id, message)
        
        # Verify Redis was called
        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        assert session_id in call_args[0][0]  # Key contains session_id
    
    @pytest.mark.asyncio
    async def test_get_messages_empty(self, short_term_memory, mock_redis):
        """Test getting messages from empty session"""
        mock_redis.lrange.return_value = []
        
        messages = await short_term_memory.get_messages("empty_session")
        
        assert messages == []
    
    @pytest.mark.asyncio
    async def test_get_messages_with_data(self, short_term_memory, mock_redis, sample_messages):
        """Test getting messages with data"""
        # Mock Redis to return JSON-encoded messages
        mock_redis.lrange.return_value = [
            json.dumps(msg).encode() for msg in reversed(sample_messages)
        ]
        
        messages = await short_term_memory.get_messages("test_session")
        
        assert len(messages) == len(sample_messages)
    
    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, short_term_memory, mock_redis):
        """Test message limit"""
        messages = [
            json.dumps({"role": "user", "content": f"Message {i}"}).encode()
            for i in range(20)
        ]
        mock_redis.lrange.return_value = messages[:10]  # Return only 10
        
        result = await short_term_memory.get_messages("test_session", limit=10)
        
        assert len(result) <= 10
    
    # ========== Summary Tests ==========
    
    @pytest.mark.asyncio
    async def test_get_summary_none(self, short_term_memory, mock_redis):
        """Test getting non-existent summary"""
        mock_redis.get.return_value = None
        
        summary = await short_term_memory.get_summary("no_summary_session")
        
        assert summary is None
    
    @pytest.mark.asyncio
    async def test_save_and_get_summary(self, short_term_memory, mock_redis):
        """Test saving and retrieving summary"""
        session_id = "summary_session"
        summary_text = "This is a conversation summary."
        
        await short_term_memory.save_summary(session_id, summary_text)
        
        mock_redis.setex.assert_called_once()
    
    # ========== Clear Tests ==========
    
    @pytest.mark.asyncio
    async def test_clear_session(self, short_term_memory, mock_redis):
        """Test clearing a session"""
        session_id = "clear_me"
        
        await short_term_memory.clear_session(session_id)
        
        # Should delete both messages and summary keys
        assert mock_redis.delete.called
    
    # ========== Window Sliding Tests ==========
    
    @pytest.mark.asyncio
    async def test_message_window_trimming(self, short_term_memory, mock_redis):
        """Test that messages are trimmed to window size"""
        session_id = "window_test"
        
        # Add message - should trigger trim
        await short_term_memory.add_message(session_id, {
            "role": "user",
            "content": "Test message",
        })
        
        # Verify ltrim was called to maintain window
        mock_redis.ltrim.assert_called()


class TestShortTermMemoryEdgeCases:
    """Edge case tests"""
    
    @pytest.fixture
    def stm(self, memory_config, mock_redis):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            stm = ShortTermMemory(memory_config)
            stm._redis = mock_redis
            return stm
    
    @pytest.mark.asyncio
    async def test_message_with_special_characters(self, stm, mock_redis):
        """Test message with unicode and special chars"""
        message = {
            "role": "user",
            "content": "你好！🎉 Special chars: <>&\"'",
        }
        
        await stm.add_message("special_session", message)
        
        # Should not raise
        mock_redis.lpush.assert_called()
    
    @pytest.mark.asyncio
    async def test_very_long_message(self, stm, mock_redis):
        """Test handling of very long messages"""
        long_content = "A" * 100000  # 100KB message
        message = {"role": "user", "content": long_content}
        
        await stm.add_message("long_session", message)
        
        mock_redis.lpush.assert_called()
    
    @pytest.mark.asyncio
    async def test_concurrent_message_addition(self, stm, mock_redis):
        """Test adding messages concurrently"""
        import asyncio
        
        session_id = "concurrent_session"
        tasks = [
            stm.add_message(session_id, {"role": "user", "content": f"Message {i}"})
            for i in range(10)
        ]
        
        await asyncio.gather(*tasks)
        
        assert mock_redis.lpush.call_count == 10
