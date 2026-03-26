"""
BGE-M3 Embedding Service Unit Tests
向量化服务单元测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from dv_agent.rag.embedding import BGEM3Embedder, EmbeddingResult
from dv_agent.rag.embedding.bge_m3 import SparseVector


class TestSparseVector:
    """稀疏向量测试"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        sparse = SparseVector(
            indices=[1, 2, 3],
            values=[0.5, 0.3, 0.2]
        )
        
        assert len(sparse) == 3
        assert sparse.indices == [1, 2, 3]
        assert sparse.values == [0.5, 0.3, 0.2]
    
    def test_to_dict(self):
        """测试转换为字典"""
        sparse = SparseVector(
            indices=[100, 200],
            values=[0.8, 0.4]
        )
        
        result = sparse.to_dict()
        assert result == {100: 0.8, 200: 0.4}
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {10: 0.9, 20: 0.5, 30: 0.1}
        sparse = SparseVector.from_dict(data)
        
        assert len(sparse) == 3
        assert set(sparse.indices) == {10, 20, 30}
    
    def test_filter_by_weight_min_threshold(self):
        """测试按最小权重过滤"""
        sparse = SparseVector(
            indices=[1, 2, 3, 4, 5],
            values=[0.1, 0.2, 0.3, 0.4, 0.5]
        )
        
        filtered = sparse.filter_by_weight(min_weight=0.3)
        
        assert len(filtered) == 3
        assert all(v >= 0.3 for v in filtered.values)
    
    def test_filter_by_weight_top_k(self):
        """测试按 Top-K 过滤"""
        sparse = SparseVector(
            indices=[1, 2, 3, 4, 5],
            values=[0.1, 0.5, 0.3, 0.4, 0.2]
        )
        
        filtered = sparse.filter_by_weight(top_k=3)
        
        assert len(filtered) == 3
        # 应该保留权重最高的3个：0.5, 0.4, 0.3
        assert max(filtered.values) == 0.5
    
    def test_filter_combined(self):
        """测试组合过滤"""
        sparse = SparseVector(
            indices=[1, 2, 3, 4, 5],
            values=[0.1, 0.5, 0.3, 0.4, 0.2]
        )
        
        filtered = sparse.filter_by_weight(min_weight=0.2, top_k=2)
        
        # 先过滤 >= 0.2: [0.5, 0.3, 0.4, 0.2]
        # 再取 Top-2: [0.5, 0.4]
        assert len(filtered) == 2
        assert 0.5 in filtered.values
        assert 0.4 in filtered.values
    
    def test_empty_after_filter(self):
        """测试过滤后为空"""
        sparse = SparseVector(
            indices=[1, 2],
            values=[0.1, 0.2]
        )
        
        filtered = sparse.filter_by_weight(min_weight=0.5)
        
        assert len(filtered) == 0


class TestEmbeddingResult:
    """向量化结果测试"""
    
    def test_dense_dim(self):
        """测试稠密向量维度"""
        result = EmbeddingResult(
            text="test",
            dense_embedding=[0.1] * 1024
        )
        
        assert result.dense_dim == 1024
    
    def test_sparse_len(self):
        """测试稀疏向量长度"""
        result = EmbeddingResult(
            text="test",
            sparse_embedding=SparseVector(
                indices=[1, 2, 3],
                values=[0.5, 0.3, 0.2]
            )
        )
        
        assert result.sparse_len == 3
    
    def test_sparse_len_none(self):
        """测试稀疏向量为空时"""
        result = EmbeddingResult(text="test")
        assert result.sparse_len == 0


class TestBGEM3Embedder:
    """BGE-M3 向量化服务测试"""
    
    def test_initialization(self):
        """测试初始化"""
        embedder = BGEM3Embedder(
            model_name="test-model",
            cache_enabled=True,
            sparse_weight_threshold=0.1,
            sparse_top_k=100,
        )
        
        assert embedder.model_name == "test-model"
        assert embedder.cache_enabled
        assert embedder.sparse_weight_threshold == 0.1
        assert embedder.sparse_top_k == 100
        assert not embedder.is_loaded
    
    def test_device_detection_cpu(self):
        """测试 CPU 设备检测"""
        with patch.dict('sys.modules', {'torch': None}):
            embedder = BGEM3Embedder()
            # 如果没有 torch 或 CUDA，应该使用 CPU
            assert embedder.device in ["cpu", "cuda"]
    
    @patch('dv_agent.rag.embedding.bge_m3.BGEM3Embedder._load_model')
    def test_embed_single(self, mock_load):
        """测试单个文本向量化"""
        embedder = BGEM3Embedder(cache_enabled=False)
        
        # Mock 模型
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": [np.array([0.1] * 1024)],
            "lexical_weights": [{100: 0.5, 200: 0.3}]
        }
        embedder._model = mock_model
        embedder._model_loaded = True
        
        result = embedder.embed("测试文本")
        
        assert result.text == "测试文本"
        assert result.dense_dim == 1024
        assert result.sparse_len > 0
    
    @patch('dv_agent.rag.embedding.bge_m3.BGEM3Embedder._load_model')
    def test_embed_batch(self, mock_load):
        """测试批量向量化"""
        embedder = BGEM3Embedder(cache_enabled=False)
        
        # Mock 模型
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": [np.array([0.1] * 1024) for _ in range(3)],
            "lexical_weights": [{100: 0.5} for _ in range(3)]
        }
        embedder._model = mock_model
        embedder._model_loaded = True
        
        texts = ["文本1", "文本2", "文本3"]
        results = embedder.embed_batch(texts, batch_size=2)
        
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.text == texts[i]
    
    def test_cache_hit(self):
        """测试缓存命中"""
        embedder = BGEM3Embedder(cache_enabled=True, cache_ttl=3600)
        
        # 预填充缓存
        cached_result = EmbeddingResult(
            text="cached",
            dense_embedding=[0.1] * 1024,
            sparse_embedding=SparseVector(indices=[1], values=[0.5])
        )
        import time
        cache_key = embedder._get_cache_key("cached")
        embedder._cache[cache_key] = (cached_result, time.time())
        
        # 获取应该命中缓存
        result = embedder._get_from_cache("cached")
        
        assert result is not None
        assert result.text == "cached"
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        embedder = BGEM3Embedder(cache_enabled=True)
        
        result = embedder._get_from_cache("not-cached")
        
        assert result is None
    
    def test_cache_expired(self):
        """测试缓存过期"""
        embedder = BGEM3Embedder(cache_enabled=True, cache_ttl=1)
        
        # 预填充已过期的缓存
        cached_result = EmbeddingResult(text="expired")
        import time
        cache_key = embedder._get_cache_key("expired")
        embedder._cache[cache_key] = (cached_result, time.time() - 10)
        
        result = embedder._get_from_cache("expired")
        
        assert result is None
    
    def test_cache_disabled(self):
        """测试缓存禁用"""
        embedder = BGEM3Embedder(cache_enabled=False)
        
        # 即使手动设置缓存，也应该返回 None
        embedder._set_cache("test", EmbeddingResult(text="test"))
        result = embedder._get_from_cache("test")
        
        assert result is None
    
    def test_clear_cache(self):
        """测试清空缓存"""
        embedder = BGEM3Embedder(cache_enabled=True)
        
        # 填充一些缓存
        import time
        for i in range(5):
            key = embedder._get_cache_key(f"text{i}")
            embedder._cache[key] = (EmbeddingResult(text=f"text{i}"), time.time())
        
        assert len(embedder._cache) == 5
        
        embedder.clear_cache()
        
        assert len(embedder._cache) == 0
    
    def test_get_cache_stats(self):
        """测试获取缓存统计"""
        embedder = BGEM3Embedder(cache_enabled=True, cache_ttl=100)
        
        # 填充一些缓存
        import time
        for i in range(3):
            key = embedder._get_cache_key(f"valid{i}")
            embedder._cache[key] = (EmbeddingResult(text=f"valid{i}"), time.time())
        
        # 添加过期的
        for i in range(2):
            key = embedder._get_cache_key(f"expired{i}")
            embedder._cache[key] = (EmbeddingResult(text=f"expired{i}"), time.time() - 200)
        
        stats = embedder.get_cache_stats()
        
        assert stats["total_entries"] == 5
        assert stats["valid_entries"] == 3
        assert stats["expired_entries"] == 2
    
    def test_embedding_dim(self):
        """测试向量维度"""
        embedder = BGEM3Embedder()
        assert embedder.embedding_dim == 1024
    
    def test_from_config(self):
        """测试从配置创建"""
        config = {
            "model_name": "custom-model",
            "device": "cpu",
            "use_fp16": False,
            "cache_enabled": True,
            "cache_ttl": 7200,
            "sparse_weight_threshold": 0.05,
            "sparse_top_k": 200,
        }
        
        embedder = BGEM3Embedder.from_config(config)
        
        assert embedder.model_name == "custom-model"
        assert embedder.device == "cpu"
        assert not embedder.use_fp16
        assert embedder.cache_enabled
        assert embedder.cache_ttl == 7200
        assert embedder.sparse_weight_threshold == 0.05
        assert embedder.sparse_top_k == 200
    
    @patch('dv_agent.rag.embedding.bge_m3.BGEM3Embedder._load_model')
    def test_embed_query(self, mock_load):
        """测试查询向量化"""
        embedder = BGEM3Embedder(cache_enabled=False)
        
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": [np.array([0.1] * 1024)],
            "lexical_weights": [{100: 0.5}]
        }
        embedder._model = mock_model
        embedder._model_loaded = True
        
        result = embedder.embed_query("查询文本")
        
        assert result.text == "查询文本"
        assert result.dense_dim == 1024
    
    @patch('dv_agent.rag.embedding.bge_m3.BGEM3Embedder._load_model')
    def test_embed_documents(self, mock_load):
        """测试文档向量化"""
        embedder = BGEM3Embedder(cache_enabled=False)
        
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": [np.array([0.1] * 1024) for _ in range(2)],
            "lexical_weights": [{100: 0.5} for _ in range(2)]
        }
        embedder._model = mock_model
        embedder._model_loaded = True
        
        docs = ["文档1", "文档2"]
        results = embedder.embed_documents(docs)
        
        assert len(results) == 2
    
    def test_sparse_filtering_in_embed(self):
        """测试向量化时的稀疏过滤"""
        embedder = BGEM3Embedder(
            cache_enabled=False,
            sparse_weight_threshold=0.3,
            sparse_top_k=2,
        )
        
        # Mock 模型返回较多的稀疏权重
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": [np.array([0.1] * 1024)],
            "lexical_weights": [{1: 0.1, 2: 0.2, 3: 0.3, 4: 0.4, 5: 0.5}]
        }
        embedder._model = mock_model
        embedder._model_loaded = True
        
        result = embedder.embed("测试")
        
        # 过滤后应该只有权重 >= 0.3 的 Top-2
        assert result.sparse_len == 2
        assert all(v >= 0.3 for v in result.sparse_embedding.values)


# pytest fixtures
@pytest.fixture
def embedder():
    """创建测试用向量化服务"""
    return BGEM3Embedder(
        cache_enabled=False,
        sparse_weight_threshold=0.0,
    )


@pytest.fixture
def mock_embedder():
    """创建带 Mock 的向量化服务"""
    embedder = BGEM3Embedder(cache_enabled=False)
    
    mock_model = MagicMock()
    mock_model.encode.return_value = {
        "dense_vecs": [np.array([0.1] * 1024)],
        "lexical_weights": [{i: 0.5 - i * 0.1 for i in range(5)}]
    }
    embedder._model = mock_model
    embedder._model_loaded = True
    
    return embedder


def test_integration_embed_and_cache(mock_embedder):
    """集成测试：向量化和缓存"""
    mock_embedder.cache_enabled = True
    mock_embedder.cache_ttl = 3600
    
    # 第一次调用
    result1 = mock_embedder.embed("测试文本")
    call_count_after_first = mock_embedder._model.encode.call_count
    
    # 第二次调用（应该命中缓存）
    result2 = mock_embedder.embed("测试文本")
    call_count_after_second = mock_embedder._model.encode.call_count
    
    assert result1.text == result2.text
    assert result1.dense_embedding == result2.dense_embedding
    assert call_count_after_first == call_count_after_second  # 没有额外调用
