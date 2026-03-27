"""
RAG API Module
RAG 服务 API 模块

提供文档管理和检索的 HTTP 接口。

端点：
- POST /documents/upload    - 上传文档
- GET  /documents/{id}      - 获取文档详情
- DELETE /documents/{id}    - 删除文档
- GET  /documents           - 列出文档
- POST /search              - 统一检索
- POST /search/documents    - 仅文档检索
- GET  /collections         - 列出集合
- POST /collections         - 创建集合
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth.dependencies import get_current_user
from ..auth.models import User

logger = logging.getLogger(__name__)

# ============ Request/Response Models ============

class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    document_id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    created_at: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentInfo(BaseModel):
    """文档信息"""
    document_id: str
    tenant_id: str
    collection_id: Optional[str] = None
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: list[DocumentInfo]
    total: int
    page: int
    page_size: int


class SearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., min_length=1, max_length=2000, description="查询文本")
    top_k: int = Field(default=10, ge=1, le=100, description="返回结果数量")
    
    # 来源配置
    include_documents: bool = Field(default=True, description="是否检索文档")
    collection_ids: Optional[list[str]] = Field(default=None, description="限定的集合ID列表")
    
    # 检索模式
    mode: str = Field(default="hybrid", description="检索模式: dense, sparse, bm25, hybrid")
    
    # 高级选项
    use_reranking: bool = Field(default=True, description="是否使用重排序")
    use_query_expansion: bool = Field(default=True, description="是否使用查询扩展")
    min_score: float = Field(default=0.1, ge=0.0, le=1.0, description="最小分数阈值")
    
    # 过滤器
    filters: Optional[dict[str, Any]] = Field(default=None, description="元数据过滤条件")


class SearchResultItem(BaseModel):
    """检索结果项"""
    chunk_id: str
    document_id: str
    content: str
    score: float
    chunk_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # 分数详情
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rerank_score: Optional[float] = None


class SearchResponse(BaseModel):
    """检索响应"""
    query: str
    results: list[SearchResultItem]
    total: int
    
    # 性能指标
    latency_ms: float
    from_cache: bool = False
    
    # 查询扩展信息
    expanded_queries: Optional[list[str]] = None


class CollectionInfo(BaseModel):
    """集合信息"""
    collection_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectionCreateRequest(BaseModel):
    """创建集合请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectionListResponse(BaseModel):
    """集合列表响应"""
    collections: list[CollectionInfo]
    total: int


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
    code: str = "UNKNOWN_ERROR"


# ============ Dependency Injection ============

class RAGDependencies:
    """RAG 依赖注入容器"""
    
    _document_manager = None
    _retriever = None
    _embedder = None
    
    @classmethod
    def set_document_manager(cls, manager):
        cls._document_manager = manager
    
    @classmethod
    def set_retriever(cls, retriever):
        cls._retriever = retriever
    
    @classmethod
    def set_embedder(cls, embedder):
        cls._embedder = embedder
    
    @classmethod
    def get_document_manager(cls):
        if cls._document_manager is None:
            raise HTTPException(
                status_code=503,
                detail="Document manager not initialized"
            )
        return cls._document_manager
    
    @classmethod
    def get_retriever(cls):
        if cls._retriever is None:
            raise HTTPException(
                status_code=503,
                detail="Retriever not initialized"
            )
        return cls._retriever


def get_document_manager():
    """获取文档管理器依赖"""
    return RAGDependencies.get_document_manager()


def get_retriever():
    """获取检索器依赖"""
    return RAGDependencies.get_retriever()


# ============ Router ============

router = APIRouter(prefix="/rag", tags=["RAG"])


# ============ Document Endpoints ============

@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    }
)
async def upload_document(
    file: UploadFile = File(...),
    collection_id: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None),  # JSON string
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    上传文档
    
    支持的文件类型：PDF, DOCX, TXT, MD, HTML
    
    - **file**: 上传的文件
    - **collection_id**: 集合 ID（可选）
    - **metadata**: 元数据 JSON 字符串（可选）
    """
    import json
    
    try:
        tenant_id = str(current_user.id)
        
        # 解析元数据
        extra_metadata = {}
        if metadata:
            try:
                extra_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid metadata JSON")
        
        # 读取文件内容
        content = await file.read()
        
        # 检查文件大小 (默认限制 50MB)
        max_size = 50 * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {max_size // (1024*1024)}MB"
            )
        
        # 上传处理
        result = await document_manager.upload_document(
            tenant_id=tenant_id,
            filename=file.filename,
            content=content,
            collection_id=collection_id,
            metadata=extra_metadata,
        )
        
        # 检查上传是否成功
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Upload failed")
            )
        
        # 获取文档详情
        doc_id = result.get("doc_id")
        doc_info = await document_manager.get_document(doc_id, tenant_id)
        
        return DocumentUploadResponse(
            document_id=doc_id,
            filename=doc_info.get("filename", file.filename) if doc_info else file.filename,
            file_type=doc_info.get("file_type", "") if doc_info else "",
            file_size=len(content),
            chunk_count=0,  # 异步处理时还未生成分块
            status=result.get("status", "queued"),
            created_at=doc_info.get("created_at") if doc_info else None,
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        logger.error(f"Document upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get(
    "/documents/{document_id}",
    response_model=DocumentInfo,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
    }
)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    获取文档详情
    
    - **document_id**: 文档 ID
    """
    try:
        tenant_id = str(current_user.id)
        doc = await document_manager.get_document(
            document_id=document_id,
            tenant_id=tenant_id,
        )
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return DocumentInfo(
            document_id=doc.document_id,
            tenant_id=doc.tenant_id,
            collection_id=doc.collection_id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            chunk_count=doc.chunk_count,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            metadata=doc.metadata or {},
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/documents/{document_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
    }
)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    删除文档
    
    - **document_id**: 文档 ID
    """
    try:
        tenant_id = str(current_user.id)
        
        # 验证 document_id 是否有效
        if not document_id or document_id == "undefined":
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        success = await document_manager.delete_document(
            doc_id=document_id,
            tenant_id=tenant_id,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {"status": "deleted", "document_id": document_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/documents",
    response_model=DocumentListResponse,
)
async def list_documents(
    collection_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    列出文档
    
    - **collection_id**: 集合 ID（可选）
    - **page**: 页码
    - **page_size**: 每页数量
    """
    try:
        tenant_id = str(current_user.id)
        offset = (page - 1) * page_size
        
        docs, total = await document_manager.list_documents(
            tenant_id=tenant_id,
            collection_id=collection_id,
            offset=offset,
            limit=page_size,
        )
        
        def parse_metadata(meta):
            """解析 metadata，处理字符串或字典"""
            if meta is None:
                return {}
            if isinstance(meta, dict):
                return meta
            if isinstance(meta, str):
                try:
                    import json
                    return json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    return {}
            return {}
        
        return DocumentListResponse(
            documents=[
                DocumentInfo(
                    document_id=doc.get("doc_id", ""),
                    tenant_id=doc.get("tenant_id", ""),
                    collection_id=doc.get("collection_id"),
                    filename=doc.get("filename", ""),
                    file_type=doc.get("file_type", ""),
                    file_size=doc.get("file_size", 0),
                    chunk_count=doc.get("chunk_count", 0),
                    status=doc.get("status", "pending"),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                    metadata=parse_metadata(doc.get("metadata")),
                )
                for doc in docs
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
        
    except Exception as e:
        logger.error(f"List documents failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ Search Endpoints ============

@router.post(
    "/search",
    response_model=SearchResponse,
)
async def search_documents(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    retriever = Depends(get_retriever),
):
    """
    检索文档
    
    支持多种检索模式：
    - **dense**: 仅稠密向量检索（语义）
    - **sparse**: 仅稀疏向量检索（词汇）
    - **bm25**: 仅 BM25 检索（关键词）
    - **hybrid**: 混合检索（默认）
    """
    from .retrieval import RetrievalQuery, SearchMode
    
    try:
        logger.info(f"[SEARCH] Received request: query={request.query[:50]}, mode={request.mode}, top_k={request.top_k}")
        tenant_id = str(current_user.id)
        
        # 构建查询
        mode_map = {
            "dense": SearchMode.DENSE_ONLY,
            "sparse": SearchMode.SPARSE_ONLY,
            "bm25": SearchMode.BM25_ONLY,
            "hybrid": SearchMode.HYBRID_ALL,  # 默认使用全路召回
        }
        
        query = RetrievalQuery(
            query=request.query,
            tenant_id=tenant_id,
            collection_id=request.collection_ids[0] if request.collection_ids else None,
            top_k=request.top_k,
            mode=mode_map.get(request.mode, SearchMode.HYBRID_ALL),
            rerank=request.use_reranking,
            expand_queries=request.use_query_expansion,
            filters=request.filters,
        )
        
        # 执行检索
        response = await retriever.retrieve(query)
        
        # 构建响应
        results = [
            SearchResultItem(
                chunk_id=str(r.chunk_id),  # 转换 UUID 为字符串
                document_id=str(r.doc_id),  # 转换 UUID 为字符串
                content=r.content,
                score=r.score,
                chunk_index=0,  # TODO: 需要从 metadata 中获取
                metadata=r.metadata,
                dense_score=r.source_scores.get('dense', 0.0),
                sparse_score=r.source_scores.get('sparse', 0.0),
                bm25_score=r.source_scores.get('bm25', 0.0),
                rerank_score=r.source_scores.get('rerank', 0.0),
            )
            for r in response.results
        ]
        
        return SearchResponse(
            query=request.query,
            results=results,
            total=len(results),
            latency_ms=response.latency_ms,
            from_cache=False,  # TODO: RetrievalResponse 没有 from_cache 字段
            expanded_queries=response.expanded_queries,
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/search/simple",
    response_model=SearchResponse,
)
async def simple_search(
    query: str = Query(..., min_length=1, max_length=2000),
    collection_id: Optional[str] = Query(default=None),
    top_k: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    retriever = Depends(get_retriever),
):
    """
    简单检索（GET 请求）
    
    便捷的检索接口，使用默认配置。
    """
    try:
        tenant_id = str(current_user.id)
        results_list = await retriever.simple_search(
            query=query,
            tenant_id=tenant_id,
            collection_id=collection_id,
            top_k=top_k,
        )
        
        # simple_search 返回 List[RetrievalResult]，不是 RetrievalResponse
        results = [
            SearchResultItem(
                chunk_id=str(r.chunk_id),
                document_id=str(r.doc_id),
                content=r.content,
                score=r.score,
                chunk_index=0,
                metadata=r.metadata,
                dense_score=r.source_scores.get('dense', 0.0),
                sparse_score=r.source_scores.get('sparse', 0.0),
                bm25_score=r.source_scores.get('bm25', 0.0),
                rerank_score=r.source_scores.get('rerank', 0.0),
            )
            for r in results_list
        ]
        
        return SearchResponse(
            query=query,
            results=results,
            total=len(results),
            latency_ms=0.0,  # simple_search 不返回 latency
            from_cache=False,
        )
        
    except Exception as e:
        logger.error(f"Simple search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ Collection Endpoints ============

@router.get(
    "/collections",
    response_model=CollectionListResponse,
)
async def list_collections(
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    列出当前用户的集合
    """
    try:
        tenant_id = str(current_user.id)
        collections = await document_manager.list_collections(tenant_id=tenant_id)
        
        return CollectionListResponse(
            collections=[
                CollectionInfo(
                    collection_id=c.collection_id,
                    tenant_id=c.tenant_id,
                    name=c.name,
                    description=c.description,
                    document_count=c.document_count,
                    chunk_count=c.chunk_count,
                    created_at=c.created_at,
                    metadata=c.metadata or {},
                )
                for c in collections
            ],
            total=len(collections),
        )
        
    except Exception as e:
        logger.error(f"List collections failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/collections",
    response_model=CollectionInfo,
)
async def create_collection(
    request: CollectionCreateRequest,
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    创建集合
    
    - **name**: 集合名称
    - **description**: 集合描述（可选）
    - **metadata**: 元数据（可选）
    """
    try:
        tenant_id = str(current_user.id)
        collection = await document_manager.create_collection(
            tenant_id=tenant_id,
            name=request.name,
            description=request.description,
            metadata=request.metadata,
        )
        
        return CollectionInfo(
            collection_id=collection.collection_id,
            tenant_id=collection.tenant_id,
            name=collection.name,
            description=collection.description,
            document_count=0,
            chunk_count=0,
            created_at=collection.created_at,
            metadata=collection.metadata or {},
        )
        
    except Exception as e:
        logger.error(f"Create collection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/collections/{collection_id}",
)
async def delete_collection(
    collection_id: str,
    delete_documents: bool = Query(default=False, description="是否同时删除集合中的文档"),
    current_user: User = Depends(get_current_user),
    document_manager = Depends(get_document_manager),
):
    """
    删除集合
    
    - **collection_id**: 集合 ID
    - **delete_documents**: 是否同时删除集合中的文档
    """
    try:
        tenant_id = str(current_user.id)
        success = await document_manager.delete_collection(
            collection_id=collection_id,
            tenant_id=tenant_id,
            delete_documents=delete_documents,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        return {"status": "deleted", "collection_id": collection_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete collection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ Health Check ============

@router.get("/health")
async def health_check():
    """RAG 服务健康检查"""
    return {
        "status": "healthy",
        "service": "rag",
        "timestamp": datetime.utcnow().isoformat(),
    }


