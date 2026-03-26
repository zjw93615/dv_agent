"""
WebSocket 消息模型

定义 WebSocket 通信的消息格式和事件类型
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    """WebSocket 消息类型"""
    
    # 系统消息
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    
    # Agent 事件
    AGENT_THINKING = "agent.thinking"
    AGENT_STREAM = "agent.stream"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_TOOL_RESULT = "agent.tool_result"
    AGENT_RESPONSE = "agent.response"
    AGENT_ERROR = "agent.error"
    AGENT_COMPLETE = "agent.complete"
    
    # 文档处理事件
    DOCUMENT_PROGRESS = "document.progress"
    DOCUMENT_COMPLETED = "document.completed"
    DOCUMENT_ERROR = "document.error"
    
    # 会话事件
    SESSION_UPDATE = "session.update"
    SESSION_MESSAGE = "session.message"


class WSMessage(BaseModel):
    """WebSocket 消息基类"""
    type: WSMessageType = Field(..., description="消息类型")
    session_id: Optional[str] = Field(None, description="会话 ID")
    timestamp: int = Field(
        default_factory=lambda: int(datetime.utcnow().timestamp() * 1000),
        description="时间戳（毫秒）"
    )
    data: dict[str, Any] = Field(default_factory=dict, description="消息数据")
    
    class Config:
        use_enum_values = True


# ===== 系统消息 =====

class PingMessage(WSMessage):
    """心跳请求"""
    type: WSMessageType = WSMessageType.PING
    data: dict = Field(default_factory=dict)


class PongMessage(WSMessage):
    """心跳响应"""
    type: WSMessageType = WSMessageType.PONG
    data: dict = Field(default_factory=dict)


class ConnectedMessage(WSMessage):
    """连接成功消息"""
    type: WSMessageType = WSMessageType.CONNECTED
    data: dict = Field(default_factory=lambda: {
        "message": "Connected successfully"
    })


class ErrorMessage(WSMessage):
    """错误消息"""
    type: WSMessageType = WSMessageType.ERROR
    data: dict = Field(default_factory=dict)
    
    @classmethod
    def create(cls, error: str, code: str = "error", session_id: Optional[str] = None):
        return cls(
            session_id=session_id,
            data={"error": error, "code": code}
        )


# ===== Agent 事件 =====

class AgentThinkingEvent(WSMessage):
    """Agent 思考中事件"""
    type: WSMessageType = WSMessageType.AGENT_THINKING
    
    @classmethod
    def create(cls, session_id: str, thought: Optional[str] = None):
        return cls(
            session_id=session_id,
            data={"thought": thought, "status": "thinking"}
        )


class AgentToolCallEvent(WSMessage):
    """Agent 工具调用事件"""
    type: WSMessageType = WSMessageType.AGENT_TOOL_CALL
    
    @classmethod
    def create(
        cls,
        session_id: str,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ):
        return cls(
            session_id=session_id,
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "status": "calling"
            }
        )


class AgentToolResultEvent(WSMessage):
    """Agent 工具结果事件"""
    type: WSMessageType = WSMessageType.AGENT_TOOL_RESULT
    
    @classmethod
    def create(
        cls,
        session_id: str,
        tool_name: str,
        tool_call_id: str,
        result: str,
        success: bool = True,
    ):
        return cls(
            session_id=session_id,
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "result": result,
                "success": success,
                "status": "completed"
            }
        )


class AgentResponseEvent(WSMessage):
    """Agent 响应事件（流式）"""
    type: WSMessageType = WSMessageType.AGENT_RESPONSE
    
    @classmethod
    def create(
        cls,
        session_id: str,
        content: str,
        is_delta: bool = True,
        is_complete: bool = False,
    ):
        return cls(
            session_id=session_id,
            data={
                "content": content,
                "is_delta": is_delta,
                "is_complete": is_complete,
            }
        )


class AgentErrorEvent(WSMessage):
    """Agent 错误事件"""
    type: WSMessageType = WSMessageType.AGENT_ERROR
    
    @classmethod
    def create(
        cls,
        session_id: str,
        error: str,
        code: str = "agent_error",
        recoverable: bool = True,
    ):
        return cls(
            session_id=session_id,
            data={
                "error": error,
                "code": code,
                "recoverable": recoverable,
            }
        )


class AgentCompleteEvent(WSMessage):
    """Agent 完成事件"""
    type: WSMessageType = WSMessageType.AGENT_COMPLETE
    
    @classmethod
    def create(
        cls,
        session_id: str,
        message_id: Optional[str] = None,
        total_tokens: Optional[int] = None,
    ):
        return cls(
            session_id=session_id,
            data={
                "message_id": message_id,
                "total_tokens": total_tokens,
                "status": "complete"
            }
        )


# ===== 文档处理事件 =====

class DocumentProgressEvent(WSMessage):
    """文档处理进度事件"""
    type: WSMessageType = WSMessageType.DOCUMENT_PROGRESS
    
    @classmethod
    def create(
        cls,
        document_id: str,
        stage: str,
        progress: float,
        message: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        return cls(
            session_id=session_id,
            data={
                "document_id": document_id,
                "stage": stage,  # "uploading", "parsing", "chunking", "embedding", "indexing"
                "progress": progress,  # 0.0 - 1.0
                "message": message,
            }
        )


class DocumentCompletedEvent(WSMessage):
    """文档处理完成事件"""
    type: WSMessageType = WSMessageType.DOCUMENT_COMPLETED
    
    @classmethod
    def create(
        cls,
        document_id: str,
        filename: str,
        chunk_count: int,
        session_id: Optional[str] = None,
    ):
        return cls(
            session_id=session_id,
            data={
                "document_id": document_id,
                "filename": filename,
                "chunk_count": chunk_count,
                "status": "completed"
            }
        )


class DocumentErrorEvent(WSMessage):
    """文档处理错误事件"""
    type: WSMessageType = WSMessageType.DOCUMENT_ERROR
    
    @classmethod
    def create(
        cls,
        document_id: str,
        error: str,
        stage: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        return cls(
            session_id=session_id,
            data={
                "document_id": document_id,
                "error": error,
                "stage": stage,
                "status": "error"
            }
        )
