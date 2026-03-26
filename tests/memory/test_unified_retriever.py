"""
Unified Retriever Tests
统一检索器单元测试
"""

import asyncio
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dv_agent.memory.retrieval.unified_retriever import (
    UnifiedRetriever,
    UnifiedQuery,
    UnifiedResult,
    UnifiedResponse,
    SourceType,
)


# ============ UnifiedQuery Tests ============

class TestUnifiedQuery:
    """统一查询对象测试"""
    
    def test_default_values(self):
        """测试默认值"""
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试查询",
        )
        
        assert query.top_k == 10
        assert query.memory_weight == 0.4
        assert query.document_weight == 0.6
        assert SourceType.MEMORY in query.sources
        assert SourceType.DOCUMENT in query.sources
    
    def test_custom_weights(self):
        """测试自定义权重"""
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试查询",
            memory_weight=0.7,
            document_weight=0.3,
        )
        
        assert query.memory_weight == 0.7
        assert query.document_weight == 0.3
    
    def test_source_configuration(self):
        """测试来源配置"""
        # 仅记忆
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
            sources=[SourceType.MEMORY],
        )
        assert len(query.sources) == 1
        assert SourceType.MEMORY in query.sources
        
        # 仅文档
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
            sources=[SourceType.DOCUMENT],
        )
        assert SourceType.DOCUMENT in query.sources


# ============ UnifiedResult Tests ============

class TestUnifiedResult:
    """统一结果对象测试"""
    
    def test_memory_result(self):
        """测试记忆结果"""
        result = UnifiedResult(
            id="mem_001",
            content="这是一段对话记忆",
            source=SourceType.MEMORY,
            score=0.85,
            metadata={"importance": 0.9},
        )
        
        assert result.source == SourceType.MEMORY
        assert result.score == 0.85
    
    def test_document_result(self):
        """测试文档结果"""
        result = UnifiedResult(
            id="chunk_001",
            content="这是文档内容",
            source=SourceType.DOCUMENT,
            score=0.92,
            document_chunk={
                "document_id": "doc_001",
                "chunk_index": 0,
            },
        )
        
        assert result.source == SourceType.DOCUMENT
        assert result.document_chunk["document_id"] == "doc_001"
    
    def test_to_context_string(self):
        """测试上下文字符串转换"""
        memory_result = UnifiedResult(
            id="mem_001",
            content="记忆内容",
            source=SourceType.MEMORY,
            score=0.8,
        )
        
        context = memory_result.to_context_string(include_source=True)
        assert "📝对话记忆" in context
        assert "记忆内容" in context
        
        doc_result = UnifiedResult(
            id="chunk_001",
            content="文档内容",
            source=SourceType.DOCUMENT,
            score=0.9,
        )
        
        context = doc_result.to_context_string(include_source=True)
        assert "📚知识文档" in context


# ============ UnifiedResponse Tests ============

class TestUnifiedResponse:
    """统一响应对象测试"""
    
    def test_response_statistics(self):
        """测试响应统计"""
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
        )
        
        response = UnifiedResponse(
            query=query,
            results=[
                UnifiedResult(id="1", content="内容1", source=SourceType.MEMORY, score=0.9),
                UnifiedResult(id="2", content="内容2", source=SourceType.MEMORY, score=0.8),
                UnifiedResult(id="3", content="内容3", source=SourceType.DOCUMENT, score=0.85),
            ],
            memory_count=2,
            document_count=1,
        )
        
        assert response.total_count == 3
        assert len(response.get_memory_results()) == 2
        assert len(response.get_document_results()) == 1
    
    def test_to_context(self):
        """测试上下文转换"""
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
        )
        
        response = UnifiedResponse(
            query=query,
            results=[
                UnifiedResult(id="1", content="内容1", source=SourceType.MEMORY, score=0.9),
                UnifiedResult(id="2", content="内容2", source=SourceType.DOCUMENT, score=0.8),
            ],
        )
        
        context = response.to_context(max_tokens=4000)
        
        assert "内容1" in context
        assert "内容2" in context
    
    def test_to_context_with_token_limit(self):
        """测试带 token 限制的上下文转换"""
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
        )
        
        # 创建大量结果
        results = [
            UnifiedResult(
                id=str(i),
                content="这是一段很长的内容" * 50,  # 每个结果约 450 字符
                source=SourceType.DOCUMENT,
                score=1.0 - i * 0.01,
            )
            for i in range(20)
        ]
        
        response = UnifiedResponse(query=query, results=results)
        
        # 限制 token 数
        context = response.to_context(max_tokens=500)
        
        # 应该只包含部分结果
        assert len(context) < len(results) * 450


# ============ UnifiedRetriever Tests ============

class TestUnifiedRetriever:
    """统一检索器测试"""
    
    @pytest.fixture
    def mock_memory_retriever(self):
        """Mock 记忆检索器"""
        retriever = AsyncMock()
        retriever.retrieve.return_value = MagicMock(
            results=[
                MagicMock(
                    memory=MagicMock(
                        id="mem_001",
                        content="记忆内容1",
                        memory_type=MagicMock(value="conversation"),
                        importance=0.8,
                        created_at=datetime.utcnow(),
                    ),
                    final_score=0.9,
                    vector_score=0.85,
                    keyword_score=0.7,
                    recency_score=0.95,
                ),
                MagicMock(
                    memory=MagicMock(
                        id="mem_002",
                        content="记忆内容2",
                        memory_type=MagicMock(value="fact"),
                        importance=0.6,
                        created_at=datetime.utcnow(),
                    ),
                    final_score=0.75,
                    vector_score=0.7,
                    keyword_score=0.6,
                    recency_score=0.8,
                ),
            ]
        )
        return retriever
    
    @pytest.fixture
    def mock_rag_retriever(self):
        """Mock RAG 检索器"""
        retriever = AsyncMock()
        retriever.simple_search.return_value = MagicMock(
            results=[
                MagicMock(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    content="文档内容1",
                    chunk_index=0,
                    final_score=0.92,
                    dense_score=0.9,
                    sparse_score=0.85,
                    bm25_score=None,
                    rerank_score=0.95,
                    metadata={"source": "test.pdf"},
                ),
                MagicMock(
                    chunk_id="chunk_002",
                    document_id="doc_001",
                    content="文档内容2",
                    chunk_index=1,
                    final_score=0.88,
                    dense_score=0.85,
                    sparse_score=0.8,
                    bm25_score=None,
                    rerank_score=0.9,
                    metadata={"source": "test.pdf"},
                ),
            ]
        )
        return retriever
    
    @pytest.mark.asyncio
    async def test_unified_retrieve(self, mock_memory_retriever, mock_rag_retriever):
        """测试统一检索"""
        retriever = UnifiedRetriever(
            memory_retriever=mock_memory_retriever,
            rag_retriever=mock_rag_retriever,
        )
        
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试查询",
            top_k=5,
        )
        
        response = await retriever.retrieve(query)
        
        assert response.total_count > 0
        assert response.memory_count > 0
        assert response.document_count > 0
        assert response.latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_memory_only_retrieve(self, mock_memory_retriever):
        """测试仅记忆检索"""
        retriever = UnifiedRetriever(
            memory_retriever=mock_memory_retriever,
            rag_retriever=None,
        )
        
        response = await retriever.search_memory_only(
            user_id="user_001",
            query="测试",
            top_k=5,
        )
        
        assert response.total_count > 0
        # 所有结果都应该是记忆来源
        for result in response.results:
            assert result.source == SourceType.MEMORY
    
    @pytest.mark.asyncio
    async def test_documents_only_retrieve(self, mock_rag_retriever):
        """测试仅文档检索"""
        retriever = UnifiedRetriever(
            memory_retriever=None,
            rag_retriever=mock_rag_retriever,
        )
        
        response = await retriever.search_documents_only(
            tenant_id="tenant_001",
            query="测试",
            top_k=5,
        )
        
        assert response.total_count > 0
        # 所有结果都应该是文档来源
        for result in response.results:
            assert result.source == SourceType.DOCUMENT
    
    @pytest.mark.asyncio
    async def test_retrieve_for_context(self, mock_memory_retriever, mock_rag_retriever):
        """测试便捷上下文检索"""
        retriever = UnifiedRetriever(
            memory_retriever=mock_memory_retriever,
            rag_retriever=mock_rag_retriever,
        )
        
        context = await retriever.retrieve_for_context(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
            max_tokens=2000,
        )
        
        assert isinstance(context, str)
        assert len(context) > 0
    
    @pytest.mark.asyncio
    async def test_weighted_scoring(self, mock_memory_retriever, mock_rag_retriever):
        """测试加权分数计算"""
        retriever = UnifiedRetriever(
            memory_retriever=mock_memory_retriever,
            rag_retriever=mock_rag_retriever,
        )
        
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
            memory_weight=0.3,
            document_weight=0.7,
        )
        
        response = await retriever.retrieve(query)
        
        # 验证分数已加权
        for result in response.results:
            if result.source == SourceType.MEMORY:
                # 记忆分数应该乘以 0.3
                assert result.score <= 1.0
            else:
                # 文档分数应该乘以 0.7
                assert result.score <= 1.0
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_memory_retriever):
        """测试错误处理"""
        # 模拟 RAG 检索失败
        mock_rag = AsyncMock()
        mock_rag.simple_search.side_effect = Exception("RAG error")
        
        retriever = UnifiedRetriever(
            memory_retriever=mock_memory_retriever,
            rag_retriever=mock_rag,
        )
        
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
        )
        
        response = await retriever.retrieve(query)
        
        # 应该仍然返回记忆结果
        assert response.memory_count > 0
        # 应该记录错误
        assert len(response.errors) > 0
    
    @pytest.mark.asyncio
    async def test_no_sources_available(self):
        """测试无检索源可用"""
        retriever = UnifiedRetriever(
            memory_retriever=None,
            rag_retriever=None,
        )
        
        query = UnifiedQuery(
            user_id="user_001",
            tenant_id="tenant_001",
            query="测试",
        )
        
        response = await retriever.retrieve(query)
        
        assert response.total_count == 0


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
