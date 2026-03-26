"""
Embedding Service
向量嵌入服务

提供文本到向量的转换，支持本地模型和 API 模式
"""

import hashlib
import logging
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    向量嵌入服务
    
    负责：
    - 文本向量化
    - 向量缓存
    - 批量处理
    """
    
    # Redis 缓存前缀
    CACHE_PREFIX = "emb:cache"
    
    # 默认模型
    DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
    
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        redis: Optional[Redis] = None,
        cache_ttl: int = 86400 * 7,  # 7 天
        dimension: int = 512,
    ):
        """
        初始化服务
        
        Args:
            model_name: Embedding 模型名称
            redis: Redis 客户端（用于缓存）
            cache_ttl: 缓存过期时间（秒）
            dimension: 向量维度
        """
        self.model_name = model_name
        self.redis = redis
        self.cache_ttl = cache_ttl
        self.dimension = dimension
        
        self._model = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        初始化模型
        
        延迟加载，避免启动时阻塞
        """
        if self._initialized:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            
            # 更新实际维度
            self.dimension = self._model.get_sentence_embedding_dimension()
            
            self._initialized = True
            logger.info(
                f"Embedding model loaded: {self.model_name} "
                f"(dimension={self.dimension})"
            )
            
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    @property
    def model(self):
        """获取模型（确保已初始化）"""
        if not self._initialized:
            raise RuntimeError(
                "EmbeddingService not initialized. Call initialize() first."
            )
        return self._model
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用 MD5 哈希作为键
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{self.CACHE_PREFIX}:{self.model_name}:{text_hash}"
    
    async def embed(
        self,
        text: str,
        use_cache: bool = True,
        normalize: bool = True,
    ) -> list[float]:
        """
        生成文本向量
        
        Args:
            text: 输入文本
            use_cache: 是否使用缓存
            normalize: 是否归一化向量
            
        Returns:
            向量（浮点数列表）
        """
        if not text.strip():
            return [0.0] * self.dimension
        
        # 尝试从缓存获取
        if use_cache and self.redis:
            cached = await self._get_cached(text)
            if cached is not None:
                return cached
        
        # 确保模型已初始化
        await self.initialize()
        
        # 生成向量
        embedding = self.model.encode(
            text,
            normalize_embeddings=normalize,
        ).tolist()
        
        # 写入缓存
        if use_cache and self.redis:
            await self._set_cached(text, embedding)
        
        return embedding
    
    async def embed_batch(
        self,
        texts: list[str],
        use_cache: bool = True,
        normalize: bool = True,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """
        批量生成文本向量
        
        Args:
            texts: 输入文本列表
            use_cache: 是否使用缓存
            normalize: 是否归一化
            batch_size: 批处理大小
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        results = [None] * len(texts)
        texts_to_embed = []
        indices_to_embed = []
        
        # 检查缓存
        if use_cache and self.redis:
            for i, text in enumerate(texts):
                if not text.strip():
                    results[i] = [0.0] * self.dimension
                    continue
                    
                cached = await self._get_cached(text)
                if cached is not None:
                    results[i] = cached
                else:
                    texts_to_embed.append(text)
                    indices_to_embed.append(i)
        else:
            for i, text in enumerate(texts):
                if not text.strip():
                    results[i] = [0.0] * self.dimension
                else:
                    texts_to_embed.append(text)
                    indices_to_embed.append(i)
        
        # 批量生成缺失的向量
        if texts_to_embed:
            await self.initialize()
            
            embeddings = self.model.encode(
                texts_to_embed,
                normalize_embeddings=normalize,
                batch_size=batch_size,
                show_progress_bar=False,
            )
            
            for i, embedding in zip(indices_to_embed, embeddings):
                results[i] = embedding.tolist()
                
                # 写入缓存
                if use_cache and self.redis:
                    await self._set_cached(texts[i], results[i])
        
        return results
    
    async def _get_cached(self, text: str) -> Optional[list[float]]:
        """从缓存获取向量"""
        import json
        
        cache_key = self._get_cache_key(text)
        cached = await self.redis.get(cache_key)
        
        if cached:
            try:
                raw = cached.decode() if isinstance(cached, bytes) else cached
                return json.loads(raw)
            except (json.JSONDecodeError, AttributeError):
                pass
        
        return None
    
    async def _set_cached(self, text: str, embedding: list[float]) -> None:
        """将向量写入缓存"""
        import json
        
        cache_key = self._get_cache_key(text)
        await self.redis.set(
            cache_key,
            json.dumps(embedding),
            ex=self.cache_ttl,
        )
    
    async def clear_cache(self, pattern: Optional[str] = None) -> int:
        """
        清除缓存
        
        Args:
            pattern: 匹配模式（可选）
            
        Returns:
            删除的键数量
        """
        if not self.redis:
            return 0
        
        if pattern:
            search_pattern = f"{self.CACHE_PREFIX}:{pattern}*"
        else:
            search_pattern = f"{self.CACHE_PREFIX}:*"
        
        count = 0
        async for key in self.redis.scan_iter(search_pattern):
            await self.redis.delete(key)
            count += 1
        
        logger.info(f"Cleared {count} embedding cache entries")
        return count
    
    async def get_cache_stats(self) -> dict:
        """获取缓存统计"""
        if not self.redis:
            return {"enabled": False}
        
        pattern = f"{self.CACHE_PREFIX}:*"
        count = 0
        async for _ in self.redis.scan_iter(pattern):
            count += 1
        
        return {
            "enabled": True,
            "model": self.model_name,
            "cached_embeddings": count,
            "ttl_seconds": self.cache_ttl,
        }
    
    async def close(self) -> None:
        """关闭服务"""
        # SentenceTransformer 不需要显式关闭
        self._model = None
        self._initialized = False


class OpenAIEmbeddingService(EmbeddingService):
    """
    OpenAI API 向量嵌入服务
    
    使用 OpenAI API 生成向量，适用于无法运行本地模型的场景
    """
    
    DEFAULT_MODEL = "text-embedding-3-small"
    
    def __init__(
        self,
        api_key: str,
        model_name: str = DEFAULT_MODEL,
        redis: Optional[Redis] = None,
        cache_ttl: int = 86400 * 7,
        dimension: int = 1536,
        base_url: Optional[str] = None,
    ):
        """
        初始化服务
        
        Args:
            api_key: OpenAI API Key
            model_name: 模型名称
            redis: Redis 客户端
            cache_ttl: 缓存 TTL
            dimension: 向量维度
            base_url: API Base URL（可选，用于兼容 API）
        """
        super().__init__(
            model_name=model_name,
            redis=redis,
            cache_ttl=cache_ttl,
            dimension=dimension,
        )
        
        self.api_key = api_key
        self.base_url = base_url
        self._client = None
    
    async def initialize(self) -> None:
        """初始化 OpenAI 客户端"""
        if self._initialized:
            return
        
        try:
            from openai import AsyncOpenAI
            
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            
            self._initialized = True
            logger.info(f"OpenAI Embedding client initialized: {self.model_name}")
            
        except ImportError:
            logger.error("openai not installed. Run: pip install openai")
            raise
    
    async def embed(
        self,
        text: str,
        use_cache: bool = True,
        normalize: bool = True,
    ) -> list[float]:
        """生成文本向量"""
        if not text.strip():
            return [0.0] * self.dimension
        
        # 尝试从缓存获取
        if use_cache and self.redis:
            cached = await self._get_cached(text)
            if cached is not None:
                return cached
        
        await self.initialize()
        
        response = await self._client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        
        embedding = response.data[0].embedding
        
        # 写入缓存
        if use_cache and self.redis:
            await self._set_cached(text, embedding)
        
        return embedding
    
    async def embed_batch(
        self,
        texts: list[str],
        use_cache: bool = True,
        normalize: bool = True,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """批量生成文本向量"""
        if not texts:
            return []
        
        results = [None] * len(texts)
        texts_to_embed = []
        indices_to_embed = []
        
        # 检查缓存
        if use_cache and self.redis:
            for i, text in enumerate(texts):
                if not text.strip():
                    results[i] = [0.0] * self.dimension
                    continue
                
                cached = await self._get_cached(text)
                if cached is not None:
                    results[i] = cached
                else:
                    texts_to_embed.append(text)
                    indices_to_embed.append(i)
        else:
            for i, text in enumerate(texts):
                if not text.strip():
                    results[i] = [0.0] * self.dimension
                else:
                    texts_to_embed.append(text)
                    indices_to_embed.append(i)
        
        # 批量生成
        if texts_to_embed:
            await self.initialize()
            
            # OpenAI API 支持批量
            response = await self._client.embeddings.create(
                model=self.model_name,
                input=texts_to_embed,
            )
            
            for data, i in zip(response.data, indices_to_embed):
                results[i] = data.embedding
                
                if use_cache and self.redis:
                    await self._set_cached(texts[i], results[i])
        
        return results
    
    async def close(self) -> None:
        """关闭服务"""
        if self._client:
            await self._client.close()
        self._client = None
        self._initialized = False
