"""
WebSocket 模块 - 实时通信

提供：
- WebSocket 连接管理
- 认证验证
- 心跳保活
- Agent 状态推送
- 文档处理进度推送

使用示例:
    from dv_agent.websocket import WebSocketManager
    
    ws_manager = WebSocketManager()
    await ws_manager.connect(websocket, user_id)
    await ws_manager.broadcast_to_user(user_id, message)
"""

from .manager import WebSocketManager, Connection
from .models import (
    WSMessage,
    WSMessageType,
    AgentThinkingEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentResponseEvent,
    AgentErrorEvent,
    DocumentProgressEvent,
    DocumentCompletedEvent,
)
from .router import router as websocket_router

__all__ = [
    # Manager
    "WebSocketManager",
    "Connection",
    # Models
    "WSMessage",
    "WSMessageType",
    "AgentThinkingEvent",
    "AgentToolCallEvent",
    "AgentToolResultEvent",
    "AgentResponseEvent",
    "AgentErrorEvent",
    "DocumentProgressEvent",
    "DocumentCompletedEvent",
    # Router
    "websocket_router",
]
