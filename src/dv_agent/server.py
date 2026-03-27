"""
FastAPI server entry point for uvicorn.

Usage:
    uvicorn dv_agent.server:app --host 0.0.0.0 --port 8080 --reload --reload-dir src
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

import asyncpg

from .a2a.server import A2AServer
from .auth.router import router as auth_router, set_db_pool
from .session.api import router as session_router, set_session_manager
from .session.manager import SessionManager
from .session.redis_client import RedisClient, RedisSettings
from .rag.api import router as rag_router, RAGDependencies
from .rag.config import (
    RAGConfig, MilvusConfig, MinIOConfig, PostgresConfig, 
    EmbeddingConfig
)
from .websocket.router import router as ws_router
from .websocket.manager import ws_manager


# Database connection pool
_db_pool: asyncpg.Pool | None = None
_redis_client: RedisClient | None = None
_session_manager: SessionManager | None = None

# RAG components
_rag_initialized: bool = False


async def init_db_pool() -> asyncpg.Pool:
    """Initialize PostgreSQL connection pool"""
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", os.getenv("RAG_POSTGRES_HOST", "localhost")),
        port=int(os.getenv("POSTGRES_PORT", os.getenv("RAG_POSTGRES_PORT", "5432"))),
        database=os.getenv("POSTGRES_DB", os.getenv("RAG_POSTGRES_DATABASE", "dv_agent")),
        user=os.getenv("POSTGRES_USER", os.getenv("RAG_POSTGRES_USER", "postgres")),
        password=os.getenv("POSTGRES_PASSWORD", os.getenv("RAG_POSTGRES_PASSWORD", "postgres123")),
        min_size=2,
        max_size=10,
    )
    return pool


@asynccontextmanager
async def lifespan(app):
    """Application lifespan manager"""
    global _db_pool, _redis_client, _session_manager
    
    # Startup
    print("🚀 Starting DV-Agent server...")
    
    # Initialize PostgreSQL
    try:
        _db_pool = await init_db_pool()
        set_db_pool(_db_pool)
        print("✅ PostgreSQL connected")
    except Exception as e:
        print(f"⚠️  PostgreSQL connection failed: {e}")
        print("   Auth features will be unavailable")
    
    # Initialize Redis and SessionManager
    try:
        redis_settings = RedisSettings(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD", None),
        )
        _redis_client = RedisClient(redis_settings)
        await _redis_client.connect()
        _session_manager = SessionManager(_redis_client)
        set_session_manager(_session_manager)
        print("✅ Redis connected, SessionManager ready")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        print("   Session features will be unavailable")
    
    # Initialize RAG components
    await init_rag_components()
    
    yield
    
    # Shutdown
    print("🛑 Shutting down...")
    await cleanup_rag_components()
    if _redis_client:
        await _redis_client.disconnect()
        print("✅ Redis disconnected")
    if _db_pool:
        await _db_pool.close()
        print("✅ PostgreSQL disconnected")


async def init_rag_components():
    """Initialize RAG components (Milvus, MinIO, DocumentManager)"""
    global _rag_initialized
    
    try:
        # Import RAG components lazily to avoid import errors
        from .rag.store import MinIOClient, PostgresDocumentStore, MilvusDocumentStore, DocumentManager
        from .rag.pipeline import DocumentPipeline
        
        # Initialize MinIO client (uses lazy connection, no explicit connect needed)
        minio_client = MinIOClient(
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            default_bucket=os.getenv("MINIO_BUCKET", "dv-agent-documents"),
        )
        # Test MinIO connection by ensuring bucket exists
        try:
            minio_client.ensure_bucket(minio_client.default_bucket)
            print("✅ MinIO connected")
        except Exception as e:
            print(f"⚠️  MinIO connection failed: {e}")
            minio_client = None
        
        # Initialize PostgreSQL document store (reuse existing pool if available)
        pg_store = None
        if _db_pool:
            pg_store = PostgresDocumentStore(pool=_db_pool)
            print("✅ RAG PostgreSQL store ready (using shared pool)")
        else:
            # Create own connection string
            pg_conn_str = (
                f"postgresql://{os.getenv('RAG_POSTGRES_USER', os.getenv('POSTGRES_USER', 'postgres'))}:"
                f"{os.getenv('RAG_POSTGRES_PASSWORD', os.getenv('POSTGRES_PASSWORD', 'postgres123'))}@"
                f"{os.getenv('RAG_POSTGRES_HOST', os.getenv('POSTGRES_HOST', 'localhost'))}:"
                f"{os.getenv('RAG_POSTGRES_PORT', os.getenv('POSTGRES_PORT', '5432'))}/"
                f"{os.getenv('RAG_POSTGRES_DATABASE', os.getenv('POSTGRES_DB', 'dv_agent'))}"
            )
            pg_store = PostgresDocumentStore(connection_string=pg_conn_str)
            print("✅ RAG PostgreSQL store ready")
        
        # Initialize Milvus document store (sync connect)
        milvus_store = None
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = int(os.getenv("MILVUS_PORT", "19530"))
        try:
            print(f"   Connecting to Milvus at {milvus_host}:{milvus_port}...")
            milvus_store = MilvusDocumentStore(
                host=milvus_host,
                port=milvus_port,
            )
            if milvus_store.connect():
                print("✅ Milvus connected")
            else:
                print("⚠️  Milvus connection failed")
                milvus_store = None
        except Exception as e:
            import traceback
            print(f"⚠️  Milvus initialization failed: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            milvus_store = None
        
        # Initialize document pipeline (uses its own PipelineConfig)
        from .rag.pipeline import PipelineConfig as PipelineCfg
        pipeline_config = PipelineCfg()
        pipeline = DocumentPipeline(pipeline_config)
        
        # Initialize embedder FIRST (needed for both DocumentManager and Retriever)
        embedder = None
        try:
            from .rag.embedding import BGEM3Embedder
            embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
            embedding_device = os.getenv("RAG_EMBEDDING_DEVICE", "cuda")  # 默认使用 CUDA
            embedder = BGEM3Embedder(
                model_name=embedding_model,
                device=embedding_device,
            )
            print(f"✅ Embedding model loaded: {embedding_model} on {embedding_device}")
        except Exception as e:
            print(f"⚠️  Embedding model not available: {e}")
            print("   Document vectorization and search will fall back to BM25/keyword search")
        
        # Create DocumentManager WITH embedder
        doc_manager = DocumentManager(
            minio_client=minio_client,
            pg_store=pg_store,
            milvus_store=milvus_store,
            pipeline=pipeline,
            embedder=embedder,  # Now includes embedder for vectorization
        )
        
        # Register with RAG dependencies
        RAGDependencies.set_document_manager(doc_manager)
        
        # Initialize Retriever for search functionality
        try:
            from .rag.retrieval import HybridRetriever
            
            # Create retriever (reuse the same embedder)
            retriever = HybridRetriever(
                milvus_store=milvus_store,
                pg_store=pg_store,
                embedder=embedder,
            )
            RAGDependencies.set_retriever(retriever)
            print("✅ RAG Retriever ready")
            
        except Exception as e:
            print(f"⚠️  Retriever initialization failed: {e}")
            print("   Search functionality will be unavailable")
        
        _rag_initialized = True
        print("✅ RAG DocumentManager ready")
        
    except ImportError as e:
        print(f"⚠️  RAG module import failed: {e}")
        print("   RAG features will be unavailable")
    except Exception as e:
        print(f"⚠️  RAG initialization failed: {e}")
        print("   RAG features will be unavailable")


async def cleanup_rag_components():
    """Cleanup RAG components on shutdown"""
    global _rag_initialized
    
    if not _rag_initialized:
        return
    
    try:
        # Get document manager and cleanup
        doc_manager = RAGDependencies._document_manager
        if doc_manager:
            if doc_manager.minio:
                # MinIO client doesn't need explicit close
                pass
            if doc_manager.pg:
                await doc_manager.pg.disconnect()
                print("✅ RAG PostgreSQL store disconnected")
            if doc_manager.milvus:
                await doc_manager.milvus.disconnect()
                print("✅ Milvus disconnected")
    except Exception as e:
        print(f"⚠️  RAG cleanup error: {e}")


# Create a simple A2A server instance for uvicorn
_server = A2AServer(
    agent_id="dv-agent",
    agent_name="DV-Agent",
    description="DV-Agent A2A Server",
    version="0.1.0",
)

# Export the FastAPI app for uvicorn
app = _server.app

# Add exception handler for validation errors
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle 422 Validation Errors with detailed logging"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Log detailed validation error
    logger.error(f"Validation error for {request.method} {request.url.path}")
    logger.error(f"Request body: {await request.body()}")
    logger.error(f"Validation errors: {exc.errors()}")
    
    print(f"\n{'='*60}")
    print(f"❌ Validation Error: {request.method} {request.url.path}")
    print(f"{'='*60}")
    print(f"Errors:")
    for error in exc.errors():
        print(f"  - {error}")
    print(f"{'='*60}\n")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None
        },
    )

# Set lifespan handler
app.router.lifespan_context = lifespan

# Register additional routers
app.include_router(auth_router)
app.include_router(session_router)
app.include_router(rag_router, prefix="/api")  # /api/rag/...
app.include_router(ws_router)  # WebSocket at /ws
