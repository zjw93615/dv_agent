"""
RAG (Retrieval-Augmented Generation) Module
文档检索增强生成模块

提供：
- 多格式文档处理流水线
- BGE-M3 向量化服务
- 文档存储管理
- RAG-Fusion 混合检索
- REST API 接口

Usage:
    from dv_agent.rag import RAGConfig, get_rag_config
    from dv_agent.rag.api import router as rag_router
    
    # 在 FastAPI 应用中注册路由
    app.include_router(rag_router)
"""

from .config import (
    RAGConfig,
    EmbeddingConfig,
    PipelineConfig,
    MilvusConfig,
    PostgresConfig,
    MinIOConfig,
    RetrievalConfig,
    QuotaConfig,
    get_rag_config,
    reload_rag_config,
)

__all__ = [
    # Configuration
    "RAGConfig",
    "EmbeddingConfig",
    "PipelineConfig", 
    "MilvusConfig",
    "PostgresConfig",
    "MinIOConfig",
    "RetrievalConfig",
    "QuotaConfig",
    "get_rag_config",
    "reload_rag_config",
]


# Lazy imports for heavy components
def __getattr__(name: str):
    """延迟加载重型组件"""
    
    # API
    if name == "router":
        from .api import router
        return router
    elif name == "RAGDependencies":
        from .api import RAGDependencies
        return RAGDependencies
    
    # Pipeline components
    elif name == "DocumentPipeline":
        from .pipeline import DocumentPipeline
        return DocumentPipeline
    elif name == "DocumentDetector":
        from .pipeline import DocumentDetector
        return DocumentDetector
    elif name == "TextChunker":
        from .pipeline import TextChunker
        return TextChunker
    elif name == "TextCleaner":
        from .pipeline import TextCleaner
        return TextCleaner
    
    # Embedding
    elif name == "BGEM3Embedder":
        from .embedding import BGEM3Embedder
        return BGEM3Embedder
    
    # Store
    elif name == "DocumentManager":
        from .store import DocumentManager
        return DocumentManager
    elif name == "MinIOClient":
        from .store import MinIOClient
        return MinIOClient
    elif name == "PostgresDocumentStore":
        from .store import PostgresDocumentStore
        return PostgresDocumentStore
    elif name == "MilvusDocumentStore":
        from .store import MilvusDocumentStore
        return MilvusDocumentStore
    
    # Retrieval
    elif name == "HybridRetriever":
        from .retrieval import HybridRetriever
        return HybridRetriever
    elif name == "RetrievalQuery":
        from .retrieval import RetrievalQuery
        return RetrievalQuery
    elif name == "RetrievalResult":
        from .retrieval import RetrievalResult
        return RetrievalResult
    elif name == "RetrievalResponse":
        from .retrieval import RetrievalResponse
        return RetrievalResponse
    elif name == "SearchMode":
        from .retrieval import SearchMode
        return SearchMode
    elif name == "Reranker":
        from .retrieval import Reranker
        return Reranker
    
    raise AttributeError(f"module 'dv_agent.rag' has no attribute '{name}'")