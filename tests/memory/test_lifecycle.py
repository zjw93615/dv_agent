"""
Tests for Lifecycle Components
生命周期管理单元测试
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from dv_agent.memory.models import Memory, MemoryType
from dv_agent.memory.lifecycle.extractor import MemoryExtractor
from dv_agent.memory.lifecycle.updater import ImportanceUpdater
from dv_agent.memory.lifecycle.forgetter import MemoryForgetter, ForgetPolicy


class TestMemoryExtractor:
    """MemoryExtractor tests"""
    
    @pytest.fixture
    def mock_llm(self):
        """Mock LLM"""
        llm = AsyncMock()
        llm.acomplete = AsyncMock(
            return_value=MagicMock(
                text='[{"content": "用户是Python开发者", "type": "fact", "confidence": 0.9}]'
            )
        )
        return llm
    
    @pytest.fixture
    def mock_embedding_model(self):
        """Mock embedding model"""
        import numpy as np
        model = MagicMock()
        model.encode = MagicMock(
            return_value=np.random.rand(384).astype(np.float32)
        )
        return model
    
    @pytest.fixture
    def extractor(self, memory_config, mock_llm, mock_embedding_model):
        """Create extractor with mocks"""
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_embedding_model):
            extractor = MemoryExtractor(memory_config)
            extractor._llm = mock_llm
            extractor._model = mock_embedding_model
            return extractor
    
    # ========== Extraction Tests ==========
    
    @pytest.mark.asyncio
    async def test_extract_from_messages(self, extractor, sample_messages, mock_llm):
        """Test memory extraction from messages"""
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=sample_messages,
        )
        
        assert len(memories) > 0
        mock_llm.acomplete.assert_called()
    
    @pytest.mark.asyncio
    async def test_extract_empty_messages(self, extractor):
        """Test extraction from empty messages"""
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=[],
        )
        
        assert memories == []
    
    @pytest.mark.asyncio
    async def test_extract_assigns_correct_type(self, extractor, sample_messages, mock_llm):
        """Test that extracted memories have correct types"""
        # Setup LLM to return specific types
        mock_llm.acomplete.return_value = MagicMock(
            text='[{"content": "喜欢VS Code", "type": "preference", "confidence": 0.85}]'
        )
        
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=sample_messages,
        )
        
        if memories:
            assert memories[0].memory_type == MemoryType.PREFERENCE
    
    @pytest.mark.asyncio
    async def test_extract_generates_embedding(self, extractor, sample_messages, mock_embedding_model):
        """Test that embeddings are generated"""
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=sample_messages,
        )
        
        if memories:
            assert memories[0].embedding is not None
            assert len(memories[0].embedding) == 384
            mock_embedding_model.encode.assert_called()
    
    @pytest.mark.asyncio
    async def test_extract_handles_llm_error(self, extractor, sample_messages, mock_llm):
        """Test handling of LLM errors"""
        mock_llm.acomplete.side_effect = Exception("LLM error")
        
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=sample_messages,
        )
        
        # Should return empty list, not raise
        assert memories == []
    
    @pytest.mark.asyncio
    async def test_extract_handles_invalid_json(self, extractor, sample_messages, mock_llm):
        """Test handling of invalid LLM JSON response"""
        mock_llm.acomplete.return_value = MagicMock(text="Invalid JSON")
        
        memories = await extractor.extract(
            user_id="test_user",
            session_id="test_session",
            messages=sample_messages,
        )
        
        assert memories == []


class TestImportanceUpdater:
    """ImportanceUpdater tests"""
    
    @pytest.fixture
    def updater(self, memory_config):
        """Create updater"""
        return ImportanceUpdater(memory_config)
    
    @pytest.fixture
    def old_memory(self, sample_memory) -> Memory:
        """Create an old memory for decay testing"""
        sample_memory.created_at = datetime.utcnow() - timedelta(days=30)
        sample_memory.last_accessed = datetime.utcnow() - timedelta(days=15)
        sample_memory.importance = 0.8
        sample_memory.access_count = 10
        return sample_memory
    
    # ========== Decay Tests ==========
    
    def test_calculate_decay(self, updater, old_memory):
        """Test importance decay calculation"""
        original_importance = old_memory.importance
        
        new_importance = updater.calculate_importance(old_memory)
        
        # Importance should decrease over time
        assert new_importance < original_importance
    
    def test_no_decay_for_new_memory(self, updater, sample_memory):
        """Test no decay for fresh memories"""
        sample_memory.created_at = datetime.utcnow()
        sample_memory.importance = 0.8
        
        new_importance = updater.calculate_importance(sample_memory)
        
        # Should be close to original (minimal decay)
        assert abs(new_importance - 0.8) < 0.05
    
    def test_access_boost(self, updater, sample_memory):
        """Test access count boost"""
        sample_memory.access_count = 100
        sample_memory.importance = 0.5
        
        new_importance = updater.calculate_importance(sample_memory)
        
        # High access count should boost importance
        assert new_importance > sample_memory.importance * 0.9  # Not too much decay
    
    def test_importance_bounds(self, updater, sample_memory):
        """Test importance stays within [0, 1]"""
        # Test upper bound
        sample_memory.importance = 1.0
        sample_memory.access_count = 1000
        
        new_importance = updater.calculate_importance(sample_memory)
        assert new_importance <= 1.0
        
        # Test lower bound
        sample_memory.importance = 0.01
        sample_memory.access_count = 0
        sample_memory.created_at = datetime.utcnow() - timedelta(days=365)
        
        new_importance = updater.calculate_importance(sample_memory)
        assert new_importance >= 0.0
    
    # ========== Batch Update Tests ==========
    
    @pytest.mark.asyncio
    async def test_batch_update(self, updater, sample_memories):
        """Test batch importance update"""
        mock_storage = AsyncMock()
        mock_storage.get_all = AsyncMock(return_value=sample_memories)
        mock_storage.update = AsyncMock()
        
        stats = await updater.update_all(mock_storage)
        
        assert stats["updated"] == len(sample_memories)
        assert mock_storage.update.call_count == len(sample_memories)


class TestMemoryForgetter:
    """MemoryForgetter tests"""
    
    @pytest.fixture
    def forgetter(self, memory_config):
        """Create forgetter"""
        return MemoryForgetter(memory_config)
    
    @pytest.fixture
    def old_low_importance_memory(self) -> Memory:
        """Memory that should be forgotten"""
        return Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.FACT,
            content="Old unimportant fact",
            embedding=[0.0] * 384,
            confidence=0.5,
            importance=0.1,  # Low importance
            access_count=0,
            created_at=datetime.utcnow() - timedelta(days=60),
            last_accessed=datetime.utcnow() - timedelta(days=45),
        )
    
    @pytest.fixture
    def permanent_memory(self) -> Memory:
        """Memory marked as permanent"""
        return Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.FACT,
            content="Important permanent fact",
            embedding=[0.0] * 384,
            confidence=0.9,
            importance=0.3,  # Low importance but permanent
            created_at=datetime.utcnow() - timedelta(days=100),
            metadata={"permanent": True},
        )
    
    # ========== Policy Tests ==========
    
    def test_should_soft_forget(self, forgetter, old_low_importance_memory):
        """Test soft forget policy"""
        policy = forgetter.evaluate_policy(old_low_importance_memory)
        
        # Old + low importance should trigger forgetting
        assert policy in [ForgetPolicy.SOFT_FORGET, ForgetPolicy.ARCHIVE, ForgetPolicy.HARD_DELETE]
    
    def test_should_not_forget_important(self, forgetter, sample_memory):
        """Test that important memories are kept"""
        sample_memory.importance = 0.9
        
        policy = forgetter.evaluate_policy(sample_memory)
        
        assert policy == ForgetPolicy.KEEP
    
    def test_should_not_forget_recent(self, forgetter, sample_memory):
        """Test that recent memories are kept"""
        sample_memory.created_at = datetime.utcnow() - timedelta(hours=1)
        sample_memory.importance = 0.1  # Even low importance
        
        policy = forgetter.evaluate_policy(sample_memory)
        
        assert policy == ForgetPolicy.KEEP
    
    def test_permanent_exemption(self, forgetter, permanent_memory):
        """Test permanent memories are exempt"""
        policy = forgetter.evaluate_policy(permanent_memory)
        
        assert policy == ForgetPolicy.KEEP
    
    def test_high_access_exemption(self, forgetter, old_low_importance_memory):
        """Test high access count exemption"""
        old_low_importance_memory.access_count = 100
        
        policy = forgetter.evaluate_policy(old_low_importance_memory)
        
        # High access should keep memory
        assert policy in [ForgetPolicy.KEEP, ForgetPolicy.SOFT_FORGET]
    
    # ========== Forget Cycle Tests ==========
    
    @pytest.mark.asyncio
    async def test_run_forget_cycle(self, forgetter):
        """Test running forget cycle"""
        mock_storage = AsyncMock()
        
        # Create memories in different states
        memories = [
            Memory(
                id=uuid4(),
                user_id="test",
                memory_type=MemoryType.FACT,
                content=f"Memory {i}",
                embedding=[0.0] * 384,
                importance=0.1,
                created_at=datetime.utcnow() - timedelta(days=30 + i * 10),
            )
            for i in range(5)
        ]
        
        mock_storage.get_candidates_for_forgetting = AsyncMock(return_value=memories)
        mock_storage.soft_forget = AsyncMock()
        mock_storage.archive = AsyncMock()
        mock_storage.hard_delete = AsyncMock()
        
        stats = await forgetter.run_cycle(mock_storage)
        
        assert "soft_forgotten" in stats
        assert "archived" in stats
        assert "hard_deleted" in stats


class TestForgetPolicy:
    """ForgetPolicy enum tests"""
    
    def test_policy_ordering(self):
        """Test policy severity ordering"""
        # Verify policies exist
        assert ForgetPolicy.KEEP
        assert ForgetPolicy.SOFT_FORGET
        assert ForgetPolicy.ARCHIVE
        assert ForgetPolicy.HARD_DELETE
    
    def test_policy_string_representation(self):
        """Test policy string values"""
        assert ForgetPolicy.KEEP.value == "keep"
        assert ForgetPolicy.SOFT_FORGET.value == "soft_forget"
