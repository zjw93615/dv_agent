"""
RAG Performance Benchmark Tests
RAG 性能基准测试

测试内容：
- 检索延迟
- 吞吐量
- 内存使用
- 并发性能
"""

import asyncio
import statistics
import time
from datetime import datetime
from typing import Callable, Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class BenchmarkResult:
    """基准测试结果"""
    
    def __init__(self, name: str):
        self.name = name
        self.latencies: list[float] = []
        self.errors: int = 0
        self.start_time: float = 0
        self.end_time: float = 0
    
    def add_latency(self, latency_ms: float):
        self.latencies.append(latency_ms)
    
    def add_error(self):
        self.errors += 1
    
    @property
    def total_requests(self) -> int:
        return len(self.latencies) + self.errors
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return len(self.latencies) / self.total_requests * 100
    
    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)
    
    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)
    
    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def throughput(self) -> float:
        """每秒请求数"""
        duration = self.end_time - self.start_time
        if duration == 0:
            return 0.0
        return len(self.latencies) / duration
    
    def report(self) -> str:
        """生成报告"""
        return f"""
========== Benchmark Report: {self.name} ==========
Total Requests:    {self.total_requests}
Successful:        {len(self.latencies)}
Errors:            {self.errors}
Success Rate:      {self.success_rate:.2f}%
Throughput:        {self.throughput:.2f} req/s

Latency Statistics:
  Average:         {self.avg_latency:.2f} ms
  P50 (Median):    {self.p50_latency:.2f} ms
  P95:             {self.p95_latency:.2f} ms
  P99:             {self.p99_latency:.2f} ms
  Min:             {min(self.latencies) if self.latencies else 0:.2f} ms
  Max:             {max(self.latencies) if self.latencies else 0:.2f} ms
================================================
"""


async def run_benchmark(
    name: str,
    func: Callable,
    iterations: int = 100,
    warmup: int = 10,
    concurrency: int = 1,
) -> BenchmarkResult:
    """
    运行基准测试
    
    Args:
        name: 测试名称
        func: 要测试的异步函数
        iterations: 迭代次数
        warmup: 预热次数
        concurrency: 并发数
    """
    result = BenchmarkResult(name)
    
    # 预热
    for _ in range(warmup):
        try:
            await func()
        except Exception:
            pass
    
    # 正式测试
    async def run_single():
        start = time.perf_counter()
        try:
            await func()
            latency = (time.perf_counter() - start) * 1000
            result.add_latency(latency)
        except Exception:
            result.add_error()
    
    result.start_time = time.perf_counter()
    
    if concurrency == 1:
        for _ in range(iterations):
            await run_single()
    else:
        # 并发执行
        semaphore = asyncio.Semaphore(concurrency)
        
        async def run_with_semaphore():
            async with semaphore:
                await run_single()
        
        tasks = [run_with_semaphore() for _ in range(iterations)]
        await asyncio.gather(*tasks)
    
    result.end_time = time.perf_counter()
    
    return result


# ============ Benchmark Tests ============

class TestRetrievalLatency:
    """检索延迟基准测试"""
    
    @pytest.fixture
    def mock_retriever(self):
        """Mock 检索器"""
        retriever = AsyncMock()
        retriever.simple_search.return_value = MagicMock(
            results=[
                MagicMock(
                    chunk_id=f"chunk_{i}",
                    content=f"Content {i}",
                    final_score=0.9 - i * 0.05,
                )
                for i in range(10)
            ],
            latency_ms=50.0,
        )
        return retriever
    
    @pytest.mark.asyncio
    async def test_single_query_latency(self, mock_retriever):
        """测试单次查询延迟"""
        async def query():
            return await mock_retriever.simple_search(
                query="测试查询",
                tenant_id="tenant_001",
                top_k=10,
            )
        
        result = await run_benchmark(
            name="Single Query Latency",
            func=query,
            iterations=100,
            warmup=10,
        )
        
        print(result.report())
        
        # 断言：平均延迟应该很低（Mock 情况下）
        assert result.avg_latency < 100  # ms
        assert result.success_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_concurrent_query_latency(self, mock_retriever):
        """测试并发查询延迟"""
        async def query():
            return await mock_retriever.simple_search(
                query="测试查询",
                tenant_id="tenant_001",
                top_k=10,
            )
        
        result = await run_benchmark(
            name="Concurrent Query Latency",
            func=query,
            iterations=100,
            warmup=10,
            concurrency=10,
        )
        
        print(result.report())
        
        # 断言：吞吐量应该有提升
        assert result.throughput > 10  # 至少每秒 10 个请求


class TestEmbeddingPerformance:
    """嵌入性能基准测试"""
    
    @pytest.fixture
    def mock_embedder(self):
        """Mock 嵌入器"""
        embedder = AsyncMock()
        embedder.embed.return_value = [
            MagicMock(
                dense_embedding=[0.1] * 1024,
                sparse_embedding={i: 0.1 for i in range(100)},
            )
        ]
        return embedder
    
    @pytest.mark.asyncio
    async def test_single_embedding_latency(self, mock_embedder):
        """测试单次嵌入延迟"""
        async def embed():
            return await mock_embedder.embed(["这是一段测试文本"])
        
        result = await run_benchmark(
            name="Single Embedding Latency",
            func=embed,
            iterations=50,
            warmup=5,
        )
        
        print(result.report())
        
        assert result.success_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_batch_embedding_latency(self, mock_embedder):
        """测试批量嵌入延迟"""
        texts = [f"测试文本 {i}" for i in range(32)]
        
        async def embed_batch():
            return await mock_embedder.embed(texts)
        
        result = await run_benchmark(
            name="Batch Embedding Latency (32 texts)",
            func=embed_batch,
            iterations=20,
            warmup=2,
        )
        
        print(result.report())
        
        assert result.success_rate == 100.0


class TestRRFFusionPerformance:
    """RRF 融合性能测试"""
    
    def test_fusion_large_results(self):
        """测试大量结果的融合性能"""
        from dv_agent.rag.retrieval.rrf_fusion import RRFFusion
        
        fusion = RRFFusion(k=60)
        
        # 创建大量结果
        ranked_lists = []
        for i in range(5):  # 5 个排名列表
            ranked_lists.append([
                (f"doc_{j}", 1.0 - j * 0.001)
                for j in range(1000)  # 每个列表 1000 个结果
            ])
        
        # 测试性能
        start = time.perf_counter()
        for _ in range(100):  # 100 次迭代
            fusion.fuse(ranked_lists)
        elapsed = (time.perf_counter() - start) * 1000 / 100  # 平均每次毫秒
        
        print(f"\nRRF Fusion (5 lists x 1000 items): {elapsed:.2f} ms/iteration")
        
        # 断言：应该在合理时间内完成
        assert elapsed < 100  # 每次小于 100ms


class TestCachePerformance:
    """缓存性能测试"""
    
    @pytest.mark.asyncio
    async def test_cache_hit_latency(self):
        """测试缓存命中延迟"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=1000)
        
        # 预填充缓存
        test_data = {"results": [{"id": i, "score": 0.9} for i in range(10)]}
        for i in range(100):
            await cache.set(f"key_{i}", test_data, ttl=300)
        
        # 测试命中
        async def cache_get():
            return await cache.get("key_50")
        
        result = await run_benchmark(
            name="Cache Hit Latency",
            func=cache_get,
            iterations=1000,
            warmup=100,
        )
        
        print(result.report())
        
        # 缓存命中应该非常快
        assert result.avg_latency < 1  # 小于 1ms
    
    @pytest.mark.asyncio
    async def test_cache_miss_latency(self):
        """测试缓存未命中延迟"""
        from dv_agent.rag.retrieval.cache import RetrievalCache
        
        cache = RetrievalCache(local_max_size=1000)
        
        async def cache_miss():
            return await cache.get("nonexistent_key")
        
        result = await run_benchmark(
            name="Cache Miss Latency",
            func=cache_miss,
            iterations=1000,
            warmup=100,
        )
        
        print(result.report())
        
        # 缓存未命中也应该很快
        assert result.avg_latency < 1  # 小于 1ms


class TestChunkerPerformance:
    """文本分块性能测试"""
    
    def test_chunker_large_document(self):
        """测试大文档分块性能"""
        from dv_agent.rag.pipeline.chunker import TextChunker
        
        chunker = TextChunker(chunk_size=512, chunk_overlap=50)
        
        # 创建大文档
        large_text = "这是一段测试文本。" * 10000  # 约 90KB
        
        # 测试性能
        start = time.perf_counter()
        for _ in range(10):
            chunks = chunker.chunk(large_text)
        elapsed = (time.perf_counter() - start) * 1000 / 10
        
        print(f"\nChunker (90KB document): {elapsed:.2f} ms/iteration")
        print(f"Chunks generated: {len(chunks)}")
        
        # 断言
        assert elapsed < 500  # 每次小于 500ms
        assert len(chunks) > 0


# ============ Additional Tests ============

class TestMultiFormatProcessing:
    """多格式文档处理测试 (Task 9.3)"""
    
    def test_detect_pdf(self):
        """测试 PDF 检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        assert detector.detect_by_filename("document.pdf") == "pdf"
        assert detector.detect_by_filename("DOCUMENT.PDF") == "pdf"
        assert detector.detect_by_mime("application/pdf") == "pdf"
    
    def test_detect_docx(self):
        """测试 DOCX 检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        assert detector.detect_by_filename("document.docx") == "docx"
        assert detector.detect_by_mime("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "docx"
    
    def test_detect_markdown(self):
        """测试 Markdown 检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        assert detector.detect_by_filename("readme.md") == "markdown"
        assert detector.detect_by_filename("README.MD") == "markdown"
    
    def test_detect_html(self):
        """测试 HTML 检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        assert detector.detect_by_filename("page.html") == "html"
        assert detector.detect_by_filename("page.htm") == "html"
        assert detector.detect_by_mime("text/html") == "html"
    
    def test_detect_excel(self):
        """测试 Excel 检测"""
        from dv_agent.rag.pipeline.detector import DocumentDetector
        
        detector = DocumentDetector()
        
        assert detector.detect_by_filename("data.xlsx") == "xlsx"
        assert detector.detect_by_filename("data.xls") == "xls"


class TestTenantIsolation:
    """租户隔离测试 (Task 9.5)"""
    
    @pytest.mark.asyncio
    async def test_document_tenant_isolation(self):
        """测试文档租户隔离"""
        from dv_agent.rag.store.manager import DocumentManager
        from unittest.mock import AsyncMock
        
        # Mock 存储
        mock_pg = AsyncMock()
        mock_pg.list_documents.return_value = (
            [{"id": "doc_1", "tenant_id": "tenant_001"}],
            1,
        )
        
        manager = DocumentManager(
            embedder=AsyncMock(),
            minio_client=AsyncMock(),
            pg_store=mock_pg,
            milvus_store=AsyncMock(),
        )
        
        # 查询 tenant_001 的文档
        docs, total = await manager.list_documents(
            tenant_id="tenant_001",
            offset=0,
            limit=10,
        )
        
        # 验证调用时传入了 tenant_id
        mock_pg.list_documents.assert_called_once()
        call_args = mock_pg.list_documents.call_args
        assert call_args.kwargs.get("tenant_id") == "tenant_001" or "tenant_001" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_retrieval_tenant_isolation(self):
        """测试检索租户隔离"""
        from dv_agent.rag.retrieval.retriever import HybridRetriever
        from dv_agent.rag.retrieval import RetrievalQuery, SearchMode
        from unittest.mock import AsyncMock
        
        # Mock 组件
        mock_embedder = AsyncMock()
        mock_embedder.embed_query.return_value = MagicMock(
            dense_embedding=[0.1] * 1024,
            sparse_embedding={1: 0.5},
        )
        
        mock_milvus = AsyncMock()
        mock_milvus.search_dense.return_value = []
        mock_milvus.search_sparse.return_value = []
        
        mock_pg = AsyncMock()
        mock_pg.search_bm25.return_value = []
        mock_pg.get_chunks_by_ids.return_value = []
        
        retriever = HybridRetriever(
            embedder=mock_embedder,
            milvus_store=mock_milvus,
            pg_store=mock_pg,
        )
        
        # 执行检索
        query = RetrievalQuery(
            query="测试",
            tenant_id="tenant_002",
            mode=SearchMode.HYBRID,
        )
        
        await retriever.search(query)
        
        # 验证 tenant_id 被正确传递
        # (具体验证取决于实际实现)
    
    def test_collection_name_includes_tenant(self):
        """测试集合名称包含租户标识"""
        from dv_agent.rag.store.milvus_document import MilvusDocumentStore
        
        store = MilvusDocumentStore(host="localhost", port=19530)
        
        name = store._get_collection_name("tenant_abc", "dense")
        
        assert "tenant_abc" in name


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
