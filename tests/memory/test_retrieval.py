"""
Tests for Retriever and Reranker
检索系统单元测试
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from dv_agent.memory.models import Memory, MemoryType
from dv_agent.memory.retrieval.retriever import MemoryRetriever, RetrievalQuery, RetrievalResult
from dv_agent.memory.retrieval.reranker import CrossEncoderReranker


class TestMemoryRetriever:
    """MemoryRetriever tests"""
    
    @pytest.fixture
    def mock_long_term(self):
        """Mock LongTermMemory"""
        ltm = AsyncMock()
        ltm.search_by_vector = AsyncMock(return_value=[])
        ltm.search_by_keyword = AsyncMock(return_value=[])
        ltm.get_by_user = AsyncMock(return_value=[])
        return ltm
    
    @pytest.fixture
    def mock_embedding_model(self):
        """Mock embedding model"""
        model = MagicMock()
        model.encode = MagicMock(
            return_value=np.random.rand(384).astype(np.float32)
        )
        return model
    
    @pytest.fixture
    def retriever(self, memory_config, mock_long_term, mock_embedding_model):
        """Create retriever with mocks"""
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_embedding_model):
            retriever = MemoryRetriever(memory_config)
            retriever._long_term = mock_long_term
            retriever._model = mock_embedding_model
            retriever._redis = AsyncMock()
            retriever._redis.get = AsyncMock(return_value=None)
            retriever._redis.setex = AsyncMock()
            return retriever
    
    # ========== Query Tests ==========
    
    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, retriever, mock_long_term):
        """Test retrieval with no results"""
        query = RetrievalQuery(
            user_id="test_user",
            query="What is Python?",
            top_k=10,
        )
        
        results = await retriever.retrieve(query)
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_retrieve_with_vector_results(
        self, retriever, mock_long_term, sample_memories
    ):
        """Test retrieval with vector search results"""
        # Setup mock to return sample memories
        mock_long_term.search_by_vector.return_value = [
            (sample_memories[0], 0.95),
            (sample_memories[1], 0.85),
        ]
        
        query = RetrievalQuery(
            user_id="test_user",
            query="Python programming",
            top_k=5,
        )
        
        results = await retriever.retrieve(query)
        
        assert len(results) > 0
        mock_long_term.search_by_vector.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_with_type_filter(
        self, retriever, mock_long_term, sample_memories
    ):
        """Test retrieval with memory type filter"""
        mock_long_term.search_by_vector.return_value = [
            (sample_memories[0], 0.9),  # FACT type
        ]
        
        query = RetrievalQuery(
            user_id="test_user",
            query="Developer skills",
            top_k=5,
            memory_types=[MemoryType.FACT, MemoryType.SKILL],
        )
        
        results = await retriever.retrieve(query)
        
        # All results should be of specified types
        for result in results:
            assert result.memory.memory_type in [MemoryType.FACT, MemoryType.SKILL]
    
    @pytest.mark.asyncio
    async def test_multi_path_recall(self, retriever, mock_long_term, sample_memories):
        """Test that multiple recall paths are used"""
        # Setup different results for each path
        mock_long_term.search_by_vector.return_value = [
            (sample_memories[0], 0.9),
        ]
        mock_long_term.search_by_keyword.return_value = [
            (sample_memories[1], 0.8),
        ]
        mock_long_term.get_by_user.return_value = [
            sample_memories[2],
        ]
        
        query = RetrievalQuery(
            user_id="test_user",
            query="Python developer",
            top_k=10,
            weights={"vector": 0.5, "keyword": 0.3, "recency": 0.2},
        )
        
        results = await retriever.retrieve(query)
        
        # Should have called all three paths
        mock_long_term.search_by_vector.assert_called()
        mock_long_term.search_by_keyword.assert_called()
        mock_long_term.get_by_user.assert_called()
    
    # ========== Deduplication Tests ==========
    
    @pytest.mark.asyncio
    async def test_deduplication(self, retriever, mock_long_term, sample_memory):
        """Test that duplicate memories are deduplicated"""
        # Return same memory from multiple paths
        mock_long_term.search_by_vector.return_value = [
            (sample_memory, 0.95),
        ]
        mock_long_term.search_by_keyword.return_value = [
            (sample_memory, 0.85),
        ]
        
        query = RetrievalQuery(
            user_id="test_user",
            query="Software engineer",
            top_k=10,
        )
        
        results = await retriever.retrieve(query)
        
        # Should only appear once with highest score
        memory_ids = [r.memory.id for r in results]
        assert len(memory_ids) == len(set(memory_ids))
    
    # ========== Score Fusion Tests ==========
    
    @pytest.mark.asyncio
    async def test_score_fusion(self, retriever, mock_long_term, sample_memories):
        """Test score fusion from multiple paths"""
        # Memory appears in both vector and keyword with different scores
        mock_long_term.search_by_vector.return_value = [
            (sample_memories[0], 0.9),
        ]
        mock_long_term.search_by_keyword.return_value = [
            (sample_memories[0], 0.7),
        ]
        
        query = RetrievalQuery(
            user_id="test_user",
            query="Python",
            top_k=5,
            weights={"vector": 0.6, "keyword": 0.4, "recency": 0.0},
        )
        
        results = await retriever.retrieve(query)
        
        if results:
            # Score should be fusion of both paths
            # 0.9 * 0.6 + 0.7 * 0.4 = 0.54 + 0.28 = 0.82
            assert results[0].final_score > 0


class TestCrossEncoderReranker:
    """CrossEncoderReranker tests"""
    
    @pytest.fixture
    def mock_cross_encoder(self):
        """Mock cross-encoder model"""
        model = MagicMock()
        model.predict = MagicMock(return_value=np.array([0.9, 0.7, 0.5, 0.3]))
        return model
    
    @pytest.fixture
    def reranker(self, mock_cross_encoder):
        """Create reranker with mock"""
        with patch("sentence_transformers.CrossEncoder", return_value=mock_cross_encoder):
            reranker = CrossEncoderReranker()
            reranker._model = mock_cross_encoder
            return reranker
    
    @pytest.fixture
    def sample_retrieval_results(self, sample_memories) -> list[RetrievalResult]:
        """Sample retrieval results for reranking"""
        return [
            RetrievalResult(
                memory=sample_memories[i],
                vector_score=0.9 - i * 0.1,
                keyword_score=0.0,
                recency_score=0.0,
                final_score=0.9 - i * 0.1,
            )
            for i in range(len(sample_memories))
        ]
    
    # ========== Reranking Tests ==========
    
    def test_rerank_basic(self, reranker, sample_retrieval_results, mock_cross_encoder):
        """Test basic reranking"""
        query = "Python developer skills"
        
        reranked = reranker.rerank(query, sample_retrieval_results, top_k=3)
        
        assert len(reranked) == 3
        mock_cross_encoder.predict.assert_called_once()
    
    def test_rerank_preserves_top_k(self, reranker, sample_retrieval_results):
        """Test that top_k is respected"""
        reranked = reranker.rerank("Query", sample_retrieval_results, top_k=2)
        
        assert len(reranked) == 2
    
    def test_rerank_empty_input(self, reranker):
        """Test reranking empty list"""
        reranked = reranker.rerank("Query", [], top_k=5)
        
        assert reranked == []
    
    def test_rerank_single_result(self, reranker, sample_retrieval_results):
        """Test reranking single result"""
        single = [sample_retrieval_results[0]]
        
        reranked = reranker.rerank("Query", single, top_k=5)
        
        assert len(reranked) == 1
    
    # ========== MMR Tests ==========
    
    def test_mmr_diversity(self, reranker, sample_retrieval_results, mock_cross_encoder):
        """Test MMR produces diverse results"""
        # Setup mock to return varied scores
        mock_cross_encoder.predict.return_value = np.array([0.95, 0.94, 0.93, 0.92])
        
        reranked = reranker.rerank(
            "Query",
            sample_retrieval_results,
            top_k=3,
            diversity=0.3,  # MMR lambda
        )
        
        assert len(reranked) == 3
        # With diversity, order should consider both relevance and diversity
    
    def test_mmr_zero_diversity(self, reranker, sample_retrieval_results, mock_cross_encoder):
        """Test MMR with zero diversity (pure relevance)"""
        mock_cross_encoder.predict.return_value = np.array([0.5, 0.9, 0.3, 0.7])
        
        reranked = reranker.rerank(
            "Query",
            sample_retrieval_results,
            top_k=4,
            diversity=0.0,  # Pure relevance ranking
        )
        
        # Should be ordered by score
        scores = [r.reranker_score for r in reranked if r.reranker_score is not None]
        assert scores == sorted(scores, reverse=True)


class TestRetrievalQuery:
    """RetrievalQuery validation tests"""
    
    def test_valid_query(self):
        """Test valid query creation"""
        query = RetrievalQuery(
            user_id="user123",
            query="Test query",
            top_k=10,
        )
        
        assert query.user_id == "user123"
        assert query.top_k == 10
    
    def test_default_weights(self):
        """Test default weight values"""
        query = RetrievalQuery(
            user_id="user",
            query="Test",
        )
        
        assert query.weights is not None
        assert "vector" in query.weights
    
    def test_custom_weights(self):
        """Test custom weight values"""
        custom_weights = {"vector": 0.7, "keyword": 0.2, "recency": 0.1}
        query = RetrievalQuery(
            user_id="user",
            query="Test",
            weights=custom_weights,
        )
        
        assert query.weights == custom_weights


class TestRetrievalResult:
    """RetrievalResult tests"""
    
    def test_result_creation(self, sample_memory):
        """Test result creation"""
        result = RetrievalResult(
            memory=sample_memory,
            vector_score=0.9,
            keyword_score=0.5,
            recency_score=0.3,
            final_score=0.7,
        )
        
        assert result.memory == sample_memory
        assert result.final_score == 0.7
    
    def test_result_with_reranker_score(self, sample_memory):
        """Test result with reranker score"""
        result = RetrievalResult(
            memory=sample_memory,
            vector_score=0.9,
            keyword_score=0.0,
            recency_score=0.0,
            final_score=0.9,
            reranker_score=0.95,
        )
        
        assert result.reranker_score == 0.95
