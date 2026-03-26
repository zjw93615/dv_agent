"""
DV-Agent: Multi-Agent AI Framework with ReAct Reasoning.

A production-grade AI agent framework featuring:
- Multi-agent orchestration with ReAct reasoning loops
- Unified LLM gateway with provider fallback
- A2A (Agent-to-Agent) protocol for distributed communication
- Session management with Redis persistence
- MCP (Model Context Protocol) tool integration
- Intent recognition and routing

Usage:
    # Start server
    from dv_agent import run_server
    run_server()
    
    # Or use programmatically
    from dv_agent import create_application
    
    async with create_application() as app:
        result = await app.process_message("Hello!")
        print(result)
"""

__version__ = "0.1.0"
__author__ = "DV-Agent Team"

# Core exports
from .app import Application, create_application, create_app
from .main import run_server, process_single
from .config.settings import Settings, get_settings

# Component exports
from .llm_gateway.gateway import LLMGateway
from .llm_gateway.models import Message, LLMResponse, MessageRole
from .llm_gateway import Role  # Alias for MessageRole

from .session.manager import SessionManager
from .session.models import Session, ConversationHistory, AgentContext

from .agents.base_agent import BaseAgent
from .agents.orchestrator import Orchestrator
from .agents.react_loop import ReActLoop

from .intent.recognizer import IntentRecognizer
from .intent.router import IntentRouter
from .intent.models import IntentResult, Intent

from .tools.registry import ToolRegistry
from .tools.models import BaseTool as Tool, ToolResult
from .tools.mcp_manager import MCPManager

from .a2a.server import A2AServer
from .a2a.client import A2AClient
from .a2a.models import A2ARequest, A2AResponse

__all__ = [
    # Version
    "__version__",
    
    # Application
    "Application",
    "create_application",
    "create_app",
    "run_server",
    "process_single",
    
    # Settings
    "Settings",
    "get_settings",
    
    # LLM Gateway
    "LLMGateway",
    "Message",
    "LLMResponse",
    "Role",
    
    # Session
    "SessionManager",
    "Session",
    "ConversationHistory",
    "AgentContext",
    
    # Agents
    "BaseAgent",
    "Orchestrator",
    "ReActLoop",
    
    # Intent
    "IntentRecognizer",
    "IntentRouter",
    "IntentResult",
    "Intent",
    
    # Tools
    "ToolRegistry",
    "Tool",
    "ToolResult",
    "MCPManager",
    
    # A2A
    "A2AServer",
    "A2AClient",
    "A2ARequest",
    "A2AResponse",
]