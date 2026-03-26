"""
WebSocket 连接管理器

提供 WebSocket 连接的管理、认证、心跳和消息分发
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Set
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from .models import (
    ConnectedMessage,
    ErrorMessage,
    PongMessage,
    WSMessage,
    WSMessageType,
)

logger = logging.getLogger(__name__)

# 配置常量
MAX_CONNECTIONS_PER_USER = 100
HEARTBEAT_INTERVAL = 30  # 秒
HEARTBEAT_TIMEOUT = 60  # 秒


@dataclass
class Connection:
    """WebSocket 连接封装"""
    id: str
    websocket: WebSocket
    user_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)
    subscribed_sessions: Set[str] = field(default_factory=set)
    
    def __hash__(self) -> int:
        """使 Connection 可哈希（基于 id）"""
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        """基于 id 比较"""
        if not isinstance(other, Connection):
            return False
        return self.id == other.id
    
    def is_alive(self) -> bool:
        """检查连接是否存活（心跳超时判断）"""
        elapsed = (datetime.utcnow() - self.last_ping).total_seconds()
        return elapsed < HEARTBEAT_TIMEOUT
    
    def touch(self) -> None:
        """更新最后心跳时间"""
        self.last_ping = datetime.utcnow()
    
    async def send(self, message: WSMessage) -> bool:
        """发送消息"""
        try:
            await self.websocket.send_json(message.model_dump(mode="json"))
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to connection {self.id}: {e}")
            return False
    
    async def send_json(self, data: dict) -> bool:
        """发送 JSON 数据"""
        try:
            await self.websocket.send_json(data)
            return True
        except Exception as e:
            logger.warning(f"Failed to send JSON to connection {self.id}: {e}")
            return False


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(
        self,
        max_connections_per_user: int = MAX_CONNECTIONS_PER_USER,
        heartbeat_interval: int = HEARTBEAT_INTERVAL,
    ):
        self.max_connections_per_user = max_connections_per_user
        self.heartbeat_interval = heartbeat_interval
        
        # 连接存储
        # user_id -> Set[Connection]
        self._connections: dict[str, Set[Connection]] = {}
        # connection_id -> Connection
        self._connection_by_id: dict[str, Connection] = {}
        # session_id -> Set[Connection] (订阅关系)
        self._session_subscribers: dict[str, Set[Connection]] = {}
        
        # 事件处理器
        self._event_handlers: dict[str, list[Callable]] = {}
        
        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """启动管理器（心跳任务等）"""
        if self._running:
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocket manager started")
    
    async def stop(self) -> None:
        """停止管理器"""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有连接
        for user_id in list(self._connections.keys()):
            for conn in list(self._connections.get(user_id, set())):
                await self.disconnect(conn.id, reason="server_shutdown")
        
        logger.info("WebSocket manager stopped")
    
    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
    ) -> Optional[Connection]:
        """
        建立新连接
        
        Args:
            websocket: WebSocket 对象
            user_id: 用户 ID
            
        Returns:
            Connection 对象，如果超出限制返回 None
        """
        # 检查连接数限制
        user_connections = self._connections.get(user_id, set())
        if len(user_connections) >= self.max_connections_per_user:
            logger.warning(
                f"Connection limit reached for user {user_id}: {len(user_connections)}"
            )
            await websocket.close(code=4429, reason="Too many connections")
            return None
        
        # 接受连接
        await websocket.accept()
        
        # 创建连接对象
        connection = Connection(
            id=str(uuid4()),
            websocket=websocket,
            user_id=user_id,
        )
        
        # 存储连接
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(connection)
        self._connection_by_id[connection.id] = connection
        
        # 发送连接成功消息
        await connection.send(ConnectedMessage())
        
        logger.info(
            f"WebSocket connected: user={user_id}, conn={connection.id}, "
            f"total_user_conns={len(self._connections[user_id])}"
        )
        
        return connection
    
    async def disconnect(
        self,
        connection_id: str,
        reason: str = "client_disconnect",
    ) -> None:
        """
        断开连接
        
        Args:
            connection_id: 连接 ID
            reason: 断开原因
        """
        connection = self._connection_by_id.get(connection_id)
        if not connection:
            return
        
        user_id = connection.user_id
        
        # 清理订阅
        for session_id in list(connection.subscribed_sessions):
            self._unsubscribe_session(connection, session_id)
        
        # 清理连接存储
        if user_id in self._connections:
            self._connections[user_id].discard(connection)
            if not self._connections[user_id]:
                del self._connections[user_id]
        
        del self._connection_by_id[connection_id]
        
        # 关闭 WebSocket
        try:
            await connection.websocket.close()
        except Exception:
            pass
        
        logger.info(
            f"WebSocket disconnected: user={user_id}, conn={connection_id}, reason={reason}"
        )
    
    def subscribe_session(
        self,
        connection: Connection,
        session_id: str,
    ) -> None:
        """订阅会话事件"""
        if session_id not in self._session_subscribers:
            self._session_subscribers[session_id] = set()
        
        self._session_subscribers[session_id].add(connection)
        connection.subscribed_sessions.add(session_id)
        
        logger.debug(f"Connection {connection.id} subscribed to session {session_id}")
    
    def _unsubscribe_session(
        self,
        connection: Connection,
        session_id: str,
    ) -> None:
        """取消订阅会话事件"""
        if session_id in self._session_subscribers:
            self._session_subscribers[session_id].discard(connection)
            if not self._session_subscribers[session_id]:
                del self._session_subscribers[session_id]
        
        connection.subscribed_sessions.discard(session_id)
    
    async def handle_message(
        self,
        connection: Connection,
        data: dict,
    ) -> None:
        """
        处理收到的消息
        
        Args:
            connection: 连接对象
            data: 消息数据
        """
        msg_type = data.get("type")
        
        if msg_type == "ping":
            # 心跳响应
            connection.touch()
            await connection.send(PongMessage())
            
        elif msg_type == "subscribe":
            # 订阅会话
            session_id = data.get("session_id")
            if session_id:
                self.subscribe_session(connection, session_id)
                
        elif msg_type == "unsubscribe":
            # 取消订阅
            session_id = data.get("session_id")
            if session_id:
                self._unsubscribe_session(connection, session_id)
                
        else:
            # 触发自定义事件处理器
            handlers = self._event_handlers.get(msg_type, [])
            for handler in handlers:
                try:
                    await handler(connection, data)
                except Exception as e:
                    logger.error(f"Error in event handler for {msg_type}: {e}")
    
    def on(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    # ===== 消息发送方法 =====
    
    async def send_to_connection(
        self,
        connection_id: str,
        message: WSMessage,
    ) -> bool:
        """发送消息到指定连接"""
        connection = self._connection_by_id.get(connection_id)
        if not connection:
            return False
        return await connection.send(message)
    
    async def send_to_user(
        self,
        user_id: str,
        message: WSMessage,
    ) -> int:
        """
        发送消息到用户的所有连接
        
        Returns:
            成功发送的连接数
        """
        connections = self._connections.get(user_id, set())
        sent = 0
        
        for conn in connections:
            if await conn.send(message):
                sent += 1
        
        return sent
    
    async def send_to_session(
        self,
        session_id: str,
        message: WSMessage,
    ) -> int:
        """
        发送消息到订阅了指定会话的所有连接
        
        Returns:
            成功发送的连接数
        """
        subscribers = self._session_subscribers.get(session_id, set())
        sent = 0
        
        for conn in subscribers:
            if await conn.send(message):
                sent += 1
        
        return sent
    
    async def broadcast(
        self,
        message: WSMessage,
        exclude_users: Optional[set[str]] = None,
    ) -> int:
        """
        广播消息到所有连接
        
        Returns:
            成功发送的连接数
        """
        exclude_users = exclude_users or set()
        sent = 0
        
        for user_id, connections in self._connections.items():
            if user_id in exclude_users:
                continue
            for conn in connections:
                if await conn.send(message):
                    sent += 1
        
        return sent
    
    # ===== 统计信息 =====
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total_connections = sum(
            len(conns) for conns in self._connections.values()
        )
        
        return {
            "total_connections": total_connections,
            "total_users": len(self._connections),
            "total_session_subscriptions": sum(
                len(subs) for subs in self._session_subscribers.values()
            ),
        }
    
    def get_user_connection_count(self, user_id: str) -> int:
        """获取用户连接数"""
        return len(self._connections.get(user_id, set()))
    
    # ===== 心跳循环 =====
    
    async def _heartbeat_loop(self) -> None:
        """心跳检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
    
    async def _check_connections(self) -> None:
        """检查并清理超时连接"""
        to_disconnect = []
        
        for conn in list(self._connection_by_id.values()):
            if not conn.is_alive():
                to_disconnect.append(conn.id)
        
        for conn_id in to_disconnect:
            await self.disconnect(conn_id, reason="heartbeat_timeout")
        
        if to_disconnect:
            logger.info(f"Cleaned up {len(to_disconnect)} timed out connections")


# 全局实例
ws_manager = WebSocketManager()
