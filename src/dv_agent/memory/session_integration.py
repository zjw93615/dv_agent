"""
Memory-Enhanced Session Manager
记忆增强的会话管理器

扩展 SessionManager，集成记忆系统功能。
"""

import logging
from typing import Any, Optional

from ..session.manager import SessionManager
from ..session.models import Session, ConversationHistory
from ..session.redis_client import RedisClient
from ..memory import MemoryManager, MemoryConfig, MemoryContext

logger = logging.getLogger(__name__)


class MemoryEnabledSessionManager(SessionManager):
    """
    记忆增强的会话管理器
    
    扩展功能：
    - 创建会话时可指定记忆配置
    - 获取历史时可附带摘要
    - 会话关闭时自动触发记忆提取
    - 会话恢复时加载相关长期记忆
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        memory_manager: Optional[MemoryManager] = None,
        default_ttl: int = 3600 * 24,
    ):
        """
        初始化
        
        Args:
            redis_client: Redis 客户端
            memory_manager: 记忆管理器
            default_ttl: 默认 TTL
        """
        super().__init__(redis_client, default_ttl)
        self.memory_manager = memory_manager
    
    async def create_session_with_memory(
        self,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        ttl: Optional[int] = None,
        metadata: Optional[dict] = None,
        memory_config: Optional[MemoryConfig] = None,
    ) -> Session:
        """
        创建带记忆配置的会话
        
        Args:
            user_id: 用户 ID
            title: 会话标题
            ttl: 过期时间
            metadata: 元数据
            memory_config: 记忆配置
            
        Returns:
            会话对象
        """
        # 合并记忆配置到 metadata
        meta = metadata or {}
        if memory_config:
            meta["memory_config"] = {
                "window_size": memory_config.window_size,
                "max_tokens": memory_config.max_tokens,
                "compression_threshold": memory_config.compression_threshold,
            }
        
        session = await self.create_session(
            user_id=user_id,
            title=title,
            ttl=ttl,
            metadata=meta,
        )
        
        logger.info(
            f"Created session with memory config",
            session_id=session.session_id,
            user_id=user_id,
        )
        
        return session
    
    async def get_history_with_summary(
        self,
        session_id: str,
        last_n: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        获取对话历史和摘要
        
        Args:
            session_id: 会话 ID
            last_n: 获取最后 N 条
            
        Returns:
            包含 history 和 summary 的字典
        """
        history = await self.get_history(session_id, last_n)
        
        summary = None
        if self.memory_manager:
            try:
                summary = await self.memory_manager.get_summary(session_id)
            except Exception as e:
                logger.warning(f"Failed to get summary: {e}")
        
        return {
            "history": history,
            "summary": summary,
        }
    
    async def close_session_with_extraction(
        self,
        session_id: str,
        extract_memories: bool = True,
    ) -> dict[str, Any]:
        """
        关闭会话并提取记忆
        
        Args:
            session_id: 会话 ID
            extract_memories: 是否提取记忆
            
        Returns:
            提取结果
        """
        result = {"extracted_count": 0}
        
        session = await self.get_session(session_id, touch=False)
        
        if extract_memories and self.memory_manager and session.user_id:
            try:
                # 获取对话历史
                history = session.history.messages
                conversation = [
                    {"role": msg.role, "content": msg.content}
                    for msg in history
                ]
                
                if conversation:
                    # 提取记忆
                    memories = await self.memory_manager.extract_and_store(
                        conversation=conversation,
                        user_id=session.user_id,
                        session_id=session_id,
                    )
                    result["extracted_count"] = len(memories)
                    logger.info(
                        f"Extracted {len(memories)} memories on session close",
                        session_id=session_id,
                    )
                    
            except Exception as e:
                logger.error(f"Memory extraction failed: {e}", exc_info=True)
                result["error"] = str(e)
        
        # 标记会话为关闭
        session.state = "closed"
        await self.update_session(session)
        
        return result
    
    async def suspend_session_with_extraction(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        挂起会话并提取记忆
        
        用于用户长时间不活跃时自动挂起
        
        Args:
            session_id: 会话 ID
            
        Returns:
            提取结果
        """
        result = await self.close_session_with_extraction(
            session_id=session_id,
            extract_memories=True,
        )
        
        # 标记为挂起而非关闭
        session = await self.get_session(session_id, touch=False)
        session.state = "suspended"
        await self.update_session(session)
        
        return result
    
    async def resume_session_with_memory(
        self,
        session_id: str,
        query: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        恢复会话并加载相关记忆
        
        Args:
            session_id: 会话 ID
            query: 当前查询（用于检索相关记忆）
            
        Returns:
            包含会话和记忆上下文的字典
        """
        session = await self.get_session(session_id)
        
        memory_context = None
        if self.memory_manager and session.user_id:
            try:
                # 获取记忆上下文
                memory_context = await self.memory_manager.get_context(
                    session_id=session_id,
                    user_id=session.user_id,
                    query=query,
                    include_summary=True,
                    include_memories=True,
                    memory_top_k=5,
                )
            except Exception as e:
                logger.warning(f"Failed to load memory context: {e}")
        
        # 如果是挂起状态，恢复为活跃
        if session.state == "suspended":
            session.state = "active"
            session.touch()
            await self.update_session(session)
        
        return {
            "session": session,
            "memory_context": memory_context,
        }
    
    async def add_message_to_memory(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> bool:
        """
        添加消息到短期记忆
        
        Args:
            session_id: 会话 ID
            role: 角色
            content: 内容
            
        Returns:
            是否触发了压缩
        """
        if not self.memory_manager:
            return False
        
        message = {"role": role, "content": content}
        return await self.memory_manager.add_to_short_term(session_id, message)
    
    async def get_context_for_agent(
        self,
        session_id: str,
        user_id: str,
        current_query: str,
    ) -> MemoryContext:
        """
        获取 Agent 所需的完整上下文
        
        整合短期记忆（窗口+摘要）和相关长期记忆
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            current_query: 当前用户查询
            
        Returns:
            记忆上下文
        """
        if not self.memory_manager:
            # 返回空上下文
            return MemoryContext(
                recent_messages=[],
                user_id=user_id,
                session_id=session_id,
            )
        
        return await self.memory_manager.get_context(
            session_id=session_id,
            user_id=user_id,
            query=current_query,
        )
