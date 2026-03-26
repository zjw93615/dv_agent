"""
BM25 Keyword Search

基于PostgreSQL TSVECTOR的关键词检索。

特性：
1. 原生全文索引，无需额外依赖
2. 支持中英文混合搜索
3. 与稠密检索互补，捕获精确匹配
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BM25SearchResult:
    """BM25检索结果"""
    chunk_id: str
    doc_id: str
    score: float  # ts_rank_cd 分数
    content: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BM25Searcher:
    """
    BM25关键词检索器
    
    使用PostgreSQL的全文搜索功能实现BM25-like检索。
    """
    
    def __init__(
        self,
        pg_store,  # PostgresDocumentStore
        default_top_k: int = 20,
        ts_config: str = "simple"  # PostgreSQL text search配置
    ):
        """
        初始化
        
        Args:
            pg_store: PostgreSQL存储实例
            default_top_k: 默认召回数量
            ts_config: 全文搜索配置（simple支持中英文）
        """
        self.pg_store = pg_store
        self.default_top_k = default_top_k
        self.ts_config = ts_config
        
    async def search(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[BM25SearchResult]:
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
        
        # 预处理查询
        processed_query = self._preprocess_query(query)
        
        if not processed_query.strip():
            logger.warning("Empty query after preprocessing")
            return []
        
        try:
            # 调用PostgreSQL全文搜索
            results = await self.pg_store.search_bm25(
                query=processed_query,
                tenant_id=tenant_id,
                collection_id=collection_id,
                top_k=top_k
            )
            
            # 应用额外过滤
            if filters:
                results = self._apply_filters(results, filters)
            
            # 转换结果
            search_results = []
            for row in results:
                result = BM25SearchResult(
                    chunk_id=row.get("chunk_id", ""),
                    doc_id=row.get("doc_id", ""),
                    score=float(row.get("score", 0.0)),
                    content=row.get("content", ""),
                    metadata=row.get("metadata", {})
                )
                search_results.append(result)
            
            logger.debug(f"BM25 search returned {len(search_results)} results for query: {query[:50]}...")
            return search_results
            
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    async def batch_search(
        self,
        queries: List[str],
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[BM25SearchResult]]:
        """
        批量查询检索
        
        Args:
            queries: 查询文本列表
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 每个查询返回数量
            filters: 过滤条件
            
        Returns:
            {query: [results]} 字典
        """
        # 并发执行多个搜索
        async def search_one(query: str):
            results = await self.search(
                query=query,
                tenant_id=tenant_id,
                collection_id=collection_id,
                top_k=top_k,
                filters=filters
            )
            return query, results
        
        tasks = [search_one(q) for q in queries]
        results = await asyncio.gather(*tasks)
        
        return {query: search_results for query, search_results in results}
    
    async def search_with_highlight(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        highlight_tag: str = "<mark>"
    ) -> List[Dict[str, Any]]:
        """
        带高亮的检索
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 返回数量
            highlight_tag: 高亮标签
            
        Returns:
            包含高亮内容的结果列表
        """
        top_k = top_k or self.default_top_k
        processed_query = self._preprocess_query(query)
        
        if not processed_query.strip():
            return []
        
        try:
            # 使用ts_headline进行高亮
            results = await self.pg_store.search_bm25_with_highlight(
                query=processed_query,
                tenant_id=tenant_id,
                collection_id=collection_id,
                top_k=top_k,
                highlight_options=f"StartSel={highlight_tag}, StopSel=</{highlight_tag[1:]}"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"BM25 search with highlight failed: {e}")
            return []
    
    def _preprocess_query(self, query: str) -> str:
        """
        预处理查询文本
        
        Args:
            query: 原始查询
            
        Returns:
            处理后的查询
        """
        # 移除特殊字符（保留中文、英文、数字）
        import re
        
        # 保留有意义的字符
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', query)
        
        # 压缩空白
        cleaned = ' '.join(cleaned.split())
        
        return cleaned
    
    def _apply_filters(
        self,
        results: List[Dict[str, Any]],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        应用额外过滤条件
        
        Args:
            results: 原始结果
            filters: 过滤条件
            
        Returns:
            过滤后的结果
        """
        filtered = []
        
        for result in results:
            metadata = result.get("metadata", {})
            match = True
            
            for key, value in filters.items():
                if key in metadata:
                    if isinstance(value, list):
                        if metadata[key] not in value:
                            match = False
                            break
                    elif metadata[key] != value:
                        match = False
                        break
            
            if match:
                filtered.append(result)
        
        return filtered


class BM25SearcherWithFallback(BM25Searcher):
    """
    带降级策略的BM25检索器
    
    当精确匹配无结果时，自动尝试宽松匹配。
    """
    
    async def search(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[BM25SearchResult]:
        """带降级的检索"""
        # 首先尝试标准搜索
        results = await super().search(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=top_k,
            filters=filters
        )
        
        # 如果结果太少，尝试宽松搜索
        if len(results) < 3:
            logger.debug(f"Few BM25 results ({len(results)}), trying relaxed search")
            
            # 提取关键词
            keywords = self._extract_keywords(query)
            
            if keywords and keywords != query:
                relaxed_results = await super().search(
                    query=keywords,
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    top_k=top_k,
                    filters=filters
                )
                
                # 合并结果，去重
                seen_ids = {r.chunk_id for r in results}
                for r in relaxed_results:
                    if r.chunk_id not in seen_ids:
                        # 降低宽松匹配的分数
                        r.score *= 0.8
                        results.append(r)
                        seen_ids.add(r.chunk_id)
        
        # 重新排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k or self.default_top_k]
    
    def _extract_keywords(self, query: str) -> str:
        """提取关键词"""
        # 简单的关键词提取：移除停用词
        stopwords_cn = {'的', '了', '是', '在', '有', '和', '与', '或', '等', '吗', '呢', '吧'}
        stopwords_en = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'to', 'of', 'and', 'or', 'in', 'on', 'at', 'for', 'with'}
        
        words = query.split()
        keywords = []
        
        for word in words:
            word_lower = word.lower()
            if word_lower not in stopwords_en and word not in stopwords_cn:
                keywords.append(word)
        
        return ' '.join(keywords) if keywords else query


# 便捷函数
async def bm25_search(
    query: str,
    pg_store,
    tenant_id: str,
    top_k: int = 20
) -> List[BM25SearchResult]:
    """
    快速BM25检索
    
    Args:
        query: 查询文本
        pg_store: PostgreSQL存储
        tenant_id: 租户ID
        top_k: 返回数量
        
    Returns:
        检索结果列表
    """
    searcher = BM25Searcher(pg_store)
    return await searcher.search(query, tenant_id, top_k=top_k)
