"""
Document Manager
文档管理器

提供文档的完整生命周期管理，包括上传、处理、索引和删除。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingTask:
    """处理任务"""
    
    task_id: str
    doc_id: str
    tenant_id: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def is_complete(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)


@dataclass
class TenantQuota:
    """租户配额"""
    
    max_documents: int = 10000
    max_storage_bytes: int = 10 * 1024 * 1024 * 1024  # 10GB
    max_chunks_per_doc: int = 1000
    
    current_documents: int = 0
    current_storage_bytes: int = 0
    
    def can_upload(self, file_size: int) -> bool:
        """检查是否可以上传"""
        if self.current_documents >= self.max_documents:
            return False
        if self.current_storage_bytes + file_size > self.max_storage_bytes:
            return False
        return True
    
    @property
    def usage_percent(self) -> float:
        """使用率百分比"""
        doc_usage = self.current_documents / self.max_documents * 100
        storage_usage = self.current_storage_bytes / self.max_storage_bytes * 100
        return max(doc_usage, storage_usage)


class DocumentManager:
    """
    文档管理器
    
    整合所有存储组件，提供统一的文档管理接口。
    
    功能：
    - 文档上传和处理
    - 向量索引管理
    - 租户隔离
    - 配额检查
    - 异步任务队列
    """
    
    def __init__(
        self,
        minio_client: Any = None,
        pg_store: Any = None,
        milvus_store: Any = None,
        pipeline: Any = None,
        embedder: Any = None,
        tenant_quotas: Optional[dict[str, TenantQuota]] = None,
    ):
        """
        初始化管理器
        
        Args:
            minio_client: MinIO 客户端
            pg_store: PostgreSQL 存储
            milvus_store: Milvus 存储
            pipeline: 文档处理流水线
            embedder: 向量化服务
            tenant_quotas: 租户配额配置
        """
        self.minio = minio_client
        self.pg = pg_store
        self.milvus = milvus_store
        self.pipeline = pipeline
        self.embedder = embedder
        
        # 租户配额
        self._quotas = tenant_quotas or {}
        
        # 异步任务队列
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._tasks: dict[str, ProcessingTask] = {}
        self._worker_running = False
    
    # ==================== 配额管理 ====================
    
    def get_quota(self, tenant_id: str) -> TenantQuota:
        """
        获取租户配额
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            配额对象
        """
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = TenantQuota()
        return self._quotas[tenant_id]
    
    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        """
        设置租户配额
        
        Args:
            tenant_id: 租户ID
            quota: 配额对象
        """
        self._quotas[tenant_id] = quota
    
    async def refresh_quota_usage(self, tenant_id: str) -> TenantQuota:
        """
        刷新租户配额使用情况
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            更新后的配额
        """
        quota = self.get_quota(tenant_id)
        
        if self.pg:
            # 统计文档数量
            quota.current_documents = await self.pg.count_documents(tenant_id)
            
            # TODO: 统计存储使用量
        
        return quota
    
    def check_quota(self, tenant_id: str, file_size: int) -> tuple[bool, str]:
        """
        检查配额
        
        Args:
            tenant_id: 租户ID
            file_size: 文件大小
            
        Returns:
            (是否允许, 原因)
        """
        quota = self.get_quota(tenant_id)
        
        if quota.current_documents >= quota.max_documents:
            return False, f"Document limit reached ({quota.max_documents})"
        
        if quota.current_storage_bytes + file_size > quota.max_storage_bytes:
            return False, "Storage quota exceeded"
        
        return True, ""
    
    # ==================== 文档操作 ====================
    
    async def upload_document(
        self,
        tenant_id: str,
        filename: str,
        content: bytes,
        collection_id: str = "",
        metadata: Optional[dict] = None,
        process_async: bool = True,
    ) -> dict:
        """
        上传文档
        
        Args:
            tenant_id: 租户ID
            filename: 文件名
            content: 文件内容
            collection_id: 集合ID
            metadata: 元数据
            process_async: 是否异步处理
            
        Returns:
            上传结果
        """
        # 配额检查
        allowed, reason = self.check_quota(tenant_id, len(content))
        if not allowed:
            return {
                "success": False,
                "error": reason,
            }
        
        # 生成存储路径
        import hashlib
        content_hash = hashlib.sha256(content).hexdigest()
        storage_path = f"{tenant_id}/{collection_id or 'default'}/{content_hash[:8]}_{filename}"
        
        # 上传到 MinIO
        if self.minio:
            obj_info = self.minio.upload_bytes(
                content,
                storage_path,
                metadata={"tenant_id": tenant_id, "filename": filename},
            )
            if not obj_info:
                return {
                    "success": False,
                    "error": "Failed to upload file to storage",
                }
        
        # 生成文档ID
        doc_id = hashlib.md5(
            f"{tenant_id}:{filename}:{content_hash}".encode()
        ).hexdigest()
        
        # 创建文档记录
        if self.pg:
            from .pg_document import DocumentStatus
            
            # 检测文件类型
            file_type = Path(filename).suffix.lstrip('.').lower()
            
            doc_record = await self.pg.create_document(
                doc_id=doc_id,
                tenant_id=tenant_id,
                filename=filename,
                file_type=file_type,
                file_size=len(content),
                content_hash=content_hash,
                storage_path=storage_path,
                collection_id=collection_id,
                title=metadata.get("title", "") if metadata else "",
                metadata=metadata,
            )
            
            if not doc_record:
                return {
                    "success": False,
                    "error": "Failed to create document record",
                }
        
        # 处理文档
        if process_async:
            # 加入异步队列
            task = await self._enqueue_task(doc_id, tenant_id, content)
            return {
                "success": True,
                "doc_id": doc_id,
                "task_id": task.task_id,
                "status": "queued",
            }
        else:
            # 同步处理
            result = await self._process_document(doc_id, tenant_id, content)
            return {
                "success": result,
                "doc_id": doc_id,
                "status": "completed" if result else "failed",
            }
    
    async def get_document(
        self,
        doc_id: str,
        tenant_id: str,
    ) -> Optional[dict]:
        """
        获取文档信息
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            
        Returns:
            文档信息
        """
        if self.pg:
            return await self.pg.get_document(doc_id, tenant_id)
        return None
    
    async def delete_document(
        self,
        doc_id: str,
        tenant_id: str,
    ) -> bool:
        """
        删除文档
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            
        Returns:
            是否成功
        """
        # 获取文档信息
        doc = await self.get_document(doc_id, tenant_id)
        if not doc:
            return False
        
        # 删除向量
        if self.milvus:
            self.milvus.delete_vectors_by_doc(doc_id)
        
        # 删除块
        if self.pg:
            await self.pg.delete_chunks(doc_id)
        
        # 删除文档记录
        if self.pg:
            await self.pg.delete_document(doc_id, tenant_id)
        
        # 删除文件
        if self.minio and doc.get("storage_path"):
            self.minio.delete_object(doc["storage_path"])
        
        return True
    
    async def list_documents(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        """
        列出文档
        
        Args:
            tenant_id: 租户ID
            collection_id: 集合ID
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            文档列表
        """
        if self.pg:
            return await self.pg.list_documents(
                tenant_id, collection_id, offset=offset, limit=limit
            )
        return []
    
    # ==================== 文档处理 ====================
    
    async def _process_document(
        self,
        doc_id: str,
        tenant_id: str,
        content: bytes,
    ) -> bool:
        """
        处理文档（内部方法）
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            content: 文档内容
            
        Returns:
            是否成功
        """
        from .pg_document import DocumentStatus
        
        try:
            # 更新状态为处理中
            if self.pg:
                await self.pg.update_document_status(
                    doc_id, DocumentStatus.PROCESSING
                )
            
            # 获取文档信息
            doc = await self.get_document(doc_id, tenant_id)
            if not doc:
                return False
            
            # 文档处理流水线
            if self.pipeline:
                result = self.pipeline.process(
                    content=content,
                    filename=doc["filename"],
                    tenant_id=tenant_id,
                    collection_id=doc.get("collection_id", ""),
                )
                
                if not result.success:
                    if self.pg:
                        await self.pg.update_document_status(
                            doc_id, DocumentStatus.FAILED,
                            error_message="; ".join(result.errors)
                        )
                    return False
                
                chunks = result.chunks
            else:
                return False
            
            # 存储块
            if self.pg and chunks:
                chunk_data = [
                    {
                        "chunk_index": c.index,
                        "content": c.content,
                        "page_number": c.page_number,
                        "metadata": c.metadata,
                    }
                    for c in chunks
                ]
                await self.pg.create_chunks(doc_id, chunk_data)
            
            # 向量化
            if self.embedder and chunks:
                embeddings = self.embedder.embed_documents(
                    [c.content for c in chunks]
                )
                
                # 存储向量
                if self.milvus:
                    # 获取块ID（从数据库）
                    db_chunks = await self.pg.get_chunks(doc_id)
                    chunk_ids = [c["id"] for c in db_chunks]
                    doc_ids = [doc_id] * len(chunks)
                    tenant_ids = [tenant_id] * len(chunks)
                    
                    dense_vectors = [e.dense_embedding for e in embeddings]
                    sparse_vectors = [
                        e.sparse_embedding.to_dict() 
                        if e.sparse_embedding else {}
                        for e in embeddings
                    ]
                    
                    self.milvus.insert_vectors(
                        chunk_ids, doc_ids, dense_vectors, sparse_vectors, tenant_ids
                    )
            
            # 更新状态为完成
            if self.pg:
                await self.pg.update_document_status(
                    doc_id, DocumentStatus.COMPLETED
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            if self.pg:
                await self.pg.update_document_status(
                    doc_id, DocumentStatus.FAILED,
                    error_message=str(e)
                )
            return False
    
    # ==================== 异步任务队列 ====================
    
    async def _enqueue_task(
        self,
        doc_id: str,
        tenant_id: str,
        content: bytes,
    ) -> ProcessingTask:
        """
        将任务加入队列
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            content: 文档内容
            
        Returns:
            任务对象
        """
        import uuid
        
        task_id = str(uuid.uuid4())
        task = ProcessingTask(
            task_id=task_id,
            doc_id=doc_id,
            tenant_id=tenant_id,
        )
        
        self._tasks[task_id] = task
        await self._task_queue.put((task, content))
        
        # 确保 worker 在运行
        if not self._worker_running:
            asyncio.create_task(self._run_worker())
        
        return task
    
    async def _run_worker(self):
        """运行任务处理 worker"""
        self._worker_running = True
        
        while True:
            try:
                # 获取任务（带超时）
                try:
                    task, content = await asyncio.wait_for(
                        self._task_queue.get(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    # 队列空闲，退出 worker
                    if self._task_queue.empty():
                        break
                    continue
                
                # 更新任务状态
                task.status = TaskStatus.PROCESSING
                task.started_at = datetime.utcnow()
                
                # 处理任务
                success = await self._process_document(
                    task.doc_id, task.tenant_id, content
                )
                
                # 更新任务状态
                task.completed_at = datetime.utcnow()
                task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                
            except Exception as e:
                logger.error(f"Worker error: {e}")
                if 'task' in locals():
                    task.status = TaskStatus.FAILED
                    task.error_message = str(e)
        
        self._worker_running = False
    
    def get_task_status(self, task_id: str) -> Optional[ProcessingTask]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象
        """
        return self._tasks.get(task_id)
    
    def get_pending_tasks(self) -> list[ProcessingTask]:
        """
        获取待处理任务
        
        Returns:
            任务列表
        """
        return [
            t for t in self._tasks.values()
            if not t.is_complete
        ]
    
    # ==================== 初始化和关闭 ====================
    
    async def close(self):
        """关闭管理器"""
        if self.pg:
            await self.pg.close()
        if self.milvus:
            self.milvus.close()
    
    @classmethod
    def from_config(cls, config: dict) -> "DocumentManager":
        """
        从配置创建管理器
        
        Args:
            config: 配置字典
            
        Returns:
            DocumentManager 实例
        """
        # 延迟导入以避免循环依赖
        minio_client = None
        pg_store = None
        milvus_store = None
        pipeline = None
        embedder = None
        
        if "minio" in config:
            from .minio_client import MinIOClient
            minio_client = MinIOClient.from_config(config["minio"])
        
        if "postgres" in config:
            from .pg_document import PostgresDocumentStore
            pg_store = PostgresDocumentStore.from_config(config["postgres"])
        
        if "milvus" in config:
            from .milvus_document import MilvusDocumentStore
            milvus_store = MilvusDocumentStore.from_config(config["milvus"])
        
        if "pipeline" in config:
            from ..pipeline import DocumentPipeline
            pipeline = DocumentPipeline.from_config(config["pipeline"])
        
        if "embedding" in config:
            from ..embedding import BGEM3Embedder
            embedder = BGEM3Embedder.from_config(config["embedding"])
        
        return cls(
            minio_client=minio_client,
            pg_store=pg_store,
            milvus_store=milvus_store,
            pipeline=pipeline,
            embedder=embedder,
        )
