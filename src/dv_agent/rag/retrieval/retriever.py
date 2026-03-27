"""
RAG-Fusion Retriever

检索编排器 - 整合多路召回、RRF融合、精排等组件。

完整检索流程：
1. 查询扩展：生成多个查询变体
2. 并行召回：稠密向量 + 稀疏向量 + BM25
3. RRF融合：合并多路结果
4. 精排重排：Cross-Encoder精确排序
5. 返回结果
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from . import SearchMode, RetrievalQuery, RetrievalResult, RetrievalResponse
from .query_generator import QueryGenerator, QueryExpansionConfig
from .dense_search import DenseSearcher, DenseSearchResult
from .sparse_search import SparseSearcher, SparseSearchResult
from .bm25_search import BM25Searcher, BM25SearchResult
from .rrf_fusion import WeightedRRFFusion, FusionResult
from .reranker import Reranker, LightweightReranker, RerankResult

logger = logging.getLogger(__name__)


@dataclass
class RetrieverConfig:
    """检索器配置"""
    # 召回配置
    dense_top_k: int = 30              # 稠密检索召回数
    sparse_top_k: int = 30             # 稀疏检索召回数
    bm25_top_k: int = 30               # BM25召回数
    
    # RRF配置
    rrf_k: int = 60                    # RRF平滑参数
    dense_weight: float = 1.0          # 稠密检索权重
    sparse_weight: float = 0.8         # 稀疏检索权重
    bm25_weight: float = 0.6           # BM25权重
    
    # 查询扩展配置
    num_query_variations: int = 3      # 查询变体数量
    use_hyde: bool = False             # 是否使用HyDE
    
    # 重排配置
    enable_rerank: bool = True         # 是否启用重排
    rerank_top_k: int = 50             # 送入重排的候选数
    use_lightweight_rerank: bool = False  # 使用轻量级重排
    
    # 结果配置
    default_top_k: int = 10            # 默认返回数量
    min_score_threshold: float = 0.0   # 最低分数阈值


class HybridRetriever:
    """
    混合检索器
    
    整合稠密向量、稀疏向量、BM25三路检索，
    通过RRF融合和Reranker精排，实现高精度检索。
    """
    
    def __init__(
        self,
        # 存储组件
        milvus_store,           # MilvusDocumentStore
        pg_store,               # PostgresDocumentStore
        embedder,               # BGEM3Embedder
        
        # 可选组件
        llm_client=None,        # LLM客户端（用于查询扩展）
        reranker: Optional[Reranker] = None,
        
        # 配置
        config: Optional[RetrieverConfig] = None
    ):
        """
        初始化
        
        Args:
            milvus_store: Milvus向量存储
            pg_store: PostgreSQL文档存储
            embedder: BGE-M3嵌入器
            llm_client: LLM客户端（可选，用于查询扩展）
            reranker: 重排器（可选，默认自动创建）
            config: 检索配置
        """
        self.milvus_store = milvus_store
        self.pg_store = pg_store
        self.embedder = embedder
        self.llm_client = llm_client
        self.config = config or RetrieverConfig()
        
        # 初始化子组件
        self._init_components(reranker)
        
        logger.info(f"HybridRetriever initialized with config: {self.config}")
    
    def _init_components(self, reranker: Optional[Reranker]):
        """初始化子组件"""
        # 查询生成器
        query_config = QueryExpansionConfig(
            num_variations=self.config.num_query_variations,
            use_hyde=self.config.use_hyde
        )
        self.query_generator = QueryGenerator(
            llm_client=self.llm_client,
            config=query_config
        )
        
        # 检索器
        self.dense_searcher = DenseSearcher(
            milvus_store=self.milvus_store,
            embedder=self.embedder,
            default_top_k=self.config.dense_top_k
        )
        
        self.sparse_searcher = SparseSearcher(
            milvus_store=self.milvus_store,
            embedder=self.embedder,
            default_top_k=self.config.sparse_top_k
        )
        
        self.bm25_searcher = BM25Searcher(
            pg_store=self.pg_store,
            default_top_k=self.config.bm25_top_k
        )
        
        # RRF融合
        self.fusion = WeightedRRFFusion(
            k=self.config.rrf_k,
            weights={
                "dense": self.config.dense_weight,
                "sparse": self.config.sparse_weight,
                "bm25": self.config.bm25_weight
            }
        )
        
        # 重排器
        if reranker:
            self.reranker = reranker
        elif self.config.enable_rerank:
            if self.config.use_lightweight_rerank:
                self.reranker = LightweightReranker()
            else:
                self.reranker = Reranker()
        else:
            self.reranker = None
    
    async def retrieve(
        self,
        query: RetrievalQuery
    ) -> RetrievalResponse:
        """
        执行检索
        
        Args:
            query: 检索查询
            
        Returns:
            检索响应
        """
        start_time = time.time()
        debug_info = {}
        
        # Step 1: 查询扩展
        if query.expand_queries:
            expanded_queries = await self.query_generator.generate(
                query.query,
                num_variations=self.config.num_query_variations
            )
        else:
            expanded_queries = [query.query]
        
        debug_info["expanded_queries"] = expanded_queries
        
        # Step 2: 并行多路召回
        recall_results = await self._parallel_recall(
            queries=expanded_queries,
            tenant_id=query.tenant_id,
            collection_id=query.collection_id,
            mode=query.mode,
            filters=query.filters
        )
        
        debug_info["recall_counts"] = {
            source: len(results) 
            for source, results in recall_results.items()
        }
        
        # Step 3: RRF融合
        fusion_result = self._fuse_results(recall_results)
        
        debug_info["fusion_candidates"] = fusion_result.total_candidates
        
        # Step 4: 精排（可选）
        if query.rerank and self.reranker and fusion_result.candidates:
            final_results = await self._rerank_results(
                query=query.query,
                candidates=fusion_result.candidates,
                top_k=query.top_k
            )
        else:
            # 直接截取
            final_results = self._convert_fusion_to_results(
                fusion_result.candidates[:query.top_k]
            )
        
        # 构建响应
        latency_ms = (time.time() - start_time) * 1000
        
        response = RetrievalResponse(
            query=query.query,
            expanded_queries=expanded_queries,
            results=final_results,
            total_candidates=fusion_result.total_candidates,
            latency_ms=latency_ms,
            debug_info=debug_info
        )
        
        logger.info(
            f"Retrieval completed: query='{query.query[:50]}...' "
            f"results={len(final_results)} latency={latency_ms:.1f}ms"
        )
        
        return response
    
    async def _parallel_recall(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str],
        mode: SearchMode,
        filters: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        并行执行多路召回
        
        Returns:
            {source_name: [results]} 字典
        """
        results_by_source = {}
        tasks = []
        
        # 根据模式决定启用哪些检索
        enable_dense = mode in [
            SearchMode.DENSE_ONLY,
            SearchMode.HYBRID_DENSE_BM25,
            SearchMode.HYBRID_ALL
        ]
        enable_sparse = mode in [
            SearchMode.SPARSE_ONLY,
            SearchMode.HYBRID_ALL
        ]
        enable_bm25 = mode in [
            SearchMode.BM25_ONLY,
            SearchMode.HYBRID_DENSE_BM25,
            SearchMode.HYBRID_ALL
        ]
        
        # 创建检索任务
        if enable_dense:
            tasks.append(self._dense_recall(queries, tenant_id, collection_id, filters))
        
        if enable_sparse:
            tasks.append(self._sparse_recall(queries, tenant_id, collection_id, filters))
        
        if enable_bm25:
            tasks.append(self._bm25_recall(queries, tenant_id, collection_id, filters))
        
        # 并行执行
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果
        task_idx = 0
        if enable_dense:
            if not isinstance(task_results[task_idx], Exception):
                results_by_source["dense"] = task_results[task_idx]
            else:
                logger.error(f"Dense recall failed: {task_results[task_idx]}")
                results_by_source["dense"] = []
            task_idx += 1
        
        if enable_sparse:
            if not isinstance(task_results[task_idx], Exception):
                results_by_source["sparse"] = task_results[task_idx]
            else:
                logger.error(f"Sparse recall failed: {task_results[task_idx]}")
                results_by_source["sparse"] = []
            task_idx += 1
        
        if enable_bm25:
            if not isinstance(task_results[task_idx], Exception):
                results_by_source["bm25"] = task_results[task_idx]
            else:
                logger.error(f"BM25 recall failed: {task_results[task_idx]}")
                results_by_source["bm25"] = []
        
        return results_by_source
    
    async def _dense_recall(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """稠密向量召回"""
        all_results = []
        seen_ids = set()
        
        # 如果指定了 collection_id,先从 PG 查询该集合的文档列表
        doc_ids = None
        if collection_id:
            doc_ids = await self._get_collection_doc_ids(tenant_id, collection_id)
            if not doc_ids:
                logger.warning(f"No documents found in collection {collection_id}")
                return []
        
        # 批量检索(不再传递 collection_id,而是传递 doc_ids)
        results_map = await self.dense_searcher.batch_search(
            queries=queries,
            tenant_id=tenant_id,
            collection_id=None,  # 不再使用
            top_k=self.config.dense_top_k,
            filters=filters,
            doc_ids=doc_ids  # 使用 doc_ids 过滤
        )
        
        # 合并去重
        for query, results in results_map.items():
            for r in results:
                if r.chunk_id not in seen_ids:
                    all_results.append({
                        "chunk_id": r.chunk_id,
                        "doc_id": r.doc_id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata
                    })
                    seen_ids.add(r.chunk_id)
        
        # 按分数排序
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:self.config.dense_top_k]
    
    async def _sparse_recall(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """稀疏向量召回"""
        all_results = []
        seen_ids = set()
        
        # 如果指定了 collection_id,先从 PG 查询该集合的文档列表
        doc_ids = None
        if collection_id:
            doc_ids = await self._get_collection_doc_ids(tenant_id, collection_id)
            if not doc_ids:
                logger.warning(f"No documents found in collection {collection_id}")
                return []
        
        results_map = await self.sparse_searcher.batch_search(
            queries=queries,
            tenant_id=tenant_id,
            collection_id=None,  # 不再使用
            top_k=self.config.sparse_top_k,
            filters=filters,
            doc_ids=doc_ids  # 使用 doc_ids 过滤
        )
        
        for query, results in results_map.items():
            for r in results:
                if r.chunk_id not in seen_ids:
                    all_results.append({
                        "chunk_id": r.chunk_id,
                        "doc_id": r.doc_id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata
                    })
                    seen_ids.add(r.chunk_id)
        
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:self.config.sparse_top_k]
    
    async def _bm25_recall(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """BM25关键词召回"""
        all_results = []
        seen_ids = set()
        
        results_map = await self.bm25_searcher.batch_search(
            queries=queries,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=self.config.bm25_top_k,
            filters=filters
        )
        
        for query, results in results_map.items():
            for r in results:
                if r.chunk_id not in seen_ids:
                    all_results.append({
                        "chunk_id": r.chunk_id,
                        "doc_id": r.doc_id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata
                    })
                    seen_ids.add(r.chunk_id)
        
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:self.config.bm25_top_k]
    
    def _fuse_results(
        self,
        results_by_source: Dict[str, List[Dict[str, Any]]]
    ) -> FusionResult:
        """RRF融合"""
        return self.fusion.fuse(
            results_by_source=results_by_source,
            top_k=self.config.rerank_top_k
        )
    
    async def _rerank_results(
        self,
        query: str,
        candidates: List,
        top_k: int
    ) -> List[RetrievalResult]:
        """重排结果"""
        # 转换为重排输入格式
        rerank_input = [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "content": c.content,
                "score": c.rrf_score,
                "metadata": c.metadata
            }
            for c in candidates
        ]
        
        # 执行重排
        reranked = await self.reranker.rerank(
            query=query,
            candidates=rerank_input,
            top_k=top_k
        )
        
        # 转换为结果格式
        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                doc_id=r.doc_id,
                content=r.content,
                score=r.final_score,
                source_scores={
                    "rerank": r.rerank_score,
                    "rrf": r.original_score
                },
                metadata=r.metadata
            )
            for r in reranked
        ]
    
    def _convert_fusion_to_results(
        self,
        candidates: List
    ) -> List[RetrievalResult]:
        """将融合结果转换为最终结果"""
        return [
            RetrievalResult(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                content=c.content,
                score=c.rrf_score,
                source_scores=c.source_scores,
                metadata=c.metadata
            )
            for c in candidates
        ]
    
    async def _get_collection_doc_ids(
        self,
        tenant_id: str,
        collection_id: str
    ) -> Optional[List[str]]:
        """
        从 PostgreSQL 查询集合中的所有文档ID
        
        Args:
            tenant_id: 租户ID
            collection_id: 集合ID
            
        Returns:
            文档ID列表(字符串),如果集合不存在或为空则返回 None
        """
        try:
            # 调用 PG 查询集合文档
            docs = await self.pg_store.list_documents(
                tenant_id=tenant_id,
                collection_id=collection_id,
                limit=10000  # 假设一个集合不会超过1万个文档
            )
            
            if not docs:
                return None
            
            # 提取 doc_id 并转换为字符串(PostgreSQL 返回的字段名是 "doc_id")
            doc_ids = [str(doc["doc_id"]) for doc in docs]
            logger.debug(f"Found {len(doc_ids)} documents in collection {collection_id}")
            return doc_ids
            
        except Exception as e:
            logger.error(f"Failed to get collection doc_ids: {e}", exc_info=True)
            return None
    
    async def simple_search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        collection_id: Optional[str] = None
    ) -> List[RetrievalResult]:
        """
        简化检索接口
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            top_k: 返回数量
            collection_id: 文档集合ID
            
        Returns:
            检索结果列表
        """
        retrieval_query = RetrievalQuery(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=top_k
        )
        
        response = await self.retrieve(retrieval_query)
        return response.results


# 便捷函数
async def hybrid_search(
    query: str,
    tenant_id: str,
    milvus_store,
    pg_store,
    embedder,
    top_k: int = 10,
    collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    快速混合检索
    
    Args:
        query: 查询文本
        tenant_id: 租户ID
        milvus_store: Milvus存储
        pg_store: PostgreSQL存储
        embedder: 嵌入器
        top_k: 返回数量
        collection_id: 文档集合ID
        
    Returns:
        检索结果列表
    """
    retriever = HybridRetriever(
        milvus_store=milvus_store,
        pg_store=pg_store,
        embedder=embedder
    )
    
    results = await retriever.simple_search(
        query=query,
        tenant_id=tenant_id,
        top_k=top_k,
        collection_id=collection_id
    )
    
    return [
        {
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "content": r.content,
            "score": r.score,
            "metadata": r.metadata
        }
        for r in results
    ]
