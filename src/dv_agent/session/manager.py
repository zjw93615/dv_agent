"""
Session Manager
会话管理器，提供 CRUD 操作和 Redis 持久化
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from .models import (
    Session,
    SessionState,
    ConversationHistory,
    ConversationMessage,
    AgentContext,
)
from .redis_client import RedisClient
from ..config.exceptions import SessionNotFoundError, SessionExpiredError
from ..config.logging import get_logger

logger = get_logger(__name__)

# Redis Key 前缀
SESSION_PREFIX = "session:"
HISTORY_PREFIX = "history:"
CONTEXT_PREFIX = "context:"
USER_SESSIONS_PREFIX = "user_sessions:"


class SessionManager:
    """
    会话管理器
    
    功能：
    - Session CRUD
    - Redis 持久化
    - TTL 管理
    - 会话恢复
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        default_ttl: int = 3600 * 24,  # 24小时
    ):
        self.redis = redis_client
        self.default_ttl = default_ttl
    
    # ===== Session CRUD =====
    
    async def create_session(
        self,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        ttl: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Session:
        """创建新会话"""
        session_id = str(uuid4())
        ttl = ttl or self.default_ttl
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            title=title,
            ttl=ttl,
            metadata=metadata or {},
            history=ConversationHistory(session_id=session_id),
        )
        
        await self._save_session(session)
        
        # 关联用户
        if user_id:
            await self._add_user_session(user_id, session_id)
        
        logger.info(
            f"Session created",
            session_id=session_id,
            user_id=user_id,
            ttl=ttl,
        )
        
        return session
    
    async def get_session(
        self,
        session_id: str,
        touch: bool = True,
    ) -> Session:
        """获取会话"""
        key = f"{SESSION_PREFIX}{session_id}"
        data = await self.redis.get_json(key)
        
        if not data:
            raise SessionNotFoundError(
                message=f"Session not found: {session_id}",
                session_id=session_id,
            )
        
        session = Session(**data)
        
        # 检查过期
        if session.is_expired:
            session.state = SessionState.EXPIRED
            await self._save_session(session)
            raise SessionExpiredError(
                message=f"Session expired: {session_id}",
                session_id=session_id,
            )
        
        # 更新活跃时间
        if touch and session.is_active:
            session.touch()
            await self._save_session(session)
        
        return session
    
    async def update_session(self, session: Session) -> None:
        """更新会话"""
        session.updated_at = datetime.utcnow()
        await self._save_session(session)
    
    async def delete_session(self, session_id: str) -> None:
        """删除会话"""
        key = f"{SESSION_PREFIX}{session_id}"
        
        # 获取会话信息（用于清理关联数据）
        try:
            session = await self.get_session(session_id, touch=False)
            if session.user_id:
                await self._remove_user_session(session.user_id, session_id)
        except SessionNotFoundError:
            pass
        
        # 删除会话数据
        await self.redis.delete(key)
        await self.redis.delete(f"{HISTORY_PREFIX}{session_id}")
        await self.redis.delete(f"{CONTEXT_PREFIX}{session_id}")
        
        logger.info(f"Session deleted", session_id=session_id)
    
    async def _save_session(self, session: Session) -> None:
        """保存会话到 Redis"""
        key = f"{SESSION_PREFIX}{session.session_id}"
        await self.redis.set_json(key, session.model_dump(mode="json"), ttl=session.ttl)
    
    # ===== 对话历史 =====
    
    async def add_message(
        self,
        session_id: str,
        message: ConversationMessage,
    ) -> None:
        """添加消息到会话历史"""
        session = await self.get_session(session_id)
        session.history.add_message(message)
        await self._save_session(session)
    
    async def add_user_message(
        self,
        session_id: str,
        content: str,
        **kwargs,
    ) -> ConversationMessage:
        """添加用户消息"""
        session = await self.get_session(session_id)
        msg = session.history.add_user_message(content, **kwargs)
        await self._save_session(session)
        return msg
    
    async def add_assistant_message(
        self,
        session_id: str,
        content: str,
        **kwargs,
    ) -> ConversationMessage:
        """添加助手消息"""
        session = await self.get_session(session_id)
        msg = session.history.add_assistant_message(content, **kwargs)
        await self._save_session(session)
        return msg
    
    async def get_history(
        self,
        session_id: str,
        last_n: Optional[int] = None,
    ) -> ConversationHistory:
        """获取对话历史"""
        session = await self.get_session(session_id, touch=False)
        
        if last_n:
            # 返回裁剪后的历史
            history = ConversationHistory(
                session_id=session_id,
                messages=session.history.get_last_n(last_n),
            )
            return history
        
        return session.history
    
    # ===== Agent 上下文 =====
    
    async def get_agent_context(
        self,
        session_id: str,
        agent_id: str,
    ) -> AgentContext:
        """获取 Agent 上下文"""
        session = await self.get_session(session_id)
        return session.get_agent_context(agent_id)
    
    async def update_agent_context(
        self,
        session_id: str,
        agent_id: str,
        context: AgentContext,
    ) -> None:
        """更新 Agent 上下文"""
        session = await self.get_session(session_id)
        session.agent_contexts[agent_id] = context
        await self._save_session(session)
    
    async def save_react_checkpoint(
        self,
        session_id: str,
        agent_id: str,
    ) -> None:
        """保存 ReAct 检查点（用于恢复）"""
        session = await self.get_session(session_id)
        ctx = session.get_agent_context(agent_id)
        
        # 单独保存上下文（避免丢失）
        key = f"{CONTEXT_PREFIX}{session_id}:{agent_id}"
        await self.redis.set_json(key, ctx.model_dump(mode="json"), ttl=session.ttl)
    
    async def restore_react_checkpoint(
        self,
        session_id: str,
        agent_id: str,
    ) -> Optional[AgentContext]:
        """恢复 ReAct 检查点"""
        key = f"{CONTEXT_PREFIX}{session_id}:{agent_id}"
        data = await self.redis.get_json(key)
        
        if data:
            return AgentContext(**data)
        return None
    
    # ===== 用户会话 =====
    
    async def _add_user_session(self, user_id: str, session_id: str) -> None:
        """关联用户会话"""
        key = f"{USER_SESSIONS_PREFIX}{user_id}"
        await self.redis.sadd(key, session_id)
    
    async def _remove_user_session(self, user_id: str, session_id: str) -> None:
        """移除用户会话关联"""
        key = f"{USER_SESSIONS_PREFIX}{user_id}"
        await self.redis.srem(key, session_id)
    
    async def get_user_sessions(
        self,
        user_id: str,
        active_only: bool = True,
    ) -> list[Session]:
        """获取用户的所有会话"""
        key = f"{USER_SESSIONS_PREFIX}{user_id}"
        session_ids = await self.redis.smembers(key)
        
        sessions = []
        for sid in session_ids:
            try:
                session = await self.get_session(sid, touch=False)
                if active_only and not session.is_active:
                    continue
                sessions.append(session)
            except (SessionNotFoundError, SessionExpiredError):
                # 清理无效关联
                await self._remove_user_session(user_id, sid)
        
        # 按最后活跃时间排序
        sessions.sort(key=lambda s: s.last_active_at, reverse=True)
        return sessions
    
    async def get_resumable_sessions(
        self,
        user_id: str,
    ) -> list[dict]:
        """获取可恢复的会话（有未完成任务）"""
        sessions = await self.get_user_sessions(user_id)
        
        resumable = []
        for session in sessions:
            ctx = session.get_resumable_context()
            if ctx:
                resumable.append(ctx)
        
        return resumable
    
    # ===== 会话状态管理 =====
    
    async def pause_session(self, session_id: str) -> None:
        """暂停会话"""
        session = await self.get_session(session_id)
        session.pause()
        await self._save_session(session)
        logger.info(f"Session paused", session_id=session_id)
    
    async def resume_session(self, session_id: str) -> Session:
        """恢复会话"""
        session = await self.get_session(session_id)
        
        if not session.can_resume():
            raise SessionExpiredError(
                message=f"Session cannot be resumed: {session_id}",
                session_id=session_id,
            )
        
        session.resume()
        await self._save_session(session)
        logger.info(f"Session resumed", session_id=session_id)
        
        return session
    
    async def complete_session(self, session_id: str) -> None:
        """完成会话"""
        session = await self.get_session(session_id)
        session.complete()
        await self._save_session(session)
        logger.info(f"Session completed", session_id=session_id)
    
    async def extend_session(
        self,
        session_id: str,
        additional_ttl: int,
    ) -> None:
        """延长会话 TTL"""
        session = await self.get_session(session_id)
        session.ttl += additional_ttl
        if session.expires_at:
            session.expires_at += timedelta(seconds=additional_ttl)
        await self._save_session(session)
        logger.debug(f"Session TTL extended", session_id=session_id, new_ttl=session.ttl)
    
    # ===== 清理 =====
    
    async def cleanup_expired_sessions(
        self,
        user_id: Optional[str] = None,
    ) -> int:
        """清理过期会话"""
        if user_id:
            sessions = await self.get_user_sessions(user_id, active_only=False)
        else:
            # 全局清理需要扫描（慎用）
            logger.warning("Global session cleanup is not recommended")
            return 0
        
        cleaned = 0
        for session in sessions:
            if session.is_expired:
                await self.delete_session(session.session_id)
                cleaned += 1
        
        if cleaned > 0:
            logger.info(f"Cleaned up expired sessions", count=cleaned, user_id=user_id)
        
        return cleaned
