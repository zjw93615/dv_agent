"""上下文工程模块

为 DV-Agent 提供上下文管理能力：
- TokenCounter: Token 计数器（tiktoken + 缓存）
- HistoryManager: 历史管理与压缩
- ContextBuilder: GSSC 流水线（Gather-Select-Structure-Compress）
- ObservationTruncator: 工具输出截断器
- PromptTemplate: 结构化提示词模板
- EntityMemory: 实体记忆系统
- RAGContextRetriever: RAG 上下文检索器 (向量检索历史对话)
"""

from .token_counter import TokenCounter, get_token_counter
from .history_manager import HistoryManager
from .context_builder import ContextBuilder, ContextPacket, ContextType, StructuredContext
from .observation_truncator import (
    ObservationTruncator,
    TruncateStrategy,
    TruncateResult,
    get_truncator,
    truncate_output,
)
from .prompt_template import (
    PromptTemplate,
    TemplateType,
    TemplateManager,
    get_template_manager,
    get_template,
    render_template,
)
from .entity_memory import (
    EntityMemory,
    Entity,
    EntityType,
    get_entity_memory,
    clear_memory_cache,
)
from .rag_context_retriever import (
    RAGContextRetriever,
    RetrievedContext,
    retrieve_relevant_context,
)

__all__ = [
    # Token 计数
    "TokenCounter",
    "get_token_counter",
    # 历史管理
    "HistoryManager",
    # GSSC 上下文构建
    "ContextBuilder",
    "ContextPacket",
    "ContextType",
    "StructuredContext",
    # 工具输出截断
    "ObservationTruncator",
    "TruncateStrategy",
    "TruncateResult",
    "get_truncator",
    "truncate_output",
    # 结构化模板
    "PromptTemplate",
    "TemplateType",
    "TemplateManager",
    "get_template_manager",
    "get_template",
    "render_template",
    # 实体记忆
    "EntityMemory",
    "Entity",
    "EntityType",
    "get_entity_memory",
    "clear_memory_cache",
    # RAG 上下文检索
    "RAGContextRetriever",
    "RetrievedContext",
    "retrieve_relevant_context",
]
