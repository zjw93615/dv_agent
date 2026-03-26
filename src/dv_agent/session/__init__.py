"""
Session 模块
会话管理、对话历史和状态持久化
"""

from .models import (
    Session,
    SessionState,
    ConversationHistory,
    ConversationMessage,
    MessageType,
    AgentContext,
    ReActStep,
)
from .manager import SessionManager
from .redis_client import (
    RedisClient,
    RedisSettings,
    get_redis_client,
    init_redis,
    close_redis,
    redis_context,
)

__all__ = [
    # Models
    "Session",
    "SessionState",
    "ConversationHistory",
    "ConversationMessage",
    "MessageType",
    "AgentContext",
    "ReActStep",
    # Manager
    "SessionManager",
    # Redis
    "RedisClient",
    "RedisSettings",
    "get_redis_client",
    "init_redis",
    "close_redis",
    "redis_context",
]