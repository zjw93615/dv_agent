"""
Retrieval Cache

检索结果缓存，减少重复查询的计算开销。

特性：
1. 基于Redis的分布式缓存
2. 支持查询指纹（忽略无关参数变化）
3. 可配置TTL和缓存策略
4. 缓存预热和失效机制
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置"""
    enabled: bool = True                    # 是否启用缓存
    ttl_seconds: int = 3600                 # 默认TTL（1小时）
    max_cached_results: int = 100           # 单个查询最大缓存结果数
    key_prefix: str = "rag:retrieval:"      # 缓存键前缀
    
    # 缓存策略
    cache_expanded_queries: bool = True     # 缓存扩展后的查询
    cache_raw_results: bool = False         # 缓存原始召回结果（较大）
    cache_final_results: bool = True        # 缓存最终结果
    
    # 查询指纹参数
    include_collection_in_key: bool = True  # 键中包含collection_id
    include_filters_in_key: bool = True     # 键中包含filters


class RetrievalCache:
    """
    检索结果缓存
    
    使用Redis存储热点查询的检索结果，支持多级缓存。
    """
    
    def __init__(
        self,
        redis_client=None,
        config: Optional[CacheConfig] = None
    ):
        """
        初始化
        
        Args:
            redis_client: Redis异步客户端
            config: 缓存配置
        """
        self.redis = redis_client
        self.config = config or CacheConfig()
        
        # 本地LRU缓存（热点数据）
        self._local_cache: Dict[str, Dict[str, Any]] = {}
        self._local_cache_max_size = 100
        self._local_cache_hits = 0
        self._local_cache_misses = 0
        
        # 统计
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "evictions": 0
        }
    
    def _generate_cache_key(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        cache_type: str = "final"
    ) -> str:
        """
        生成缓存键
        
        使用查询内容和参数的哈希作为键。
        """
        key_parts = [
            query.lower().strip(),
            tenant_id,
            str(top_k),
            cache_type
        ]
        
        if self.config.include_collection_in_key and collection_id:
            key_parts.append(collection_id)
        
        if self.config.include_filters_in_key and filters:
            # 排序确保一致性
            filters_str = json.dumps(filters, sort_keys=True)
            key_parts.append(filters_str)
        
        # 生成哈希
        key_content = "|".join(key_parts)
        key_hash = hashlib.md5(key_content.encode()).hexdigest()[:16]
        
        return f"{self.config.key_prefix}{tenant_id}:{cache_type}:{key_hash}"
    
    async def get(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        cache_type: str = "final"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的检索结果
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 返回数量
            filters: 过滤条件
            cache_type: 缓存类型（final/raw/queries）
            
        Returns:
            缓存的结果列表，未命中返回None
        """
        if not self.config.enabled:
            return None
        
        cache_key = self._generate_cache_key(
            query, tenant_id, collection_id, top_k, filters, cache_type
        )
        
        # 首先检查本地缓存
        if cache_key in self._local_cache:
            entry = self._local_cache[cache_key]
            if time.time() < entry["expires_at"]:
                self._local_cache_hits += 1
                self._stats["hits"] += 1
                logger.debug(f"Local cache hit: {cache_key}")
                return entry["data"]
            else:
                # 过期，移除
                del self._local_cache[cache_key]
        
        self._local_cache_misses += 1
        
        # 检查Redis
        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    results = json.loads(cached_data)
                    self._stats["hits"] += 1
                    
                    # 更新本地缓存
                    self._update_local_cache(cache_key, results)
                    
                    logger.debug(f"Redis cache hit: {cache_key}")
                    return results
            except Exception as e:
                logger.warning(f"Redis cache get failed: {e}")
        
        self._stats["misses"] += 1
        return None
    
    async def set(
        self,
        query: str,
        tenant_id: str,
        results: List[Dict[str, Any]],
        collection_id: Optional[str] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        cache_type: str = "final",
        ttl: Optional[int] = None
    ) -> bool:
        """
        缓存检索结果
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            results: 检索结果
            collection_id: 文档集合ID
            top_k: 返回数量
            filters: 过滤条件
            cache_type: 缓存类型
            ttl: 过期时间（秒）
            
        Returns:
            是否成功
        """
        if not self.config.enabled:
            return False
        
        # 检查缓存类型是否启用
        if cache_type == "final" and not self.config.cache_final_results:
            return False
        if cache_type == "raw" and not self.config.cache_raw_results:
            return False
        if cache_type == "queries" and not self.config.cache_expanded_queries:
            return False
        
        cache_key = self._generate_cache_key(
            query, tenant_id, collection_id, top_k, filters, cache_type
        )
        
        # 限制缓存结果数量
        cached_results = results[:self.config.max_cached_results]
        
        ttl = ttl or self.config.ttl_seconds
        
        # 更新本地缓存
        self._update_local_cache(cache_key, cached_results, ttl)
        
        # 更新Redis
        if self.redis:
            try:
                await self.redis.setex(
                    cache_key,
                    ttl,
                    json.dumps(cached_results)
                )
                self._stats["sets"] += 1
                logger.debug(f"Cache set: {cache_key}, ttl={ttl}s")
                return True
            except Exception as e:
                logger.warning(f"Redis cache set failed: {e}")
                return False
        
        return True
    
    def _update_local_cache(
        self,
        key: str,
        data: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ):
        """更新本地缓存"""
        ttl = ttl or self.config.ttl_seconds
        
        # 检查容量，LRU驱逐
        if len(self._local_cache) >= self._local_cache_max_size:
            # 移除最旧的条目
            oldest_key = min(
                self._local_cache.keys(),
                key=lambda k: self._local_cache[k].get("accessed_at", 0)
            )
            del self._local_cache[oldest_key]
            self._stats["evictions"] += 1
        
        self._local_cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl,
            "accessed_at": time.time()
        }
    
    async def invalidate(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        pattern: Optional[str] = None
    ) -> int:
        """
        使缓存失效
        
        Args:
            tenant_id: 租户ID
            collection_id: 文档集合ID（可选，指定则只失效该集合）
            pattern: 自定义匹配模式
            
        Returns:
            失效的键数量
        """
        invalidated = 0
        
        # 构建匹配模式
        if pattern:
            match_pattern = pattern
        elif collection_id:
            match_pattern = f"{self.config.key_prefix}{tenant_id}:*:{collection_id}*"
        else:
            match_pattern = f"{self.config.key_prefix}{tenant_id}:*"
        
        # 清理本地缓存
        keys_to_remove = [
            k for k in self._local_cache.keys()
            if k.startswith(f"{self.config.key_prefix}{tenant_id}")
        ]
        for key in keys_to_remove:
            del self._local_cache[key]
            invalidated += 1
        
        # 清理Redis
        if self.redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(
                        cursor=cursor,
                        match=match_pattern,
                        count=100
                    )
                    if keys:
                        await self.redis.delete(*keys)
                        invalidated += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Redis cache invalidation failed: {e}")
        
        logger.info(f"Invalidated {invalidated} cache entries for tenant {tenant_id}")
        return invalidated
    
    async def invalidate_document(
        self,
        tenant_id: str,
        doc_id: str
    ) -> int:
        """
        文档更新/删除时失效相关缓存
        
        简单策略：失效该租户的所有缓存
        （更精细的策略需要维护文档到查询的反向索引）
        """
        return await self.invalidate(tenant_id)
    
    async def warm_up(
        self,
        queries: List[Dict[str, Any]],
        retriever
    ) -> int:
        """
        缓存预热
        
        Args:
            queries: 预热查询列表，每个包含 query, tenant_id, collection_id 等
            retriever: 检索器实例
            
        Returns:
            预热的查询数量
        """
        warmed = 0
        
        for q in queries:
            try:
                # 检查是否已缓存
                cached = await self.get(
                    query=q.get("query", ""),
                    tenant_id=q.get("tenant_id", ""),
                    collection_id=q.get("collection_id"),
                    top_k=q.get("top_k", 10)
                )
                
                if cached is None:
                    # 执行检索并缓存
                    results = await retriever.simple_search(
                        query=q.get("query", ""),
                        tenant_id=q.get("tenant_id", ""),
                        collection_id=q.get("collection_id"),
                        top_k=q.get("top_k", 10)
                    )
                    
                    # 转换为可序列化格式
                    serializable_results = [
                        {
                            "chunk_id": r.chunk_id,
                            "doc_id": r.doc_id,
                            "content": r.content,
                            "score": r.score,
                            "metadata": r.metadata
                        }
                        for r in results
                    ]
                    
                    await self.set(
                        query=q.get("query", ""),
                        tenant_id=q.get("tenant_id", ""),
                        results=serializable_results,
                        collection_id=q.get("collection_id"),
                        top_k=q.get("top_k", 10)
                    )
                    warmed += 1
                    
            except Exception as e:
                logger.warning(f"Cache warm-up failed for query: {e}")
        
        logger.info(f"Cache warm-up completed: {warmed} queries")
        return warmed
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0
        
        return {
            **self._stats,
            "hit_rate": hit_rate,
            "local_cache_size": len(self._local_cache),
            "local_hits": self._local_cache_hits,
            "local_misses": self._local_cache_misses
        }
    
    def clear_local_cache(self):
        """清空本地缓存"""
        self._local_cache.clear()
        logger.info("Local cache cleared")
    
    async def clear_all(self, tenant_id: Optional[str] = None):
        """
        清空所有缓存
        
        Args:
            tenant_id: 可选，只清空指定租户
        """
        self.clear_local_cache()
        
        if self.redis:
            if tenant_id:
                await self.invalidate(tenant_id)
            else:
                # 清空所有RAG缓存
                try:
                    cursor = 0
                    while True:
                        cursor, keys = await self.redis.scan(
                            cursor=cursor,
                            match=f"{self.config.key_prefix}*",
                            count=100
                        )
                        if keys:
                            await self.redis.delete(*keys)
                        if cursor == 0:
                            break
                except Exception as e:
                    logger.warning(f"Redis cache clear failed: {e}")


class CachedRetriever:
    """
    带缓存的检索器包装器
    
    自动处理缓存的读取和写入。
    """
    
    def __init__(
        self,
        retriever,  # HybridRetriever
        cache: RetrievalCache
    ):
        """
        初始化
        
        Args:
            retriever: 底层检索器
            cache: 缓存实例
        """
        self.retriever = retriever
        self.cache = cache
    
    async def search(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        bypass_cache: bool = False
    ) -> List[Dict[str, Any]]:
        """
        带缓存的检索
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 文档集合ID
            top_k: 返回数量
            filters: 过滤条件
            bypass_cache: 是否跳过缓存
            
        Returns:
            检索结果列表
        """
        # 尝试从缓存获取
        if not bypass_cache:
            cached = await self.cache.get(
                query=query,
                tenant_id=tenant_id,
                collection_id=collection_id,
                top_k=top_k,
                filters=filters
            )
            if cached is not None:
                return cached
        
        # 执行检索
        results = await self.retriever.simple_search(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=top_k
        )
        
        # 转换为可序列化格式
        serializable_results = [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata
            }
            for r in results
        ]
        
        # 写入缓存
        await self.cache.set(
            query=query,
            tenant_id=tenant_id,
            results=serializable_results,
            collection_id=collection_id,
            top_k=top_k,
            filters=filters
        )
        
        return serializable_results
