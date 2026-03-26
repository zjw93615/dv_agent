"""
WebSocket 路由

提供 WebSocket 端点和认证
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ..auth.jwt import jwt_manager
from .manager import ws_manager, Connection
from .models import ErrorMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def verify_ws_token(token: str) -> Optional[str]:
    """
    验证 WebSocket Token
    
    Args:
        token: JWT Token（从 query parameter 获取）
        
    Returns:
        用户 ID，验证失败返回 None
    """
    if not token:
        return None
    
    payload = jwt_manager.verify_token(token, expected_type="access")
    if not payload:
        return None
    
    return payload.sub


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Access Token"),
):
    """
    WebSocket 端点
    
    认证方式：通过 query parameter 传递 JWT Token
    
    示例：
        ws://localhost:8000/ws?token=<jwt_token>
    
    消息协议：
        所有消息都是 JSON 格式，包含 type 字段
        
        客户端发送：
        - {"type": "ping"} - 心跳
        - {"type": "subscribe", "session_id": "<id>"} - 订阅会话事件
        - {"type": "unsubscribe", "session_id": "<id>"} - 取消订阅
        
        服务器发送：
        - {"type": "pong"} - 心跳响应
        - {"type": "connected"} - 连接成功
        - {"type": "agent.thinking", ...} - Agent 思考中
        - {"type": "agent.tool_call", ...} - 工具调用
        - {"type": "agent.tool_result", ...} - 工具结果
        - {"type": "agent.response", ...} - Agent 响应
        - {"type": "document.progress", ...} - 文档处理进度
        - 等等...
    """
    # 验证 Token
    user_id = await verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return
    
    # 建立连接
    connection = await ws_manager.connect(websocket, user_id)
    if not connection:
        # 连接被拒绝（超出限制）
        return
    
    try:
        # 消息循环
        while True:
            try:
                data = await websocket.receive_json()
                await ws_manager.handle_message(connection, data)
            except ValueError as e:
                # JSON 解析错误
                logger.warning(f"Invalid JSON from {connection.id}: {e}")
                await connection.send(
                    ErrorMessage.create("Invalid JSON message", "invalid_json")
                )
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected by client: {connection.id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await ws_manager.disconnect(connection.id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    获取 WebSocket 统计信息
    
    返回当前连接数、用户数等统计
    """
    return ws_manager.get_stats()
