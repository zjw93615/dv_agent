"""
Memory Retriever
记忆检索器 - 多路召回与结果融合

提供三种检索路径：
1. 向量检索（Milvus）- 语义相似度
2. 关键词检索（PG TSVECTOR）- 精确匹配
3. 时序检索（PG）- 最近访问
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from ..config import MemoryConfig
from ..long_term import LongTermMemory, SearchResult
from ..models import Memory, MemoryType

logger = logging.getLogger(__name__)


@dataclass
class RetrievalQuery:
    """检索查询"""
    user_id: str
    query: str
    top_k: int = 20
    memory_types: Optional[list[MemoryType]] = None
    
    # 检索路径开关
    use_vector: bool = True
    use_keyword: bool = True
    use_recency: bool = True
    
    # 权重配置
    vector_weight: float = 0.5
    keyword_weight: float = 0.3
    recency_weight: float = 0.2
    
    # 过滤条件
    min_importance: Optional[float] = None
    max_age_days: Optional[int] = None
    
    # 是否跳过缓存
    skip_cache: bool = False


@dataclass
class RetrievalResult:
    """检索结果"""
    query: RetrievalQuery
    results: list[SearchResult] = field(default_factory=list)
    
    # 统计信息
    vector_count: int = 0
    keyword_count: int = 0
    recency_count: int = 0
    
    # 性能指标
    latency_ms: float = 0.0
    from_cache: bool = False
    
    @property
    def total_count(self) -> int:
        return len(self.results)


class MemoryRetriever:
    """
    记忆检索器
    
    职责：
    - 多路并行召回
    - 结果去重与合并
    - 分数计算与排序
    - 结果缓存
    """
    
    # 缓存 Key 前缀
    CACHE_PREFIX = "cache:memory"
    
    def __init__(
        self,
        long_term: LongTermMemory,
        redis_client=None,
        config: Optional[MemoryConfig] = None,
    ):
        """
        初始化检索器
        
        Args:
            long_term: 长期记忆存储
            redis_client: Redis 客户端（用于缓存）
            config: 配置
        """
        self.long_term = long_term
        self.redis = redis_client
        self.config = config or MemoryConfig()
        
        # 缓存配置
        self._cache_ttl = 300  # 5分钟
    
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """
        执行检索
        
        Args:
            query: 检索查询
            
        Returns:
            检索结果
        """
        start_time = datetime.utcnow()
        
        # 尝试从缓存获取
        if not query.skip_cache and self.redis:
            cached = await self._get_cached(query)
            if cached:
                cached.latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                cached.from_cache = True
                return cached
        
        # 并行执行多路检索
        tasks = []
        task_names = []
        
        if query.use_vector:
            tasks.append(self._search_vector(query))
            task_names.append("vector")
        
        if query.use_keyword:
            tasks.append(self._search_keyword(query))
            task_names.append("keyword")
        
        if query.use_recency:
            tasks.append(self._search_recency(query))
            task_names.append("recency")
        
        if not tasks:
            # 没有启用任何检索路径
            return RetrievalResult(query=query)
        
        # 并行执行
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果
        vector_results: list[tuple[UUID, float]] = []
        keyword_results: list[tuple[Memory, float]] = []
        recency_results: list[Memory] = []
        
        for name, results in zip(task_names, results_list):
            if isinstance(results, Exception):
                logger.warning(f"{name} search failed: {results}")
                continue
            
            if name == "vector":
                vector_results = results
            elif name == "keyword":
                keyword_results = results
            elif name == "recency":
                recency_results = results
        
        # 合并与评分
        merged = await self._merge_results(
            query=query,
            vector_results=vector_results,
            keyword_results=keyword_results,
            recency_results=recency_results,
        )
        
        # 应用过滤
        filtered = self._apply_filters(merged, query)
        
        # 构建结果
        result = RetrievalResult(
            query=query,
            results=filtered[:query.top_k],
            vector_count=len(vector_results),
            keyword_count=len(keyword_results),
            recency_count=len(recency_results),
            latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
        )
        
        # 缓存结果
        if not query.skip_cache and self.redis:
            await self._cache_result(query, result)
        
        logger.debug(
            f"Retrieved {result.total_count} memories for user {query.user_id} "
            f"(vector={result.vector_count}, keyword={result.keyword_count}, "
            f"recency={result.recency_count}) in {result.latency_ms:.1f}ms"
        )
        
        return result
    
    async def _search_vector(
        self,
        query: RetrievalQuery,
    ) -> list[tuple[UUID, float]]:
        """
        向量检索
        
        Args:
            query: 检索查询
            
        Returns:
            (memory_id, score) 列表
        """
        query_embedding = await self.long_term.embedding.embed(query.query)
        
        results = await self.long_term.milvus.search_by_vector(
            user_id=query.user_id,
            embedding=query_embedding,
            top_k=query.top_k * 2,  # 多取一些用于后续融合
            memory_types=[t.value for t in query.memory_types] if query.memory_types else None,
        )
        
        return results
    
    async def _search_keyword(
        self,
        query: RetrievalQuery,
    ) -> list[tuple[Memory, float]]:
        """
        关键词检索
        
        Args:
            query: 检索查询
            
        Returns:
            (memory, score) 列表
        """
        results = await self.long_term.pg.search_fulltext(
            user_id=query.user_id,
            query=query.query,
            limit=query.top_k * 2,
        )
        
        return results
    
    async def _search_recency(
        self,
        query: RetrievalQuery,
    ) -> list[Memory]:
        """
        时序检索
        
        Args:
            query: 检索查询
            
        Returns:
            按最近访问排序的记忆列表
        """
        results = await self.long_term.pg.get_recent(
            user_id=query.user_id,
            limit=query.top_k,
        )
        
        return results
    
    async def _merge_results(
        self,
        query: RetrievalQuery,
        vector_results: list[tuple[UUID, float]],
        keyword_results: list[tuple[Memory, float]],
        recency_results: list[Memory],
    ) -> list[SearchResult]:
        """
        合并多路检索结果
        
        Args:
            query: 检索查询
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            recency_results: 时序检索结果
            
        Returns:
            合并后的检索结果
        """
        memory_scores: dict[UUID, SearchResult] = {}
        
        # 处理向量结果
        for memory_id, score in vector_results:
            if memory_id not in memory_scores:
                memory_scores[memory_id] = SearchResult(
                    memory=None,
                    vector_score=score,
                )
            else:
                memory_scores[memory_id].vector_score = score
        
        # 处理关键词结果
        for memory, score in keyword_results:
            if memory.id not in memory_scores:
                memory_scores[memory.id] = SearchResult(
                    memory=memory,
                    keyword_score=score,
                )
            else:
                memory_scores[memory.id].keyword_score = score
                if memory_scores[memory.id].memory is None:
                    memory_scores[memory.id].memory = memory
        
        # 处理时序结果
        total_recency = max(len(recency_results), 1)
        for idx, memory in enumerate(recency_results):
            recency_score = 1.0 - (idx / total_recency)
            
            if memory.id not in memory_scores:
                memory_scores[memory.id] = SearchResult(
                    memory=memory,
                    recency_score=recency_score,
                )
            else:
                memory_scores[memory.id].recency_score = recency_score
                if memory_scores[memory.id].memory is None:
                    memory_scores[memory.id].memory = memory
        
        # 补全缺失的记忆数据
        missing_ids = [
            mid for mid, result in memory_scores.items()
            if result.memory is None
        ]
        
        if missing_ids:
            missing_memories = await asyncio.gather(
                *[self.long_term.pg.get(mid) for mid in missing_ids]
            )
            for mid, mem in zip(missing_ids, missing_memories):
                if mem:
                    memory_scores[mid].memory = mem
                else:
                    # 记忆已删除，移除
                    del memory_scores[mid]
        
        # 计算最终分数
        results = []
        for result in memory_scores.values():
            if result.memory is None:
                continue
            
            v_score = result.vector_score or 0.0
            k_score = result.keyword_score or 0.0
            r_score = result.recency_score or 0.0
            
            result.final_score = (
                query.vector_weight * v_score +
                query.keyword_weight * k_score +
                query.recency_weight * r_score
            )
            results.append(result)
        
        # 按分数排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        return results
    
    def _apply_filters(
        self,
        results: list[SearchResult],
        query: RetrievalQuery,
    ) -> list[SearchResult]:
        """
        应用过滤条件
        
        Args:
            results: 检索结果
            query: 检索查询
            
        Returns:
            过滤后的结果
        """
        filtered = []
        now = datetime.utcnow()
        
        for result in results:
            memory = result.memory
            
            # 重要性过滤
            if query.min_importance is not None:
                if memory.importance < query.min_importance:
                    continue
            
            # 时间过滤
            if query.max_age_days is not None:
                age = now - memory.created_at
                if age.days > query.max_age_days:
                    continue
            
            # 类型过滤
            if query.memory_types:
                if memory.memory_type not in query.memory_types:
                    continue
            
            filtered.append(result)
        
        return filtered
    
    def _get_cache_key(self, query: RetrievalQuery) -> str:
        """
        生成缓存键
        
        Args:
            query: 检索查询
            
        Returns:
            缓存键
        """
        # 构建缓存键内容
        key_data = {
            "user_id": query.user_id,
            "query": query.query,
            "top_k": query.top_k,
            "memory_types": [t.value for t in query.memory_types] if query.memory_types else None,
            "use_vector": query.use_vector,
            "use_keyword": query.use_keyword,
            "use_recency": query.use_recency,
            "vector_weight": query.vector_weight,
            "keyword_weight": query.keyword_weight,
            "recency_weight": query.recency_weight,
            "min_importance": query.min_importance,
            "max_age_days": query.max_age_days,
        }
        
        key_str = json.dumps(key_data, sort_keys=True)
        query_hash = hashlib.md5(key_str.encode()).hexdigest()[:12]
        
        return f"{self.CACHE_PREFIX}:{query.user_id}:{query_hash}"
    
    async def _get_cached(self, query: RetrievalQuery) -> Optional[RetrievalResult]:
        """
        获取缓存的结果
        
        Args:
            query: 检索查询
            
        Returns:
            缓存的结果，不存在返回 None
        """
        try:
            cache_key = self._get_cache_key(query)
            cached_data = await self.redis.get(cache_key)
            
            if not cached_data:
                return None
            
            # 反序列化（简化处理，实际可能需要更复杂的反序列化）
            data = json.loads(cached_data)
            
            # 重建结果
            results = []
            for item in data.get("results", []):
                # 需要重新获取 Memory 对象
                memory = await self.long_term.pg.get(UUID(item["memory_id"]))
                if memory:
                    results.append(SearchResult(
                        memory=memory,
                        vector_score=item.get("vector_score"),
                        keyword_score=item.get("keyword_score"),
                        recency_score=item.get("recency_score"),
                        final_score=item.get("final_score", 0.0),
                    ))
            
            return RetrievalResult(
                query=query,
                results=results,
                vector_count=data.get("vector_count", 0),
                keyword_count=data.get("keyword_count", 0),
                recency_count=data.get("recency_count", 0),
            )
            
        except Exception as e:
            logger.warning(f"Failed to get cached result: {e}")
            return None
    
    async def _cache_result(
        self,
        query: RetrievalQuery,
        result: RetrievalResult,
    ) -> None:
        """
        缓存检索结果
        
        Args:
            query: 检索查询
            result: 检索结果
        """
        try:
            cache_key = self._get_cache_key(query)
            
            # 序列化结果
            data = {
                "results": [
                    {
                        "memory_id": str(r.memory.id),
                        "vector_score": r.vector_score,
                        "keyword_score": r.keyword_score,
                        "recency_score": r.recency_score,
                        "final_score": r.final_score,
                    }
                    for r in result.results
                ],
                "vector_count": result.vector_count,
                "keyword_count": result.keyword_count,
                "recency_count": result.recency_count,
            }
            
            await self.redis.setex(
                cache_key,
                self._cache_ttl,
                json.dumps(data),
            )
            
        except Exception as e:
            logger.warning(f"Failed to cache result: {e}")
    
    async def invalidate_cache(self, user_id: str) -> int:
        """
        使用户的所有检索缓存失效
        
        Args:
            user_id: 用户 ID
            
        Returns:
            删除的缓存数量
        """
        if not self.redis:
            return 0
        
        try:
            pattern = f"{self.CACHE_PREFIX}:{user_id}:*"
            keys = []
            
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                return await self.redis.delete(*keys)
            
            return 0
            
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")
            return 0
