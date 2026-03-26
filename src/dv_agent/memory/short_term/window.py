"""
Sliding Window Manager
短期记忆滑动窗口管理

实现消息窗口的管理，支持 Redis 存储和 token 限制
"""

import json
import logging
from datetime import datetime
from typing import Optional

from redis.asyncio import Redis

from ..models import ShortTermMessage, WindowConfig

logger = logging.getLogger(__name__)


class SlidingWindow:
    """
    滑动窗口管理器
    
    维护会话的最近 N 条消息，支持：
    - 消息添加与裁剪
    - Token 限制检测
    - Redis 持久化
    """
    
    # Redis key 前缀
    KEY_PREFIX = "stm:window"
    CONFIG_PREFIX = "stm:config"
    
    def __init__(
        self,
        redis: Redis,
        session_id: str,
        config: Optional[WindowConfig] = None,
    ):
        """
        初始化滑动窗口
        
        Args:
            redis: Redis 客户端
            session_id: 会话 ID
            config: 窗口配置，None 时使用默认配置
        """
        self.redis = redis
        self.session_id = session_id
        self.config = config or WindowConfig()
        
        # Redis keys
        self._window_key = f"{self.KEY_PREFIX}:{session_id}"
        self._config_key = f"{self.CONFIG_PREFIX}:{session_id}"
    
    async def add_message(self, message: ShortTermMessage) -> None:
        """
        添加消息到窗口
        
        使用 LPUSH + LTRIM 维护固定大小的窗口
        
        Args:
            message: 短期记忆消息
        """
        # 序列化消息
        msg_data = message.model_dump_json()
        
        # 使用 pipeline 原子操作
        async with self.redis.pipeline(transaction=True) as pipe:
            # LPUSH 添加到头部
            pipe.lpush(self._window_key, msg_data)
            # LTRIM 保留最近 N 条
            pipe.ltrim(self._window_key, 0, self.config.window_size - 1)
            # 设置 TTL（24小时）
            pipe.expire(self._window_key, 86400)
            await pipe.execute()
        
        logger.debug(
            f"Added message to window {self.session_id}, role={message.role}"
        )
    
    async def add_messages(self, messages: list[ShortTermMessage]) -> None:
        """
        批量添加消息
        
        Args:
            messages: 消息列表
        """
        if not messages:
            return
        
        # 序列化所有消息
        msg_data_list = [m.model_dump_json() for m in messages]
        
        async with self.redis.pipeline(transaction=True) as pipe:
            # 逆序添加以保持顺序
            for msg_data in reversed(msg_data_list):
                pipe.lpush(self._window_key, msg_data)
            # 裁剪
            pipe.ltrim(self._window_key, 0, self.config.window_size - 1)
            pipe.expire(self._window_key, 86400)
            await pipe.execute()
    
    async def get_messages(
        self,
        limit: Optional[int] = None,
    ) -> list[ShortTermMessage]:
        """
        获取窗口中的消息
        
        Args:
            limit: 获取数量限制，None 时获取全部
            
        Returns:
            消息列表（按时间顺序，旧的在前）
        """
        end = (limit - 1) if limit else -1
        
        # LRANGE 获取消息（LPUSH 存储，所以是逆序的）
        raw_messages = await self.redis.lrange(self._window_key, 0, end)
        
        if not raw_messages:
            return []
        
        # 反序列化并反转顺序（使旧消息在前）
        messages = []
        for raw in reversed(raw_messages):
            try:
                msg_dict = json.loads(raw)
                messages.append(ShortTermMessage(**msg_dict))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse message: {e}")
                continue
        
        return messages
    
    async def get_recent_messages(self, n: int) -> list[ShortTermMessage]:
        """
        获取最近 N 条消息
        
        Args:
            n: 消息数量
            
        Returns:
            消息列表（按时间顺序）
        """
        raw_messages = await self.redis.lrange(self._window_key, 0, n - 1)
        
        if not raw_messages:
            return []
        
        messages = []
        for raw in reversed(raw_messages):
            try:
                msg_dict = json.loads(raw)
                messages.append(ShortTermMessage(**msg_dict))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse message: {e}")
                continue
        
        return messages
    
    async def get_message_count(self) -> int:
        """获取当前消息数量"""
        return await self.redis.llen(self._window_key)
    
    async def get_total_tokens(self) -> int:
        """
        计算窗口中所有消息的总 token 数
        
        Returns:
            总 token 数
        """
        messages = await self.get_messages()
        return sum(m.token_count for m in messages)
    
    async def needs_compression(self) -> bool:
        """
        检查是否需要压缩
        
        当消息数超过阈值或 token 数超限时需要压缩
        
        Returns:
            是否需要压缩
        """
        count = await self.get_message_count()
        if count >= self.config.compress_threshold:
            return True
        
        total_tokens = await self.get_total_tokens()
        if total_tokens >= self.config.token_limit:
            return True
        
        return False
    
    async def get_overflow_messages(self) -> list[ShortTermMessage]:
        """
        获取溢出的消息（待压缩的部分）
        
        保留最近的一半消息，返回较旧的一半用于压缩
        
        Returns:
            溢出的消息列表
        """
        messages = await self.get_messages()
        if len(messages) <= self.config.window_size // 2:
            return []
        
        # 保留后一半，返回前一半
        split_point = len(messages) // 2
        return messages[:split_point]
    
    async def trim_to(self, keep_count: int) -> None:
        """
        裁剪窗口到指定数量
        
        Args:
            keep_count: 保留的消息数量
        """
        await self.redis.ltrim(self._window_key, 0, keep_count - 1)
        logger.debug(f"Trimmed window {self.session_id} to {keep_count} messages")
    
    async def clear(self) -> None:
        """清空窗口"""
        await self.redis.delete(self._window_key)
        logger.info(f"Cleared window {self.session_id}")
    
    async def save_config(self) -> None:
        """保存窗口配置到 Redis"""
        config_data = self.config.model_dump_json()
        await self.redis.set(self._config_key, config_data, ex=86400 * 7)
    
    async def load_config(self) -> Optional[WindowConfig]:
        """从 Redis 加载窗口配置"""
        config_data = await self.redis.get(self._config_key)
        if config_data:
            try:
                return WindowConfig(**json.loads(config_data))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to load config: {e}")
        return None
    
    async def to_llm_messages(self) -> list[dict]:
        """
        转换为 LLM 消息格式
        
        Returns:
            LLM 兼容的消息字典列表
        """
        messages = await self.get_messages()
        llm_messages = []
        
        for msg in messages:
            llm_msg = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                llm_msg["name"] = msg.name
            if msg.tool_call_id:
                llm_msg["tool_call_id"] = msg.tool_call_id
            llm_messages.append(llm_msg)
        
        return llm_messages
