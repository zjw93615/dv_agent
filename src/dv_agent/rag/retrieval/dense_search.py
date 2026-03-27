"""
Dense Vector Search

基于BGE-M3稠密向量的语义检索。

特性：
1. 高维语义匹配（1024维）
2. 支持批量查询
3. 与Milvus无缝集成
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DenseSearchResult:
    """稠密检索结果"""
    chunk_id: str
    doc_id: str
    score: float  # 相似度分数 (0-1, IP距离)
    content: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DenseSearcher:
    """
    稠密向量检索器
    
    使用Milvus进行高效的向量相似度搜索。
    """
    
    def __init__(
        self,
        milvus_store,  # MilvusDocumentStore
        embedder,      # BGEM3Embedder
        collection_name: str = "doc_dense_embeddings",
        default_top_k: int = 20
    ):
        """
        初始化
        
        Args:
            milvus_store: Milvus存储实例
            embedder: BGE-M3嵌入器
            collection_name: 稠密向量集合名
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
    ) -> List[DenseSearchResult]:
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
        
        # 生成查询向量
        embedding_result = self.embedder.embed(query, return_sparse=False, return_dense=True)
        query_vector = embedding_result.dense_embedding
        
        if query_vector is None:
            logger.error("Failed to generate dense embedding for query")
            return []
        
        # 构建过滤表达式
        filter_expr = self._build_filter_expr(tenant_id, collection_id, filters)
        
        # Milvus检索
        try:
            results = await self.milvus.search_dense(
                vector=query_vector,
                tenant_id=tenant_id,
                top_k=top_k,
                collection_id=collection_id
            )
            
            # 转换结果
            search_results = []
            for hit in results:
                result = DenseSearchResult(
                    chunk_id=hit.get("chunk_id", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=hit.get("score", 0.0),
                    content=hit.get("content", ""),
                    metadata=hit.get("metadata", {})
                )
                search_results.append(result)
            
            logger.debug(f"Dense search returned {len(search_results)} results for query: {query[:50]}...")
            return search_results
            
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            return []
    
    async def batch_search(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        doc_ids: Optional[List[str]] = None
    ) -> Dict[str, List[DenseSearchResult]]:
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
        
        # 批量生成查询向量
        query_vectors = []
        for query in queries:
            embedding_result = self.embedder.embed(query, return_sparse=False, return_dense=True)
            if embedding_result.dense_embedding is not None:
                query_vectors.append(embedding_result.dense_embedding)
            else:
                query_vectors.append(None)
        
        # 并行检索
        results_map = {}
        
        async def search_one(idx: int, query: str, vector):
            if vector is None:
                return query, []
            
            try:
                results = await self.milvus.search_dense(
                    vector=vector,
                    tenant_id=tenant_id,
                    top_k=top_k,
                    collection_id=None,  # 不再使用
                    doc_ids=doc_ids  # 使用 doc_ids 过滤
                )
                
                search_results = [
                    DenseSearchResult(
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
                logger.error(f"Batch dense search failed for query {idx}: {e}")
                return query, []
        
        # 并发执行
        tasks = [
            search_one(i, q, v) 
            for i, (q, v) in enumerate(zip(queries, query_vectors))
        ]
        results = await asyncio.gather(*tasks)
        
        for query, search_results in results:
            results_map[query] = search_results
        
        return results_map
    
    async def search_by_vector(
        self,
        query_vector: List[float],
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[DenseSearchResult]:
        """
        直接使用向量检索（跳过嵌入步骤）
        
        Args:
            query_vector: 查询向量（1024维）
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
            results = await self.milvus.search_dense(
                vector=query_vector,
                tenant_id=tenant_id,
                top_k=top_k,
                collection_id=collection_id
            )
            
            return [
                DenseSearchResult(
                    chunk_id=hit.get("chunk_id", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=hit.get("score", 0.0),
                    content=hit.get("content", ""),
                    metadata=hit.get("metadata", {})
                )
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _build_filter_expr(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建Milvus过滤表达式
        
        Args:
            tenant_id: 租户ID
            collection_id: 文档集合ID
            filters: 额外过滤条件
            
        Returns:
            Milvus表达式字符串
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
                    # IN 查询
                    values_str = ', '.join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
                    conditions.append(f'{key} in [{values_str}]')
        
        return ' and '.join(conditions)


# 便捷函数
async def dense_search(
    query: str,
    milvus_store,
    embedder,
    tenant_id: str,
    top_k: int = 20
) -> List[DenseSearchResult]:
    """
    快速稠密检索
    
    Args:
        query: 查询文本
        milvus_store: Milvus存储
        embedder: 嵌入器
        tenant_id: 租户ID
        top_k: 返回数量
        
    Returns:
        检索结果列表
    """
    searcher = DenseSearcher(milvus_store, embedder)
    return await searcher.search(query, tenant_id, top_k=top_k)
