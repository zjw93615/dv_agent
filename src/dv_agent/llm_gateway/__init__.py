"""
LLM Gateway 模块
统一的大语言模型访问层
"""

from .models import (
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TokenUsage,
    ProviderConfig,
    RetryConfig,
)
from .base_adapter import BaseAdapter
from .openai_adapter import OpenAIAdapter
from .deepseek_adapter import DeepSeekAdapter
from .ollama_adapter import OllamaAdapter
from .gateway import (
    LLMGateway,
    get_llm_gateway,
    PROVIDER_ADAPTERS,
)

# Alias for compatibility
Role = MessageRole

__all__ = [
    # Models
    "Message",
    "MessageRole",
    "Role",  # Alias
    "ToolCall",
    "ToolDefinition",
    "LLMRequest",
    "LLMResponse",
    "StreamChunk",
    "TokenUsage",
    "ProviderConfig",
    "RetryConfig",
    # Adapters
    "BaseAdapter",
    "OpenAIAdapter",
    "DeepSeekAdapter",
    "OllamaAdapter",
    # Gateway
    "LLMGateway",
    "get_llm_gateway",
    "PROVIDER_ADAPTERS",
]
