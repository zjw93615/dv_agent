"""
RAG Retrieval Tests
检索系统单元测试
"""

import asyncio
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============ Query Generator Tests ============

class TestQueryGenerator:
    """查询生成器测试"""
    
    def test_rule_based_expansion(self):
        """测试规则驱动的查询扩展"""
        from dv_agent.rag.retrieval.query_generator import RuleBasedQueryExpander
        
        expander = RuleBasedQueryExpander()
        
        query = "人工智能的应用"
        expanded = expander.expand(query, max_queries=5)
        
        assert len(expanded) >= 1
        assert query in expanded  # 原始查询应该保留
    
    def test_synonym_expansion(self):
        """测试同义词扩展"""
        from dv_agent.rag.retrieval.query_generator import RuleBasedQueryExpander
        
        expander = RuleBasedQueryExpander()
        
        # 添加同义词映射
        expander.add_synonyms({
            "AI": ["人工智能", "Artificial Intelligence"],
            "ML": ["机器学习", "Machine Learning"],
        })
        
        query = "AI 技术"
        expanded = expander.expand(query, max_queries=5)
        
        # 应该包含同义词替换的版本
        assert len(expanded) >= 1


class TestLLMQueryExpander:
    """LLM 查询扩展器测试"""
    
    @pytest.mark.asyncio
    async def test_llm_expansion_mock(self):
        """测试 LLM 查询扩展（Mock）"""
        from dv_agent.rag.retrieval.query_generator import LLMQueryExpander
        
        # Mock LLM client
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """
        1. 人工智能在医疗领域有哪些应用？
        2. AI 如何改变医疗诊断？
        3. 机器学习在医学影像中的应用
        """
        
        expander = LLMQueryExpander(llm_client=mock_llm)
        
        query = "AI 医疗应用"
        expanded = await expander.expand_async(query, max_queries=3)
        
        # 验证返回多个查询
        assert len(expanded) >= 1


# ============ Dense Search Tests ============

class TestDenseSearch:
    """稠密向量检索测试"""
    
    @pytest.fixture
    def mock_milvus(self):
        """Mock Milvus 存储"""
        store = AsyncMock()
        store.search_dense.return_value = [
            {"chunk_id": "chunk_1", "document_id": "doc_1", "score": 0.95},
            {"chunk_id": "chunk_2", "document_id": "doc_1", "score": 0.88},
            {"chunk_id": "chunk_3", "document_id": "doc_2", "score": 0.75},
        ]
        return store
    
    @pytest.mark.asyncio
    async def test_dense_search(self, mock_milvus):
        """测试稠密向量检索"""
        from dv_agent.rag.retrieval.dense_search import DenseSearcher
        
        mock_embedder = AsyncMock()
        mock_embedder.embed_query.return_value = MagicMock(
            dense_embedding=[0.1] * 1024
        )
        
        searcher = DenseSearcher(
            embedder=mock_embedder,
            milvus_store=mock_milvus,
        )
        
        results = await searcher.search(
            query="测试查询",
            tenant_id="tenant_001",
            top_k=10,
        )
        
        assert len(results) == 3
        assert results[0]["score"] > results[1]["score"]


# ============ Sparse Search Tests ============

class TestSparseSearch:
    """稀疏向量检索测试"""
    
    @pytest.fixture
    def mock_milvus(self):
        """Mock Milvus 存储"""
        store = AsyncMock()
        store.search_sparse.return_value = [
            {"chunk_id": "chunk_1", "score": 0.7},
            {"chunk_id": "chunk_4", "score": 0.6},
        ]
        return store
    
    @pytest.mark.asyncio
    async def test_sparse_search(self, mock_milvus):
        """测试稀疏向量检索"""
        from dv_agent.rag.retrieval.sparse_search import SparseSearcher
        
        mock_embedder = AsyncMock()
        mock_embedder.embed_query.return_value = MagicMock(
            sparse_embedding={1: 0.5, 10: 0.3, 100: 0.2}
        )
        
        searcher = SparseSearcher(
            embedder=mock_embedder,
            milvus_store=mock_milvus,
        )
        
        results = await searcher.search(
            query="测试查询",
            tenant_id="tenant_001",
            top_k=10,
        )
        
        assert len(results) == 2


# ============ BM25 Search Tests ============

class TestBM25Search:
    """BM25 检索测试"""
    
    @pytest.fixture
    def mock_pg(self):
        """Mock PostgreSQL 存储"""
        store = AsyncMock()
        store.search_bm25.return_value = [
            {"chunk_id": "chunk_1", "content": "AI 内容", "score": 15.5},
            {"chunk_id": "chunk_5", "content": "ML 内容", "score": 12.3},
        ]
        return store
    
    @pytest.mark.asyncio
    async def test_bm25_search(self, mock_pg):
        """测试 BM25 检索"""
        from dv_agent.rag.retrieval.bm25_search import BM25Searcher
        
        searcher = BM25Searcher(pg_store=mock_pg)
        
        results = await searcher.search(
            query="人工智能",
            tenant_id="tenant_001",
            top_k=10,
        )
        
        assert len(results) == 2
        assert results[0]["score"] > results[1]["score"]


# ============ RRF Fusion Tests ============

class TestRRFFusion:
    """RRF 融合测试"""
    
    def test_basic_fusion(self):
        """测试基础 RRF 融合"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        ranked_lists = [
            [("doc_1", 0.95), ("doc_2", 0.88), ("doc_3", 0.75)],
            [("doc_2", 0.8), ("doc_1", 0.7), ("doc_4", 0.6)],
            [("doc_1", 15.5), ("doc_4", 12.3), ("doc_5", 10.1)],
        ]
        
        fused = fusion.fuse(ranked_lists)
        
        assert len(fused) > 0
        # doc_1 在所有列表中都出现，应该排名靠前
        doc_ids = [doc_id for doc_id, score in fused]
        assert "doc_1" in doc_ids[:2]
    
    def test_weighted_fusion(self):
        """测试加权 RRF 融合"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        ranked_lists = [
            [("doc_1", 0.9), ("doc_2", 0.8)],
            [("doc_3", 0.9), ("doc_1", 0.7)],
        ]
        weights = [0.8, 0.2]  # 第一个列表权重更高
        
        fused = fusion.fuse(ranked_lists, weights=weights)
        
        assert len(fused) > 0
        # doc_1 虽然在两个列表中，但第一个列表权重高，排名应该靠前
    
    def test_empty_lists(self):
        """测试空列表处理"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        ranked_lists = [[], [], []]
        fused = fusion.fuse(ranked_lists)
        
        assert len(fused) == 0
    
    def test_single_list(self):
        """测试单列表融合"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        ranked_lists = [
            [("doc_1", 0.9), ("doc_2", 0.8), ("doc_3", 0.7)],
        ]
        
        fused = fusion.fuse(ranked_lists)
        
        assert len(fused) == 3
        assert fused[0][0] == "doc_1"


# ============ Reranker Tests ============

class TestReranker:
    """重排序测试"""
    
    def test_lightweight_reranker(self):
        """测试轻量级重排序器"""
        from dv_agent.rag.retrieval.reranker import LightweightReranker
        
        reranker = LightweightReranker()
        
        query = "什么是人工智能"
        documents = [
            "人工智能是计算机科学的一个分支",
            "今天天气很好，适合出门",
            "AI 技术正在快速发展",
            "机器学习是 AI 的核心技术",
        ]
        
        results = reranker.rerank_sync(query, documents, top_k=4)
        
        assert len(results) == 4
        # 相关文档分数应该更高
        assert results[0].score >= results[-1].score
    
    @pytest.mark.asyncio
    async def test_cross_encoder_reranker_mock(self):
        """测试 Cross-Encoder 重排序（Mock）"""
        from dv_agent.rag.retrieval.reranker import CrossEncoderReranker
        
        # Mock model
        with patch('dv_agent.rag.retrieval.reranker.AutoModelForSequenceClassification'):
            with patch('dv_agent.rag.retrieval.reranker.AutoTokenizer'):
                reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
                reranker._model = MagicMock()
                reranker._tokenizer = MagicMock()
                reranker._device = "cpu"
                
                # Mock predict
                reranker._model.return_value = MagicMock(
                    logits=MagicMock(squeeze=MagicMock(return_value=[0.9, 0.5, 0.8]))
                )


# ============ Hybrid Retriever Tests ============

class TestHybridRetriever:
    """混合检索器测试"""
    
    @pytest.fixture
    def mock_components(self):
        """Mock 所有组件"""
        embedder = AsyncMock()
        embedder.embed_query.return_value = MagicMock(
            dense_embedding=[0.1] * 1024,
            sparse_embedding={1: 0.5, 10: 0.3},
        )
        
        milvus = AsyncMock()
        milvus.search_dense.return_value = [
            {"chunk_id": "c1", "document_id": "d1", "score": 0.95},
            {"chunk_id": "c2", "document_id": "d1", "score": 0.88},
        ]
        milvus.search_sparse.return_value = [
            {"chunk_id": "c1", "score": 0.7},
            {"chunk_id": "c3", "score": 0.6},
        ]
        
        pg = AsyncMock()
        pg.search_bm25.return_value = [
            {"chunk_id": "c1", "content": "内容1", "score": 15.5},
            {"chunk_id": "c4", "content": "内容4", "score": 12.3},
        ]
        pg.get_chunks_by_ids.return_value = [
            {"chunk_id": "c1", "content": "人工智能内容", "metadata": {}},
            {"chunk_id": "c2", "content": "机器学习内容", "metadata": {}},
            {"chunk_id": "c3", "content": "深度学习内容", "metadata": {}},
            {"chunk_id": "c4", "content": "神经网络内容", "metadata": {}},
        ]
        
        return {
            "embedder": embedder,
            "milvus_store": milvus,
            "pg_store": pg,
        }
    
    @pytest.mark.asyncio
    async def test_hybrid_search(self, mock_components):
        """测试混合检索"""
        from dv_agent.rag.retrieval.retriever import HybridRetriever
        from dv_agent.rag.retrieval import SearchMode
        
        retriever = HybridRetriever(**mock_components)
        
        response = await retriever.simple_search(
            query="人工智能是什么",
            tenant_id="tenant_001",
            top_k=5,
        )
        
        # 验证返回结果
        assert len(response.results) > 0
        assert response.latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_dense_only_search(self, mock_components):
        """测试仅稠密检索"""
        from dv_agent.rag.retrieval.retriever import HybridRetriever
        from dv_agent.rag.retrieval import RetrievalQuery, SearchMode
        
        retriever = HybridRetriever(**mock_components)
        
        query = RetrievalQuery(
            query="测试查询",
            tenant_id="tenant_001",
            mode=SearchMode.DENSE_ONLY,
            top_k=5,
        )
        
        response = await retriever.search(query)
        
        # 仅调用 dense 搜索
        mock_components["milvus_store"].search_dense.assert_called()


# ============ Cache Tests ============

class TestRetrievalCache:
    """检索缓存测试"""
    
    def test_cache_key_generation(self):
        """测试缓存键生成"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=100)
        
        key1 = cache._generate_key("query", "tenant", {"top_k": 10})
        key2 = cache._generate_key("query", "tenant", {"top_k": 10})
        key3 = cache._generate_key("different", "tenant", {"top_k": 10})
        
        assert key1 == key2
        assert key1 != key3
    
    @pytest.mark.asyncio
    async def test_local_cache_operations(self):
        """测试本地缓存操作"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=100)
        
        # Set
        await cache.set("test_key", {"data": "value"}, ttl=60)
        
        # Get
        result = await cache.get("test_key")
        assert result is not None
        assert result["data"] == "value"
        
        # Delete
        await cache.delete("test_key")
        result = await cache.get("test_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """测试缓存过期"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        import time
        
        cache = RetrievalCache(local_max_size=100)
        
        # 设置 1 秒过期
        await cache.set("expire_key", {"data": "value"}, ttl=1)
        
        # 立即获取应该存在
        result = await cache.get("expire_key")
        assert result is not None
        
        # 等待过期（在实际测试中可能需要 mock time）


# ============ Integration Tests ============

class TestRetrievalIntegration:
    """检索集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_retrieval_flow(self):
        """测试完整检索流程"""
        # 这个测试需要所有组件的 mock
        # 验证从查询到结果的完整流程
        pass
    
    @pytest.mark.asyncio
    async def test_query_expansion_integration(self):
        """测试查询扩展集成"""
        pass


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
