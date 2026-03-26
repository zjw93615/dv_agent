"""
RAG Service Bootstrap
RAG 服务启动配置

负责在应用启动时初始化 RAG 相关组件。
"""

import asyncio
import logging
from typing import Optional

from .config import RAGConfig, get_rag_config

logger = logging.getLogger(__name__)


class RAGServiceBootstrap:
    """
    RAG 服务启动器
    
    管理 RAG 组件的生命周期，包括：
    - 配置加载
    - 组件初始化
    - 依赖注入
    - 优雅关闭
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化启动器
        
        Args:
            config_path: 配置文件路径（可选）
        """
        self.config_path = config_path
        self.config: Optional[RAGConfig] = None
        
        # 组件实例
        self._embedder = None
        self._minio_client = None
        self._pg_store = None
        self._milvus_store = None
        self._document_manager = None
        self._retriever = None
        self._reranker = None
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        初始化所有 RAG 组件
        
        按照依赖顺序初始化：
        1. 配置
        2. 嵌入服务
        3. 存储服务
        4. 文档管理器
        5. 检索器
        """
        if self._initialized:
            logger.warning("RAG service already initialized")
            return
        
        try:
            logger.info("Initializing RAG service...")
            
            # 1. 加载配置
            self.config = get_rag_config(self.config_path)
            logger.info("RAG configuration loaded")
            
            # 2. 初始化嵌入服务
            await self._init_embedder()
            
            # 3. 初始化存储服务
            await self._init_stores()
            
            # 4. 初始化文档管理器
            await self._init_document_manager()
            
            # 5. 初始化检索器
            await self._init_retriever()
            
            # 6. 注入依赖到 API
            self._inject_dependencies()
            
            self._initialized = True
            logger.info("RAG service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}", exc_info=True)
            await self.shutdown()
            raise
    
    async def _init_embedder(self) -> None:
        """初始化嵌入服务"""
        from .embedding import BGEM3Embedder
        
        logger.info(f"Initializing embedder: {self.config.embedding.model_name}")
        
        self._embedder = BGEM3Embedder(
            model_path=self.config.embedding.model_path,
            device=self.config.embedding.device,
            batch_size=self.config.embedding.batch_size,
            max_length=self.config.embedding.max_length,
        )
        
        await self._embedder.initialize()
        logger.info("Embedder initialized")
    
    async def _init_stores(self) -> None:
        """初始化存储服务"""
        from .store import MinIOClient, PostgresDocumentStore, MilvusDocumentStore
        
        # MinIO
        logger.info(f"Connecting to MinIO: {self.config.minio.endpoint}")
        self._minio_client = MinIOClient(
            endpoint=self.config.minio.endpoint,
            access_key=self.config.minio.access_key,
            secret_key=self.config.minio.secret_key,
            secure=self.config.minio.secure,
            bucket_name=self.config.minio.bucket_name,
        )
        await self._minio_client.initialize()
        logger.info("MinIO client initialized")
        
        # PostgreSQL
        logger.info(f"Connecting to PostgreSQL: {self.config.postgres.host}")
        self._pg_store = PostgresDocumentStore(
            host=self.config.postgres.host,
            port=self.config.postgres.port,
            database=self.config.postgres.database,
            user=self.config.postgres.user,
            password=self.config.postgres.password,
        )
        await self._pg_store.initialize()
        logger.info("PostgreSQL store initialized")
        
        # Milvus
        logger.info(f"Connecting to Milvus: {self.config.milvus.host}:{self.config.milvus.port}")
        self._milvus_store = MilvusDocumentStore(
            host=self.config.milvus.host,
            port=self.config.milvus.port,
            user=self.config.milvus.user,
            password=self.config.milvus.password,
        )
        await self._milvus_store.initialize()
        logger.info("Milvus store initialized")
    
    async def _init_document_manager(self) -> None:
        """初始化文档管理器"""
        from .store import DocumentManager
        
        self._document_manager = DocumentManager(
            embedder=self._embedder,
            minio_client=self._minio_client,
            pg_store=self._pg_store,
            milvus_store=self._milvus_store,
            config=self.config,
        )
        logger.info("Document manager initialized")
    
    async def _init_retriever(self) -> None:
        """初始化检索器"""
        from .retrieval import HybridRetriever, Reranker
        
        # 初始化重排序器（如果启用）
        if self.config.retrieval.use_reranking:
            logger.info(f"Initializing reranker: {self.config.retrieval.reranker_model}")
            self._reranker = Reranker(
                model_path=self.config.retrieval.reranker_model,
                device=self.config.embedding.device,
            )
            await self._reranker.initialize()
            logger.info("Reranker initialized")
        
        # 初始化检索器
        self._retriever = HybridRetriever(
            embedder=self._embedder,
            milvus_store=self._milvus_store,
            pg_store=self._pg_store,
            reranker=self._reranker,
            config=self.config,
        )
        logger.info("Retriever initialized")
    
    def _inject_dependencies(self) -> None:
        """注入依赖到 API 层"""
        from .api import RAGDependencies
        
        RAGDependencies.set_document_manager(self._document_manager)
        RAGDependencies.set_retriever(self._retriever)
        RAGDependencies.set_embedder(self._embedder)
        
        logger.info("Dependencies injected to API layer")
    
    async def shutdown(self) -> None:
        """
        优雅关闭 RAG 服务
        
        按照依赖的逆序关闭组件。
        """
        logger.info("Shutting down RAG service...")
        
        # 清理检索器
        if self._retriever:
            try:
                await self._retriever.close()
            except Exception as e:
                logger.warning(f"Error closing retriever: {e}")
        
        # 清理重排序器
        if self._reranker:
            try:
                await self._reranker.close()
            except Exception as e:
                logger.warning(f"Error closing reranker: {e}")
        
        # 清理存储
        if self._milvus_store:
            try:
                await self._milvus_store.close()
            except Exception as e:
                logger.warning(f"Error closing Milvus: {e}")
        
        if self._pg_store:
            try:
                await self._pg_store.close()
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL: {e}")
        
        if self._minio_client:
            try:
                await self._minio_client.close()
            except Exception as e:
                logger.warning(f"Error closing MinIO: {e}")
        
        # 清理嵌入服务
        if self._embedder:
            try:
                await self._embedder.close()
            except Exception as e:
                logger.warning(f"Error closing embedder: {e}")
        
        self._initialized = False
        logger.info("RAG service shutdown complete")
    
    @property
    def document_manager(self):
        """获取文档管理器"""
        return self._document_manager
    
    @property
    def retriever(self):
        """获取检索器"""
        return self._retriever
    
    @property
    def embedder(self):
        """获取嵌入服务"""
        return self._embedder
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# 全局启动器实例
_bootstrap: Optional[RAGServiceBootstrap] = None


def get_rag_bootstrap() -> RAGServiceBootstrap:
    """
    获取 RAG 服务启动器单例
    
    Returns:
        RAGServiceBootstrap 实例
    """
    global _bootstrap
    if _bootstrap is None:
        _bootstrap = RAGServiceBootstrap()
    return _bootstrap


async def init_rag_service(config_path: Optional[str] = None) -> RAGServiceBootstrap:
    """
    初始化 RAG 服务
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        RAGServiceBootstrap 实例
    """
    global _bootstrap
    _bootstrap = RAGServiceBootstrap(config_path)
    await _bootstrap.initialize()
    return _bootstrap


async def shutdown_rag_service() -> None:
    """关闭 RAG 服务"""
    global _bootstrap
    if _bootstrap:
        await _bootstrap.shutdown()
        _bootstrap = None


# FastAPI 生命周期钩子
def create_rag_lifespan(config_path: Optional[str] = None):
    """
    创建 FastAPI 生命周期上下文管理器
    
    Usage:
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from dv_agent.rag.bootstrap import create_rag_lifespan
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with create_rag_lifespan()():
                yield
        
        app = FastAPI(lifespan=lifespan)
    """
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def lifespan():
        bootstrap = await init_rag_service(config_path)
        try:
            yield bootstrap
        finally:
            await shutdown_rag_service()
    
    return lifespan
