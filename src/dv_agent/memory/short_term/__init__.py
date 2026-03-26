"""
Short-Term Memory Module
短期记忆模块

提供会话级的消息窗口管理、Token 压缩和摘要存储
"""

import json
import logging
from datetime import datetime
from typing import Optional, Protocol

from redis.asyncio import Redis

from ..models import ShortTermMessage, WindowConfig
from .window import SlidingWindow
from .compressor import TokenCompressor, LLMClient

logger = logging.getLogger(__name__)

__all__ = [
    "ShortTermMemory",
    "SlidingWindow",
    "TokenCompressor",
    "ShortTermMessage",
    "WindowConfig",
]


class ShortTermMemory:
    """
    短期记忆管理器
    
    统一接口，整合滑动窗口和 Token 压缩：
    - 消息添加与读取
    - 自动触发压缩
    - 摘要存储与读取
    - 配置管理
    """
    
    # Redis key 前缀
    SUMMARY_PREFIX = "stm:summary"
    SUMMARY_META_PREFIX = "stm:summary_meta"
    
    def __init__(
        self,
        redis: Redis,
        llm_client: LLMClient,
        default_config: Optional[WindowConfig] = None,
    ):
        """
        初始化短期记忆管理器
        
        Args:
            redis: Redis 客户端
            llm_client: LLM 客户端（用于摘要生成）
            default_config: 默认窗口配置
        """
        self.redis = redis
        self.llm_client = llm_client
        self.default_config = default_config or WindowConfig()
        
        # 缓存已创建的窗口
        self._windows: dict[str, SlidingWindow] = {}
        self._compressors: dict[str, TokenCompressor] = {}
    
    def _get_summary_key(self, session_id: str) -> str:
        """获取摘要 Redis key"""
        return f"{self.SUMMARY_PREFIX}:{session_id}"
    
    def _get_summary_meta_key(self, session_id: str) -> str:
        """获取摘要元数据 Redis key"""
        return f"{self.SUMMARY_META_PREFIX}:{session_id}"
    
    def get_window(
        self,
        session_id: str,
        config: Optional[WindowConfig] = None,
    ) -> SlidingWindow:
        """
        获取会话的滑动窗口
        
        Args:
            session_id: 会话 ID
            config: 窗口配置（可选）
            
        Returns:
            SlidingWindow 实例
        """
        if session_id not in self._windows:
            self._windows[session_id] = SlidingWindow(
                redis=self.redis,
                session_id=session_id,
                config=config or self.default_config,
            )
        return self._windows[session_id]
    
    def get_compressor(
        self,
        session_id: str,
        config: Optional[WindowConfig] = None,
    ) -> TokenCompressor:
        """
        获取会话的压缩器
        
        Args:
            session_id: 会话 ID
            config: 配置（可选）
            
        Returns:
            TokenCompressor 实例
        """
        if session_id not in self._compressors:
            self._compressors[session_id] = TokenCompressor(
                llm_client=self.llm_client,
                config=config or self.default_config,
            )
        return self._compressors[session_id]
    
    async def add_message(
        self,
        session_id: str,
        message: ShortTermMessage,
        auto_compress: bool = True,
    ) -> None:
        """
        添加消息到短期记忆
        
        Args:
            session_id: 会话 ID
            message: 消息
            auto_compress: 是否自动触发压缩
        """
        window = self.get_window(session_id)
        await window.add_message(message)
        
        # 检查是否需要压缩
        if auto_compress and await window.needs_compression():
            await self._trigger_compression(session_id)
    
    async def add_messages(
        self,
        session_id: str,
        messages: list[ShortTermMessage],
        auto_compress: bool = True,
    ) -> None:
        """
        批量添加消息
        
        Args:
            session_id: 会话 ID
            messages: 消息列表
            auto_compress: 是否自动触发压缩
        """
        window = self.get_window(session_id)
        await window.add_messages(messages)
        
        if auto_compress and await window.needs_compression():
            await self._trigger_compression(session_id)
    
    async def _trigger_compression(self, session_id: str) -> None:
        """
        触发压缩流程
        
        Args:
            session_id: 会话 ID
        """
        window = self.get_window(session_id)
        compressor = self.get_compressor(session_id)
        
        # 获取溢出的消息
        overflow_messages = await window.get_overflow_messages()
        if not overflow_messages:
            return
        
        # 获取现有摘要
        existing_summary = await self.get_summary(session_id)
        
        # 生成新摘要
        new_summary = await compressor.compress(
            messages=overflow_messages,
            existing_summary=existing_summary,
        )
        
        # 保存摘要
        await self.save_summary(session_id, new_summary)
        
        # 裁剪窗口
        keep_count = await window.get_message_count() - len(overflow_messages)
        if keep_count > 0:
            await window.trim_to(keep_count)
        
        logger.info(
            f"Compressed session {session_id}: "
            f"{len(overflow_messages)} messages -> summary"
        )
    
    async def get_context(
        self,
        session_id: str,
        include_summary: bool = True,
    ) -> dict:
        """
        获取完整上下文
        
        Args:
            session_id: 会话 ID
            include_summary: 是否包含摘要
            
        Returns:
            包含 messages 和可选 summary 的字典
        """
        window = self.get_window(session_id)
        messages = await window.get_messages()
        
        context = {
            "messages": messages,
            "message_count": len(messages),
        }
        
        if include_summary:
            summary = await self.get_summary(session_id)
            if summary:
                context["summary"] = summary
                meta = await self.get_summary_meta(session_id)
                if meta:
                    context["summary_meta"] = meta
        
        return context
    
    async def get_llm_context(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        """
        获取 LLM 格式的上下文
        
        包含摘要（作为系统消息的一部分）和最近的消息
        
        Args:
            session_id: 会话 ID
            system_prompt: 系统提示词（可选）
            
        Returns:
            LLM 消息列表
        """
        context = await self.get_context(session_id, include_summary=True)
        llm_messages = []
        
        # 构建系统消息（含摘要）
        system_parts = []
        if system_prompt:
            system_parts.append(system_prompt)
        
        if context.get("summary"):
            system_parts.append(
                f"\n[Previous Conversation Summary]\n{context['summary']}"
            )
        
        if system_parts:
            llm_messages.append({
                "role": "system",
                "content": "\n".join(system_parts),
            })
        
        # 添加窗口内的消息
        for msg in context["messages"]:
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
    
    # ========== 摘要存储 (Task 3.5) ==========
    
    async def save_summary(
        self,
        session_id: str,
        summary: str,
        token_count: Optional[int] = None,
    ) -> None:
        """
        保存会话摘要
        
        Args:
            session_id: 会话 ID
            summary: 摘要文本
            token_count: Token 数（可选）
        """
        summary_key = self._get_summary_key(session_id)
        meta_key = self._get_summary_meta_key(session_id)
        
        # 保存摘要文本
        await self.redis.set(summary_key, summary, ex=86400 * 7)  # 7 天过期
        
        # 保存元数据
        meta = {
            "updated_at": datetime.utcnow().isoformat(),
            "char_count": len(summary),
            "token_count": token_count,
        }
        await self.redis.set(meta_key, json.dumps(meta), ex=86400 * 7)
        
        logger.debug(f"Saved summary for session {session_id}")
    
    async def get_summary(self, session_id: str) -> Optional[str]:
        """
        获取会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            摘要文本，不存在返回 None
        """
        summary_key = self._get_summary_key(session_id)
        summary = await self.redis.get(summary_key)
        
        if summary:
            return summary.decode() if isinstance(summary, bytes) else summary
        return None
    
    async def get_summary_meta(self, session_id: str) -> Optional[dict]:
        """
        获取摘要元数据
        
        Args:
            session_id: 会话 ID
            
        Returns:
            元数据字典
        """
        meta_key = self._get_summary_meta_key(session_id)
        meta = await self.redis.get(meta_key)
        
        if meta:
            raw = meta.decode() if isinstance(meta, bytes) else meta
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None
    
    async def delete_summary(self, session_id: str) -> None:
        """删除会话摘要"""
        summary_key = self._get_summary_key(session_id)
        meta_key = self._get_summary_meta_key(session_id)
        await self.redis.delete(summary_key, meta_key)
    
    # ========== 配置管理 (Task 3.6) ==========
    
    async def save_config(
        self,
        session_id: str,
        config: WindowConfig,
    ) -> None:
        """
        保存窗口配置
        
        Args:
            session_id: 会话 ID
            config: 窗口配置
        """
        window = self.get_window(session_id, config)
        window.config = config
        await window.save_config()
        
        # 更新压缩器配置
        if session_id in self._compressors:
            self._compressors[session_id].config = config
    
    async def load_config(self, session_id: str) -> Optional[WindowConfig]:
        """
        加载窗口配置
        
        Args:
            session_id: 会话 ID
            
        Returns:
            窗口配置，不存在返回 None
        """
        window = self.get_window(session_id)
        return await window.load_config()
    
    async def update_config(
        self,
        session_id: str,
        **updates,
    ) -> WindowConfig:
        """
        更新窗口配置
        
        Args:
            session_id: 会话 ID
            **updates: 要更新的字段
            
        Returns:
            更新后的配置
        """
        # 加载现有配置或使用默认
        config = await self.load_config(session_id) or self.default_config
        
        # 应用更新
        config_dict = config.model_dump()
        config_dict.update(updates)
        new_config = WindowConfig(**config_dict)
        
        # 保存
        await self.save_config(session_id, new_config)
        return new_config
    
    # ========== 清理 ==========
    
    async def clear_session(self, session_id: str) -> None:
        """
        清理会话的短期记忆
        
        Args:
            session_id: 会话 ID
        """
        window = self.get_window(session_id)
        await window.clear()
        await self.delete_summary(session_id)
        
        # 清理缓存
        self._windows.pop(session_id, None)
        self._compressors.pop(session_id, None)
        
        logger.info(f"Cleared short-term memory for session {session_id}")
    
    async def close(self) -> None:
        """关闭管理器，清理资源"""
        self._windows.clear()
        self._compressors.clear()