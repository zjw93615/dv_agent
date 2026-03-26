"""
RAG System Usage Example
RAG 系统使用示例

展示如何初始化和使用 RAG 系统的完整流程。
"""

import asyncio
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def initialize_rag_system():
    """
    初始化 RAG 系统
    
    Returns:
        tuple: (document_manager, retriever)
    """
    from dv_agent.rag import get_rag_config
    from dv_agent.rag.embedding import BGEM3Embedder
    from dv_agent.rag.store import (
        DocumentManager,
        MinIOClient,
        PostgresDocumentStore,
        MilvusDocumentStore,
    )
    from dv_agent.rag.retrieval import HybridRetriever
    
    # 1. 加载配置
    config = get_rag_config()
    logger.info("Configuration loaded")
    
    # 2. 初始化嵌入服务
    embedder = BGEM3Embedder(
        model_path=config.embedding.model_path,
        device=config.embedding.device,
    )
    await embedder.initialize()
    logger.info("Embedder initialized")
    
    # 3. 初始化存储服务
    minio_client = MinIOClient(
        endpoint=config.minio.endpoint,
        access_key=config.minio.access_key,
        secret_key=config.minio.secret_key,
    )
    
    pg_store = PostgresDocumentStore(
        connection_string=config.postgres.connection_string,
    )
    await pg_store.initialize()
    
    milvus_store = MilvusDocumentStore(
        host=config.milvus.host,
        port=config.milvus.port,
    )
    await milvus_store.initialize()
    
    logger.info("Storage services initialized")
    
    # 4. 创建文档管理器
    document_manager = DocumentManager(
        embedder=embedder,
        minio_client=minio_client,
        pg_store=pg_store,
        milvus_store=milvus_store,
        config=config,
    )
    logger.info("Document manager created")
    
    # 5. 创建检索器
    retriever = HybridRetriever(
        embedder=embedder,
        milvus_store=milvus_store,
        pg_store=pg_store,
        config=config,
    )
    logger.info("Retriever created")
    
    return document_manager, retriever


async def upload_document_example(document_manager):
    """
    文档上传示例
    
    Args:
        document_manager: 文档管理器
    """
    logger.info("=== Document Upload Example ===")
    
    # 示例文档内容
    sample_content = """
    # 人工智能简介
    
    人工智能（Artificial Intelligence, AI）是计算机科学的一个重要分支，
    致力于研究和开发能够模拟、延伸和扩展人类智能的理论、方法、技术及应用系统。
    
    ## 主要领域
    
    1. **机器学习**：使计算机能够从数据中学习
    2. **深度学习**：使用多层神经网络
    3. **自然语言处理**：理解和生成人类语言
    4. **计算机视觉**：理解图像和视频
    
    ## 应用场景
    
    - 智能助手（如 Siri、Alexa）
    - 推荐系统（如 Netflix、YouTube）
    - 自动驾驶
    - 医疗诊断
    """
    
    # 上传文档
    result = await document_manager.upload_document(
        tenant_id="demo_tenant",
        filename="ai_introduction.md",
        content=sample_content.encode('utf-8'),
        collection_id="knowledge_base",
        metadata={
            "author": "Demo",
            "category": "AI",
            "tags": ["人工智能", "机器学习", "深度学习"],
        }
    )
    
    logger.info(f"Document uploaded: {result.document_id}")
    logger.info(f"  Filename: {result.filename}")
    logger.info(f"  Chunks: {result.chunk_count}")
    logger.info(f"  Status: {result.status}")
    
    return result.document_id


async def search_example(retriever):
    """
    检索示例
    
    Args:
        retriever: 检索器
    """
    logger.info("\n=== Search Example ===")
    
    # 简单检索
    query = "什么是深度学习？"
    logger.info(f"Query: {query}")
    
    response = await retriever.simple_search(
        query=query,
        tenant_id="demo_tenant",
        collection_id="knowledge_base",
        top_k=5,
    )
    
    logger.info(f"Found {len(response.results)} results in {response.latency_ms:.1f}ms")
    
    for i, result in enumerate(response.results, 1):
        logger.info(f"\n  [{i}] Score: {result.final_score:.4f}")
        logger.info(f"      Content: {result.content[:100]}...")
        if result.dense_score:
            logger.info(f"      Dense: {result.dense_score:.4f}")
        if result.sparse_score:
            logger.info(f"      Sparse: {result.sparse_score:.4f}")
        if result.rerank_score:
            logger.info(f"      Rerank: {result.rerank_score:.4f}")


async def advanced_search_example(retriever):
    """
    高级检索示例（使用查询扩展和重排序）
    
    Args:
        retriever: 检索器
    """
    from dv_agent.rag.retrieval import RetrievalQuery, SearchMode
    
    logger.info("\n=== Advanced Search Example ===")
    
    query = RetrievalQuery(
        query="AI 在医疗领域的应用有哪些？",
        tenant_id="demo_tenant",
        collection_id="knowledge_base",
        top_k=10,
        mode=SearchMode.HYBRID,
        use_query_expansion=True,
        use_reranking=True,
        expansion_count=3,
    )
    
    logger.info(f"Query: {query.query}")
    logger.info(f"Mode: {query.mode}")
    logger.info(f"Query Expansion: {query.use_query_expansion}")
    logger.info(f"Reranking: {query.use_reranking}")
    
    response = await retriever.search(query)
    
    logger.info(f"\nResults: {len(response.results)}")
    logger.info(f"Latency: {response.latency_ms:.1f}ms")
    logger.info(f"From Cache: {response.from_cache}")
    
    if response.expanded_queries:
        logger.info(f"Expanded Queries: {response.expanded_queries}")
    
    for i, result in enumerate(response.results[:3], 1):
        logger.info(f"\n  [{i}] {result.content[:150]}...")


async def unified_retrieval_example():
    """
    统一检索示例（同时检索记忆和文档）
    """
    from dv_agent.memory.retrieval import UnifiedRetriever, UnifiedQuery, SourceType
    
    logger.info("\n=== Unified Retrieval Example ===")
    
    # 注意：这需要完整初始化 memory 和 rag 系统
    # 这里只展示 API 用法
    
    query = UnifiedQuery(
        user_id="user_001",
        tenant_id="demo_tenant",
        query="告诉我关于机器学习的内容",
        top_k=10,
        sources=[SourceType.MEMORY, SourceType.DOCUMENT],
        memory_weight=0.3,
        document_weight=0.7,
        use_reranking=True,
    )
    
    logger.info(f"Query: {query.query}")
    logger.info(f"Sources: {[s.value for s in query.sources]}")
    logger.info(f"Memory Weight: {query.memory_weight}")
    logger.info(f"Document Weight: {query.document_weight}")
    
    # 实际使用时：
    # retriever = UnifiedRetriever(...)
    # response = await retriever.retrieve(query)
    # context = response.to_context(max_tokens=4000)


async def fastapi_integration_example():
    """
    FastAPI 集成示例
    """
    logger.info("\n=== FastAPI Integration Example ===")
    
    code_example = '''
from fastapi import FastAPI
from dv_agent.rag import get_rag_config
from dv_agent.rag.api import router as rag_router, RAGDependencies

app = FastAPI(title="DV-Agent RAG Service")

@app.on_event("startup")
async def startup():
    # 初始化 RAG 组件
    config = get_rag_config()
    
    # 初始化各组件...
    document_manager = ...
    retriever = ...
    
    # 注入依赖
    RAGDependencies.set_document_manager(document_manager)
    RAGDependencies.set_retriever(retriever)

# 注册 RAG 路由
app.include_router(rag_router)

# API 端点：
# POST /rag/documents/upload     - 上传文档
# GET  /rag/documents/{id}       - 获取文档
# DELETE /rag/documents/{id}     - 删除文档
# GET  /rag/documents            - 列出文档
# POST /rag/search               - 高级检索
# GET  /rag/search/simple        - 简单检索
# GET  /rag/collections          - 列出集合
# POST /rag/collections          - 创建集合
'''
    
    logger.info("FastAPI integration code:")
    for line in code_example.strip().split('\n'):
        logger.info(f"  {line}")


async def main():
    """
    主函数
    """
    logger.info("DV-Agent RAG System Demo")
    logger.info("=" * 50)
    
    try:
        # 初始化系统
        # document_manager, retriever = await initialize_rag_system()
        
        # 文档上传示例
        # await upload_document_example(document_manager)
        
        # 检索示例
        # await search_example(retriever)
        
        # 高级检索示例
        # await advanced_search_example(retriever)
        
        # 统一检索示例
        await unified_retrieval_example()
        
        # FastAPI 集成示例
        await fastapi_integration_example()
        
        logger.info("\n" + "=" * 50)
        logger.info("Demo completed!")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
