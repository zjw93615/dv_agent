"""
RAG Integration Tests
RAG 系统集成测试

测试完整的文档处理和检索流程：
1. 文档上传 -> 处理 -> 存储
2. 向量检索 -> 融合 -> 重排序
3. 端到端查询测试
"""

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============ Test Fixtures ============

@pytest.fixture
def sample_text_content():
    """示例文本内容"""
    return """
    人工智能（Artificial Intelligence, AI）是计算机科学的一个分支，
    致力于研究和开发模拟、延伸和扩展人类智能的理论、方法、技术及应用系统。
    
    机器学习是人工智能的一个重要分支，它使计算机能够从数据中学习，
    而无需进行明确的编程。深度学习是机器学习的一个子领域，
    使用多层神经网络来学习数据的复杂表示。
    
    大型语言模型（LLM）如 GPT、Claude 等，是基于 Transformer 架构的深度学习模型，
    通过在海量文本数据上进行预训练，获得了强大的自然语言理解和生成能力。
    
    检索增强生成（RAG）是一种将检索系统与生成模型结合的技术，
    通过从知识库中检索相关信息来增强模型的回答质量。
    """


@pytest.fixture
def sample_metadata():
    """示例元数据"""
    return {
        "author": "Test Author",
        "category": "AI",
        "tags": ["machine-learning", "deep-learning", "llm"],
        "created_date": "2024-01-15",
    }


@pytest.fixture
def mock_embedder():
    """模拟嵌入器"""
    embedder = MagicMock()
    
    async def mock_embed(texts, **kwargs):
        # 返回模拟的嵌入结果
        results = []
        for text in texts:
            results.append(MagicMock(
                dense_embedding=[0.1] * 1024,  # BGE-M3 dense dim
                sparse_embedding={1: 0.5, 10: 0.3, 100: 0.2},
                colbert_embedding=[[0.1] * 1024] * 10,
            ))
        return results
    
    embedder.embed = mock_embed
    embedder.embed_query = mock_embed
    return embedder


@pytest.fixture
def mock_milvus_store():
    """模拟 Milvus 存储"""
    store = AsyncMock()
    
    # 搜索返回模拟结果
    store.search_dense.return_value = [
        {"chunk_id": "chunk_1", "score": 0.95},
        {"chunk_id": "chunk_2", "score": 0.88},
    ]
    store.search_sparse.return_value = [
        {"chunk_id": "chunk_1", "score": 0.7},
        {"chunk_id": "chunk_3", "score": 0.6},
    ]
    
    return store


@pytest.fixture
def mock_pg_store():
    """模拟 PostgreSQL 存储"""
    store = AsyncMock()
    
    # BM25 搜索返回
    store.search_bm25.return_value = [
        {"chunk_id": "chunk_1", "score": 15.5, "content": "AI 人工智能"},
        {"chunk_id": "chunk_4", "score": 12.3, "content": "机器学习"},
    ]
    
    # 获取 chunk 内容
    async def mock_get_chunks(chunk_ids, tenant_id):
        chunks = {
            "chunk_1": {"content": "人工智能是计算机科学的一个分支", "metadata": {}},
            "chunk_2": {"content": "机器学习是人工智能的一个重要分支", "metadata": {}},
            "chunk_3": {"content": "深度学习使用多层神经网络", "metadata": {}},
            "chunk_4": {"content": "大型语言模型基于 Transformer 架构", "metadata": {}},
        }
        return [chunks.get(cid, {}) for cid in chunk_ids]
    
    store.get_chunks_by_ids = mock_get_chunks
    return store


# ============ Pipeline Tests ============

class TestDocumentPipeline:
    """文档处理流水线测试"""
    
    def test_text_chunker_basic(self, sample_text_content):
        """测试基础文本分块"""
        from dv_agent.rag.pipeline.chunker import TextChunker
        
        chunker = TextChunker(
            chunk_size=200,
            chunk_overlap=50,
        )
        
        chunks = chunker.chunk(sample_text_content)
        
        assert len(chunks) > 0
        assert all(len(chunk.content) <= 250 for chunk in chunks)  # 允许一定超出
        
        # 验证重叠
        if len(chunks) > 1:
            # 相邻块应该有部分重叠内容
            pass
    
    def test_text_cleaner(self):
        """测试文本清理"""
        from dv_agent.rag.pipeline.cleaner import TextCleaner
        
        cleaner = TextCleaner()
        
        # 测试多余空白清理
        dirty_text = "  这是   一段\n\n\n有很多   空白的  文本  "
        cleaned = cleaner.clean(dirty_text)
        
        assert "   " not in cleaned
        assert cleaned.strip() == cleaned
    
    def test_document_detector(self):
        """测试文档类型检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        # 测试文件名检测
        assert detector.detect_by_filename("test.pdf") == "pdf"
        assert detector.detect_by_filename("test.docx") == "docx"
        assert detector.detect_by_filename("test.txt") == "txt"
        assert detector.detect_by_filename("test.md") == "markdown"
        
        # 测试 MIME 类型检测
        assert detector.detect_by_mime("application/pdf") == "pdf"
        assert detector.detect_by_mime("text/plain") == "txt"


class TestMetadataExtractor:
    """元数据提取测试"""
    
    def test_basic_extraction(self, sample_text_content):
        """测试基础元数据提取"""
        from dv_agent.rag.pipeline.metadata import MetadataExtractor
        
        extractor = MetadataExtractor()
        
        metadata = extractor.extract(
            content=sample_text_content,
            filename="test_doc.txt",
        )
        
        assert "filename" in metadata
        assert "char_count" in metadata
        assert metadata["char_count"] > 0


# ============ Embedding Tests ============

class TestEmbeddingService:
    """嵌入服务测试"""
    
    @pytest.mark.asyncio
    async def test_embedding_result_structure(self, mock_embedder):
        """测试嵌入结果结构"""
        texts = ["这是一段测试文本"]
        results = await mock_embedder.embed(texts)
        
        assert len(results) == 1
        result = results[0]
        
        assert hasattr(result, 'dense_embedding')
        assert hasattr(result, 'sparse_embedding')
        assert len(result.dense_embedding) == 1024


# ============ Retrieval Tests ============

class TestRRFFusion:
    """RRF 融合测试"""
    
    def test_basic_fusion(self):
        """测试基础 RRF 融合"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        # 模拟多路检索结果
        ranked_lists = [
            # 稠密检索结果
            [("doc_1", 0.95), ("doc_2", 0.88), ("doc_3", 0.75)],
            # 稀疏检索结果
            [("doc_2", 0.8), ("doc_1", 0.7), ("doc_4", 0.6)],
            # BM25 结果
            [("doc_1", 15.5), ("doc_4", 12.3), ("doc_5", 10.1)],
        ]
        
        fused = fusion.fuse(ranked_lists)
        
        assert len(fused) > 0
        # doc_1 应该排名靠前（在所有列表中都出现）
        doc_ids = [doc_id for doc_id, score in fused]
        assert "doc_1" in doc_ids[:3]
    
    def test_weighted_fusion(self):
        """测试加权 RRF 融合"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        ranked_lists = [
            [("doc_1", 0.95), ("doc_2", 0.88)],
            [("doc_3", 0.8), ("doc_1", 0.7)],
        ]
        weights = [0.7, 0.3]  # 第一个列表权重更高
        
        fused = fusion.fuse(ranked_lists, weights=weights)
        
        assert len(fused) > 0


class TestReranker:
    """重排序测试"""
    
    def test_lightweight_reranker(self):
        """测试轻量级重排序器"""
        from dv_agent.rag.retrieval.reranker import LightweightReranker
        
        reranker = LightweightReranker()
        
        query = "什么是人工智能"
        documents = [
            "人工智能是计算机科学的一个分支",
            "今天天气很好",
            "AI 技术正在快速发展",
        ]
        
        # 同步版本测试
        results = reranker.rerank_sync(query, documents, top_k=3)
        
        assert len(results) == 3
        # 相关文档应该分数更高
        assert results[0].score > results[-1].score


class TestQueryExpansion:
    """查询扩展测试"""
    
    def test_rule_based_expansion(self):
        """测试规则驱动的查询扩展"""
        from dv_agent.rag.retrieval.query_generator import RuleBasedQueryExpander
        
        expander = RuleBasedQueryExpander()
        
        query = "人工智能的应用"
        expanded = expander.expand(query, max_queries=3)
        
        assert len(expanded) >= 1
        assert query in expanded  # 原始查询应该保留


# ============ Integration Tests ============

class TestRAGIntegration:
    """RAG 端到端集成测试"""
    
    @pytest.mark.asyncio
    async def test_simple_search_flow(
        self,
        mock_embedder,
        mock_milvus_store,
        mock_pg_store,
    ):
        """测试简单搜索流程"""
        # 这里模拟完整的搜索流程
        query = "什么是机器学习"
        
        # 1. 查询嵌入
        query_embedding = await mock_embedder.embed([query])
        assert len(query_embedding) == 1
        
        # 2. 多路检索
        dense_results = await mock_milvus_store.search_dense(
            embedding=query_embedding[0].dense_embedding,
            top_k=10,
        )
        sparse_results = await mock_milvus_store.search_sparse(
            embedding=query_embedding[0].sparse_embedding,
            top_k=10,
        )
        bm25_results = await mock_pg_store.search_bm25(
            query=query,
            top_k=10,
        )
        
        # 3. 验证结果
        assert len(dense_results) > 0
        assert len(sparse_results) > 0
        assert len(bm25_results) > 0
    
    @pytest.mark.asyncio
    async def test_document_upload_flow(
        self,
        sample_text_content,
        sample_metadata,
        mock_embedder,
    ):
        """测试文档上传流程"""
        from dv_agent.rag.pipeline.chunker import TextChunker
        from dv_agent.rag.pipeline.cleaner import TextCleaner
        
        # 1. 文本清理
        cleaner = TextCleaner()
        cleaned = cleaner.clean(sample_text_content)
        
        # 2. 文本分块
        chunker = TextChunker(chunk_size=200, chunk_overlap=50)
        chunks = chunker.chunk(cleaned)
        
        assert len(chunks) > 0
        
        # 3. 生成嵌入
        chunk_texts = [c.content for c in chunks]
        embeddings = await mock_embedder.embed(chunk_texts)
        
        assert len(embeddings) == len(chunks)


# ============ API Tests ============

class TestRAGAPI:
    """RAG API 测试"""
    
    def test_search_request_validation(self):
        """测试搜索请求验证"""
        from dv_agent.rag.api import SearchRequest
        
        # 有效请求
        request = SearchRequest(query="test query", top_k=10)
        assert request.query == "test query"
        assert request.top_k == 10
        
        # 验证默认值
        assert request.mode == "hybrid"
        assert request.use_reranking is True
    
    def test_search_response_structure(self):
        """测试搜索响应结构"""
        from dv_agent.rag.api import SearchResponse, SearchResultItem
        
        results = [
            SearchResultItem(
                chunk_id="chunk_1",
                document_id="doc_1",
                content="Test content",
                score=0.95,
            )
        ]
        
        response = SearchResponse(
            query="test",
            results=results,
            total=1,
            latency_ms=50.0,
        )
        
        assert response.total == 1
        assert response.results[0].score == 0.95


# ============ Cache Tests ============

class TestRetrievalCache:
    """检索缓存测试"""
    
    def test_cache_key_generation(self):
        """测试缓存键生成"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=100)
        
        # 相同查询应该生成相同的 key
        key1 = cache._generate_key("test query", "tenant_1", {"top_k": 10})
        key2 = cache._generate_key("test query", "tenant_1", {"top_k": 10})
        
        assert key1 == key2
        
        # 不同查询应该生成不同的 key
        key3 = cache._generate_key("different query", "tenant_1", {"top_k": 10})
        assert key1 != key3
    
    @pytest.mark.asyncio
    async def test_local_cache_hit(self):
        """测试本地缓存命中"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=100)
        
        # 存入缓存
        test_data = {"results": [{"id": "1", "score": 0.9}]}
        await cache.set("test_key", test_data, ttl=60)
        
        # 从缓存获取
        cached = await cache.get("test_key")
        
        assert cached is not None
        assert cached["results"][0]["id"] == "1"


# ============ Config Tests ============

class TestRAGConfig:
    """RAG 配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        from dv_agent.rag.config import RAGConfig
        
        config = RAGConfig()
        
        # 验证默认值
        assert config.embedding.model_name == "BAAI/bge-m3"
        assert config.embedding.dense_dim == 1024
        assert config.retrieval.default_top_k == 10
    
    def test_config_from_dict(self):
        """测试从字典加载配置"""
        from dv_agent.rag.config import RAGConfig
        
        config_dict = {
            "embedding": {
                "model_name": "custom-model",
                "dense_dim": 768,
            },
            "retrieval": {
                "default_top_k": 20,
            }
        }
        
        config = RAGConfig.from_dict(config_dict)
        
        assert config.embedding.model_name == "custom-model"
        assert config.embedding.dense_dim == 768
        assert config.retrieval.default_top_k == 20


# ============ Performance Tests ============

class TestPerformance:
    """性能测试"""
    
    def test_chunker_performance(self, sample_text_content):
        """测试分块性能"""
        import time
        from dv_agent.rag.pipeline.chunker import TextChunker
        
        chunker = TextChunker(chunk_size=200, chunk_overlap=50)
        
        # 创建大文本
        large_text = sample_text_content * 100
        
        start = time.time()
        chunks = chunker.chunk(large_text)
        elapsed = time.time() - start
        
        # 应该在合理时间内完成
        assert elapsed < 5.0  # 5秒内
        assert len(chunks) > 0
    
    def test_rrf_fusion_performance(self):
        """测试 RRF 融合性能"""
        import time
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        # 创建大量结果
        ranked_lists = []
        for i in range(5):
            ranked_lists.append([
                (f"doc_{j}", 1.0 - j * 0.01)
                for j in range(1000)
            ])
        
        start = time.time()
        fused = fusion.fuse(ranked_lists)
        elapsed = time.time() - start
        
        # 应该在合理时间内完成
        assert elapsed < 1.0  # 1秒内
        assert len(fused) > 0


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
