"""
Redis连接管理模块
提供Redis连接池和通用操作封装
"""

import json
from typing import Any, Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    """Redis配置"""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 10
    redis_decode_responses: bool = True
    
    # Key前缀
    redis_key_prefix: str = "dv-agent:"
    
    # TTL配置（秒）
    session_ttl: int = 86400  # 24小时
    cache_ttl: int = 3600     # 1小时
    task_ttl: int = 3600      # 1小时
    
    class Config:
        env_file = ".env"
        extra = "ignore"


class RedisClient:
    """Redis客户端封装"""
    
    def __init__(self, settings: Optional[RedisSettings] = None):
        self.settings = settings or RedisSettings()
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """建立Redis连接"""
        if self._pool is not None:
            return
            
        self._pool = redis.ConnectionPool(
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            db=self.settings.redis_db,
            password=self.settings.redis_password,
            max_connections=self.settings.redis_max_connections,
            decode_responses=self.settings.redis_decode_responses,
        )
        self._client = redis.Redis(connection_pool=self._pool)
    
    async def disconnect(self) -> None:
        """关闭Redis连接"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
    
    @property
    def client(self) -> redis.Redis:
        """获取Redis客户端实例"""
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client
    
    def _make_key(self, key: str) -> str:
        """添加key前缀"""
        return f"{self.settings.redis_key_prefix}{key}"
    
    # ==================== 基础操作 ====================
    
    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        return await self.client.get(self._make_key(key))
    
    async def set(
        self, 
        key: str, 
        value: str, 
        ttl: Optional[int] = None
    ) -> bool:
        """设置值"""
        full_key = self._make_key(key)
        if ttl:
            return await self.client.setex(full_key, ttl, value)
        return await self.client.set(full_key, value)
    
    async def delete(self, key: str) -> int:
        """删除key"""
        return await self.client.delete(self._make_key(key))
    
    async def exists(self, key: str) -> bool:
        """检查key是否存在"""
        return await self.client.exists(self._make_key(key)) > 0
    
    async def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        return await self.client.expire(self._make_key(key), ttl)
    
    # ==================== JSON操作 ====================
    
    async def get_json(self, key: str) -> Optional[Any]:
        """获取JSON值"""
        value = await self.get(key)
        if value is None:
            return None
        return json.loads(value)
    
    async def set_json(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """设置JSON值"""
        return await self.set(key, json.dumps(value, ensure_ascii=False), ttl)
    
    # ==================== Hash操作 ====================
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """获取Hash字段"""
        return await self.client.hget(self._make_key(name), key)
    
    async def hset(self, name: str, key: str, value: str) -> int:
        """设置Hash字段"""
        return await self.client.hset(self._make_key(name), key, value)
    
    async def hmset(self, name: str, mapping: dict) -> bool:
        """批量设置Hash字段"""
        return await self.client.hset(self._make_key(name), mapping=mapping)
    
    async def hgetall(self, name: str) -> dict:
        """获取Hash所有字段"""
        return await self.client.hgetall(self._make_key(name))
    
    async def hdel(self, name: str, *keys: str) -> int:
        """删除Hash字段"""
        return await self.client.hdel(self._make_key(name), *keys)
    
    # ==================== List操作 ====================
    
    async def lpush(self, name: str, *values: str) -> int:
        """从左侧推入List"""
        return await self.client.lpush(self._make_key(name), *values)
    
    async def rpush(self, name: str, *values: str) -> int:
        """从右侧推入List"""
        return await self.client.rpush(self._make_key(name), *values)
    
    async def lrange(self, name: str, start: int, end: int) -> list:
        """获取List范围"""
        return await self.client.lrange(self._make_key(name), start, end)
    
    async def llen(self, name: str) -> int:
        """获取List长度"""
        return await self.client.llen(self._make_key(name))
    
    async def ltrim(self, name: str, start: int, end: int) -> bool:
        """裁剪List"""
        return await self.client.ltrim(self._make_key(name), start, end)
    
    # ==================== Set操作 ====================
    
    async def sadd(self, name: str, *values: str) -> int:
        """添加Set成员"""
        return await self.client.sadd(self._make_key(name), *values)
    
    async def srem(self, name: str, *values: str) -> int:
        """移除Set成员"""
        return await self.client.srem(self._make_key(name), *values)
    
    async def smembers(self, name: str) -> set:
        """获取Set所有成员"""
        return await self.client.smembers(self._make_key(name))
    
    async def sismember(self, name: str, value: str) -> bool:
        """检查是否为Set成员"""
        return await self.client.sismember(self._make_key(name), value)
    
    async def scard(self, name: str) -> int:
        """获取Set成员数量"""
        return await self.client.scard(self._make_key(name))
    
    # ==================== 健康检查 ====================
    
    async def ping(self) -> bool:
        """健康检查"""
        try:
            return await self.client.ping()
        except Exception:
            return False


# 全局Redis客户端实例
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """获取全局Redis客户端"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def init_redis() -> RedisClient:
    """初始化Redis连接"""
    client = get_redis_client()
    await client.connect()
    return client


async def close_redis() -> None:
    """关闭Redis连接"""
    global _redis_client
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None


@asynccontextmanager
async def redis_context():
    """Redis上下文管理器"""
    client = await init_redis()
    try:
        yield client
    finally:
        await close_redis()
