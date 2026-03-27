"""
Sparse Vector Search

基于BGE-M3稀疏向量的词汇权重检索。

特性：
1. 学习型词汇权重（优于传统TF-IDF）
2. 捕获精确词汇匹配
3. 与稠密向量互补
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SparseSearchResult:
    """稀疏检索结果"""
    chunk_id: str
    doc_id: str
    score: float  # 稀疏向量相似度分数
    content: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SparseSearcher:
    """
    稀疏向量检索器
    
    使用BGE-M3生成的词汇权重稀疏向量进行检索。
    比传统BM25更好地捕获词汇重要性。
    """
    
    def __init__(
        self,
        milvus_store,  # MilvusDocumentStore
        embedder,      # BGEM3Embedder
        collection_name: str = "doc_sparse_embeddings",
        default_top_k: int = 20
    ):
        """
        初始化
        
        Args:
            milvus_store: Milvus存储实例
            embedder: BGE-M3嵌入器
            collection_name: 稀疏向量集合名
            default_top_k: 默认召回数量
        """
        self.milvus = milvus_store
        self.embedder = embedder
        self.collection_name = collection_name
        self.default_top_k = default_top_k
        
    async def search(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SparseSearchResult]:
        """
        单查询检索
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 文档集合ID（可选）
            top_k: 返回数量
            filters: 额外过滤条件
            
        Returns:
            检索结果列表（按分数降序）
        """
        top_k = top_k or self.default_top_k
        
        # 生成查询的稀疏向量
        embedding_result = self.embedder.embed(query, return_sparse=True, return_dense=False)
        sparse_embedding = embedding_result.sparse_embedding
        
        if sparse_embedding is None or len(sparse_embedding) == 0:
            logger.warning("Failed to generate sparse embedding for query")
            return []
        
        # 构建过滤表达式
        filter_expr = self._build_filter_expr(tenant_id, collection_id, filters)
        
        # Milvus稀疏检索
        try:
            results = await self.milvus.search_sparse(
                sparse_vector=sparse_embedding,
                top_k=top_k,
                filter_expr=filter_expr
            )
            
            # 转换结果
            search_results = []
            for hit in results:
                result = SparseSearchResult(
                    chunk_id=hit.get("chunk_id", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=hit.get("score", 0.0),
                    content=hit.get("content", ""),
                    metadata=hit.get("metadata", {})
                )
                search_results.append(result)
            
            logger.debug(f"Sparse search returned {len(search_results)} results for query: {query[:50]}...")
            return search_results
            
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            return []
    
    async def batch_search(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        doc_ids: Optional[List[str]] = None
    ) -> Dict[str, List[SparseSearchResult]]:
        """
        批量查询检索
        
        Args:
            queries: 查询文本列表
            tenant_id: 租户ID
            collection_id: 文档集合ID(已废弃,使用 doc_ids)
            top_k: 每个查询返回数量
            filters: 过滤条件
            doc_ids: 文档ID列表(用于按集合过滤)
            
        Returns:
            {query: [results]} 字典
        """
        top_k = top_k or self.default_top_k
        
        # 批量生成稀疏向量
        sparse_vectors = []
        for query in queries:
            embedding_result = self.embedder.embed(query, return_sparse=True, return_dense=False)
            sparse_vectors.append(embedding_result.sparse_embedding)
        
        # 并行检索
        async def search_one(idx: int, query: str, sparse_vec):
            if sparse_vec is None or len(sparse_vec) == 0:
                return query, []
            
            try:
                results = self.milvus.search_sparse(
                    vector=sparse_vec,
                    tenant_id=tenant_id,
                    top_k=top_k,
                    collection_id=None,  # 不再使用
                    doc_ids=doc_ids  # 使用 doc_ids 过滤
                )
                
                search_results = [
                    SparseSearchResult(
                        chunk_id=hit.get("chunk_id", ""),
                        doc_id=hit.get("doc_id", ""),
                        score=hit.get("score", 0.0),
                        content=hit.get("content", ""),
                        metadata=hit.get("metadata", {})
                    )
                    for hit in results
                ]
                return query, search_results
            except Exception as e:
                logger.error(f"Batch sparse search failed for query {idx}: {e}")
                return query, []
        
        tasks = [
            search_one(i, q, v) 
            for i, (q, v) in enumerate(zip(queries, sparse_vectors))
        ]
        results = await asyncio.gather(*tasks)
        
        return {query: search_results for query, search_results in results}
    
    async def search_by_vector(
        self,
        sparse_vector: Dict[int, float],
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SparseSearchResult]:
        """
        直接使用稀疏向量检索
        
        Args:
            sparse_vector: 稀疏向量 {token_id: weight}
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 返回数量
            filters: 过滤条件
            
        Returns:
            检索结果列表
        """
        top_k = top_k or self.default_top_k
        filter_expr = self._build_filter_expr(tenant_id, collection_id, filters)
        
        try:
            results = await self.milvus.search_sparse(
                sparse_vector=sparse_vector,
                top_k=top_k,
                filter_expr=filter_expr
            )
            
            return [
                SparseSearchResult(
                    chunk_id=hit.get("chunk_id", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=hit.get("score", 0.0),
                    content=hit.get("content", ""),
                    metadata=hit.get("metadata", {})
                )
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Sparse vector search failed: {e}")
            return []
    
    async def search_with_expansion(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        expansion_factor: float = 1.2
    ) -> List[SparseSearchResult]:
        """
        带词汇扩展的检索
        
        通过增加召回数量并重新排序来模拟词汇扩展效果。
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 最终返回数量
            expansion_factor: 扩展因子（召回量=top_k * factor）
            
        Returns:
            检索结果列表
        """
        top_k = top_k or self.default_top_k
        expanded_k = int(top_k * expansion_factor)
        
        # 首先召回更多结果
        results = await self.search(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=expanded_k
        )
        
        # 返回Top-K
        return results[:top_k]
    
    def _build_filter_expr(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建Milvus过滤表达式
        """
        conditions = [f'tenant_id == "{tenant_id}"']
        
        if collection_id:
            conditions.append(f'collection_id == "{collection_id}"')
        
        if filters:
            for key, value in filters.items():
                if isinstance(value, str):
                    conditions.append(f'{key} == "{value}"')
                elif isinstance(value, (int, float)):
                    conditions.append(f'{key} == {value}')
                elif isinstance(value, list):
                    values_str = ', '.join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
                    conditions.append(f'{key} in [{values_str}]')
        
        return ' and '.join(conditions)


class HybridSparseSearcher(SparseSearcher):
    """
    混合稀疏检索器
    
    结合稀疏向量和词汇匹配提高召回率。
    """
    
    def __init__(
        self,
        milvus_store,
        embedder,
        pg_store=None,  # 可选的PostgreSQL存储（用于BM25增强）
        collection_name: str = "doc_sparse_embeddings",
        default_top_k: int = 20,
        bm25_weight: float = 0.3
    ):
        super().__init__(milvus_store, embedder, collection_name, default_top_k)
        self.pg_store = pg_store
        self.bm25_weight = bm25_weight
    
    async def search(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SparseSearchResult]:
        """混合检索"""
        top_k = top_k or self.default_top_k
        
        # 稀疏向量检索
        sparse_results = await super().search(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=top_k,
            filters=filters
        )
        
        # 如果没有BM25存储，直接返回
        if self.pg_store is None:
            return sparse_results
        
        # BM25检索增强
        try:
            bm25_results = await self.pg_store.search_bm25(
                query=query,
                tenant_id=tenant_id,
                collection_id=collection_id,
                top_k=top_k
            )
            
            # 简单合并：BM25结果补充到稀疏结果中
            seen_ids = {r.chunk_id for r in sparse_results}
            for bm25_hit in bm25_results:
                chunk_id = bm25_hit.get("chunk_id", "")
                if chunk_id not in seen_ids:
                    sparse_results.append(SparseSearchResult(
                        chunk_id=chunk_id,
                        doc_id=bm25_hit.get("doc_id", ""),
                        score=float(bm25_hit.get("score", 0.0)) * self.bm25_weight,
                        content=bm25_hit.get("content", ""),
                        metadata=bm25_hit.get("metadata", {})
                    ))
                    seen_ids.add(chunk_id)
            
            # 重新排序
            sparse_results.sort(key=lambda x: x.score, reverse=True)
            return sparse_results[:top_k]
            
        except Exception as e:
            logger.warning(f"BM25 enhancement failed: {e}")
            return sparse_results


# 便捷函数
async def sparse_search(
    query: str,
    milvus_store,
    embedder,
    tenant_id: str,
    top_k: int = 20
) -> List[SparseSearchResult]:
    """
    快速稀疏检索
    
    Args:
        query: 查询文本
        milvus_store: Milvus存储
        embedder: 嵌入器
        tenant_id: 租户ID
        top_k: 返回数量
        
    Returns:
        检索结果列表
    """
    searcher = SparseSearcher(milvus_store, embedder)
    return await searcher.search(query, tenant_id, top_k=top_k)
