"""
A2A (Agent-to-Agent) 模块
基于 JSON-RPC 2.0 的 Agent 间通信协议
"""

from .models import (
    A2AMethod,
    A2ARequest,
    A2AResponse,
    A2AError,
    TaskState,
    TaskInvokeParams,
    TaskResult,
    AgentInfo,
    AgentCapability,
)
from .server import A2AServer
from .client import A2AClient, A2AClientPool

__all__ = [
    # Models
    "A2AMethod",
    "A2ARequest",
    "A2AResponse",
    "A2AError",
    "TaskState",
    "TaskInvokeParams",
    "TaskResult",
    "AgentInfo",
    "AgentCapability",
    # Server
    "A2AServer",
    # Client
    "A2AClient",
    "A2AClientPool",
]