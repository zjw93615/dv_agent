"""
Memory API Router
记忆系统 API 端点

提供记忆系统的 REST API 接口。
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

# 假设这些依赖项存在于项目中
# 实际使用时需要根据项目结构调整导入

router = APIRouter(prefix="/api/v1", tags=["memory"])


# ========== 请求/响应模型 ==========

class MemoryResponse(BaseModel):
    """记忆响应"""
    id: str
    user_id: str
    memory_type: str
    content: str
    confidence: float
    importance: float
    access_count: int
    created_at: str
    updated_at: str
    metadata: dict = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    """记忆列表响应"""
    memories: list[MemoryResponse]
    total: int
    offset: int
    limit: int


class MemoryUpdateRequest(BaseModel):
    """记忆更新请求"""
    content: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    permanent: Optional[bool] = None


class MemorySearchRequest(BaseModel):
    """记忆检索请求"""
    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    memory_types: Optional[list[str]] = None
    use_reranker: bool = True


class MemorySearchResult(BaseModel):
    """检索结果项"""
    memory: MemoryResponse
    score: float


class MemorySearchResponse(BaseModel):
    """检索响应"""
    results: list[MemorySearchResult]
    query: str
    latency_ms: float


class SummaryResponse(BaseModel):
    """会话摘要响应"""
    session_id: str
    summary: Optional[str]
    message_count: int


class MaintenanceResponse(BaseModel):
    """维护任务响应"""
    importance_update: Optional[dict] = None
    forget_cycle: Optional[dict] = None
    consistency_check: Optional[dict] = None


# ========== 辅助函数 ==========

def memory_to_response(memory) -> MemoryResponse:
    """转换 Memory 对象为响应模型"""
    return MemoryResponse(
        id=str(memory.id),
        user_id=memory.user_id,
        memory_type=memory.memory_type.value,
        content=memory.content,
        confidence=memory.confidence,
        importance=memory.importance,
        access_count=memory.access_count,
        created_at=memory.created_at.isoformat(),
        updated_at=memory.updated_at.isoformat(),
        metadata=memory.metadata,
    )


# ========== 会话摘要端点 ==========

@router.get("/session/{session_id}/summary", response_model=SummaryResponse)
async def get_session_summary(
    session_id: str,
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    获取会话摘要
    
    返回会话的压缩摘要和消息统计。
    """
    # 注：实际实现需要注入 MemoryManager 依赖
    # summary = await memory_manager.get_summary(session_id)
    # messages = await memory_manager.get_short_term_messages(session_id)
    
    # 示例返回
    return SummaryResponse(
        session_id=session_id,
        summary=None,  # summary,
        message_count=0,  # len(messages),
    )


# ========== 用户记忆端点 ==========

@router.get("/memory/user/{user_id}", response_model=MemoryListResponse)
async def get_user_memories(
    user_id: str,
    memory_type: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    获取用户的记忆列表
    
    支持按类型过滤和分页。
    """
    # 注：实际实现需要注入依赖
    # type_filter = MemoryType(memory_type) if memory_type else None
    # memories = await memory_manager.get_user_memories(
    #     user_id=user_id,
    #     memory_type=type_filter,
    #     limit=limit,
    #     offset=offset,
    # )
    
    return MemoryListResponse(
        memories=[],  # [memory_to_response(m) for m in memories],
        total=0,
        offset=offset,
        limit=limit,
    )


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    hard_delete: bool = Query(default=False),
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    删除记忆
    
    Args:
        memory_id: 记忆 ID
        hard_delete: 是否硬删除（默认软删除）
    """
    try:
        memory_uuid = UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory ID format")
    
    # success = await memory_manager.delete_memory(memory_uuid, hard_delete)
    success = True  # 示例
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"success": True, "memory_id": memory_id}


@router.patch("/memory/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    更新记忆
    
    可以更新内容、重要性或标记为永久。
    """
    try:
        memory_uuid = UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory ID format")
    
    # updated = await memory_manager.update_memory(
    #     memory_id=memory_uuid,
    #     content=request.content,
    #     importance=request.importance,
    #     permanent=request.permanent,
    # )
    
    # if not updated:
    #     raise HTTPException(status_code=404, detail="Memory not found")
    
    # return memory_to_response(updated)
    
    raise HTTPException(status_code=501, detail="Not implemented")


# ========== 记忆检索端点 ==========

@router.post("/memory/search", response_model=MemorySearchResponse)
async def search_memories(
    request: MemorySearchRequest,
    user_id: str = Query(...),
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    检索用户记忆
    
    支持多路召回和 Cross-Encoder 重排序。
    """
    import time
    start_time = time.time()
    
    # type_filters = None
    # if request.memory_types:
    #     type_filters = [MemoryType(t) for t in request.memory_types]
    
    # results = await memory_manager.retrieve(
    #     user_id=user_id,
    #     query=request.query,
    #     top_k=request.top_k,
    #     memory_types=type_filters,
    #     use_reranker=request.use_reranker,
    # )
    
    latency_ms = (time.time() - start_time) * 1000
    
    return MemorySearchResponse(
        results=[],  # [MemorySearchResult(memory=memory_to_response(r.memory), score=r.final_score) for r in results],
        query=request.query,
        latency_ms=latency_ms,
    )


# ========== 维护端点 ==========

@router.post("/memory/maintenance", response_model=MaintenanceResponse)
async def run_maintenance(
    user_id: Optional[str] = None,
    # memory_manager: MemoryManager = Depends(get_memory_manager),
):
    """
    运行记忆维护任务
    
    包括重要性更新、遗忘周期和一致性检查。
    
    生产环境建议限制调用频率。
    """
    # stats = await memory_manager.run_maintenance(user_id)
    
    return MaintenanceResponse(
        importance_update={},  # stats.get("importance_update"),
        forget_cycle={},  # stats.get("forget"),
        consistency_check={},
    )


# ========== 工厂函数（用于依赖注入） ==========

def create_memory_router(memory_manager) -> APIRouter:
    """
    创建带有依赖注入的记忆路由
    
    Args:
        memory_manager: MemoryManager 实例
        
    Returns:
        配置好的 APIRouter
    """
    from fastapi import APIRouter
    
    router = APIRouter(prefix="/api/v1", tags=["memory"])
    
    @router.get("/session/{session_id}/summary", response_model=SummaryResponse)
    async def get_session_summary(session_id: str):
        summary = await memory_manager.get_summary(session_id)
        messages = await memory_manager.get_short_term_messages(session_id)
        
        return SummaryResponse(
            session_id=session_id,
            summary=summary,
            message_count=len(messages),
        )
    
    @router.get("/memory/user/{user_id}", response_model=MemoryListResponse)
    async def get_user_memories(
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        from ..models import MemoryType
        
        type_filter = MemoryType(memory_type) if memory_type else None
        memories = await memory_manager.get_user_memories(
            user_id=user_id,
            memory_type=type_filter,
            limit=limit,
            offset=offset,
        )
        
        return MemoryListResponse(
            memories=[memory_to_response(m) for m in memories],
            total=len(memories),  # 简化处理，实际应查询总数
            offset=offset,
            limit=limit,
        )
    
    @router.delete("/memory/{memory_id}")
    async def delete_memory(
        memory_id: str,
        hard_delete: bool = Query(default=False),
    ):
        try:
            memory_uuid = UUID(memory_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid memory ID format")
        
        success = await memory_manager.delete_memory(memory_uuid, hard_delete)
        
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return {"success": True, "memory_id": memory_id}
    
    @router.patch("/memory/{memory_id}", response_model=MemoryResponse)
    async def update_memory(
        memory_id: str,
        request: MemoryUpdateRequest,
    ):
        try:
            memory_uuid = UUID(memory_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid memory ID format")
        
        updated = await memory_manager.update_memory(
            memory_id=memory_uuid,
            content=request.content,
            importance=request.importance,
            permanent=request.permanent,
        )
        
        if not updated:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return memory_to_response(updated)
    
    @router.post("/memory/search", response_model=MemorySearchResponse)
    async def search_memories(
        request: MemorySearchRequest,
        user_id: str = Query(...),
    ):
        import time
        from ..models import MemoryType
        
        start_time = time.time()
        
        type_filters = None
        if request.memory_types:
            type_filters = [MemoryType(t) for t in request.memory_types]
        
        results = await memory_manager.retrieve(
            user_id=user_id,
            query=request.query,
            top_k=request.top_k,
            memory_types=type_filters,
            use_reranker=request.use_reranker,
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return MemorySearchResponse(
            results=[
                MemorySearchResult(
                    memory=memory_to_response(r.memory),
                    score=r.final_score,
                )
                for r in results
            ],
            query=request.query,
            latency_ms=latency_ms,
        )
    
    @router.post("/memory/maintenance", response_model=MaintenanceResponse)
    async def run_maintenance(user_id: Optional[str] = None):
        stats = await memory_manager.run_maintenance(user_id)
        
        return MaintenanceResponse(
            importance_update=stats.get("importance_update"),
            forget_cycle=stats.get("forget"),
        )
    
    return router
