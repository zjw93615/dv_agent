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
    
    # ==================== 集合操作 ====================
    
    async def list_collections(
        self,
        tenant_id: str,
    ) -> list:
        """
        列出集合
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            集合列表
        """
        if self.pg:
            return await self.pg.list_collections(tenant_id)
        return []
    
    async def create_collection(
        self,
        tenant_id: str,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """
        创建集合
        
        Args:
            tenant_id: 租户ID
            name: 集合名称
            description: 集合描述
            metadata: 元数据
            
        Returns:
            集合信息
        """
        import uuid
        from datetime import datetime, timezone
        from dataclasses import dataclass
        
        collection_id = str(uuid.uuid4())
        
        if self.pg:
            return await self.pg.create_collection(
                collection_id=collection_id,
                tenant_id=tenant_id,
                name=name,
                description=description,
                metadata=metadata,
            )
        
        # 如果没有 pg_store，返回一个简单对象
        @dataclass
        class Collection:
            collection_id: str
            tenant_id: str
            name: str
            description: Optional[str]
            document_count: int = 0
            chunk_count: int = 0
            created_at: datetime = None
            metadata: dict = None
        
        return Collection(
            collection_id=collection_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
    
    async def get_collection(
        self,
        collection_id: str,
        tenant_id: str,
    ):
        """
        获取集合信息
        
        Args:
            collection_id: 集合ID
            tenant_id: 租户ID
            
        Returns:
            集合信息
        """
        if self.pg:
            return await self.pg.get_collection(collection_id, tenant_id)
        return None
    
    async def delete_collection(
        self,
        collection_id: str,
        tenant_id: str,
        delete_documents: bool = False,
    ) -> bool:
        """
        删除集合
        
        Args:
            collection_id: 集合ID
            tenant_id: 租户ID
            delete_documents: 是否同时删除集合中的文档
            
        Returns:
            是否成功
        """
        if delete_documents:
            # 删除集合中的所有文档
            docs = await self.list_documents(tenant_id, collection_id)
            for doc in docs:
                await self.delete_document(doc.get("doc_id") or doc.get("document_id"), tenant_id)
        
        if self.pg:
            return await self.pg.delete_collection(collection_id, tenant_id)
        return False
    
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
        from urllib.parse import quote
        
        content_hash = hashlib.sha256(content).hexdigest()
        # 对文件名进行 URL 编码以支持中文
        safe_filename = quote(filename, safe='')
        storage_path = f"{tenant_id}/{collection_id or 'default'}/{content_hash[:8]}_{safe_filename}"
        
        # 上传到 MinIO
        if self.minio:
            # 元数据中的中文也需要编码
            obj_info = self.minio.upload_bytes(
                content,
                storage_path,
                metadata={
                    "tenant_id": tenant_id,
                    "filename": quote(filename, safe=''),
                    "original_filename": quote(filename, safe=''),
                },
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
        
        # 删除向量（忽略集合不存在的错误）
        if self.milvus:
            try:
                self.milvus.delete_vectors_by_doc(doc_id)
            except Exception as e:
                # Milvus 集合可能不存在，记录日志但继续执行
                logger.warning(f"Failed to delete vectors for doc {doc_id}: {e}")
        
        # 删除块
        if self.pg:
            await self.pg.delete_chunks(doc_id)
        
        # 删除文档记录
        if self.pg:
            await self.pg.delete_document(doc_id, tenant_id)
        
        # 删除文件
        if self.minio and doc.get("storage_path"):
            try:
                self.minio.delete_object(doc["storage_path"])
            except Exception as e:
                logger.warning(f"Failed to delete file for doc {doc_id}: {e}")
        
        return True
    
    async def list_documents(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list, int]:
        """
        列出文档
        
        Args:
            tenant_id: 租户ID
            collection_id: 集合ID
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            (文档列表, 总数)
        """
        if self.pg:
            docs = await self.pg.list_documents(
                tenant_id, collection_id, offset=offset, limit=limit
            )
            total = await self.pg.count_documents(tenant_id, collection_id)
            return docs, total
        return [], 0
    
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
        
        # 辅助函数：发送 WebSocket 通知
        async def notify_progress(stage: str, progress: float, message: str = ""):
            try:
                from ..websocket_notify import notify_document_progress
                await notify_document_progress(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    stage=stage,
                    progress=progress,
                    message=message,
                )
            except Exception as e:
                logger.debug(f"Failed to send WS notification: {e}")
        
        logger.info("=" * 60)
        logger.info(f"[DOC-PROCESS] 开始处理文档")
        logger.info(f"[DOC-PROCESS]   doc_id: {doc_id}")
        logger.info(f"[DOC-PROCESS]   tenant_id: {tenant_id}")
        logger.info(f"[DOC-PROCESS]   content_size: {len(content)} bytes")
        logger.info("=" * 60)
        
        try:
            # 更新状态为处理中
            if self.pg:
                await self.pg.update_document_status(
                    doc_id, DocumentStatus.PROCESSING
                )
                logger.debug(f"[DOC-PROCESS] 状态已更新为 PROCESSING")
            
            await notify_progress("processing", 0.1, "开始处理文档")
            
            # 获取文档信息
            doc = await self.get_document(doc_id, tenant_id)
            if not doc:
                logger.error(f"[DOC-PROCESS] 文档不存在: {doc_id}")
                return False
            
            logger.info(f"[DOC-PROCESS] 文档信息:")
            logger.info(f"[DOC-PROCESS]   filename: {doc.get('filename')}")
            logger.info(f"[DOC-PROCESS]   file_type: {doc.get('file_type')}")
            logger.info(f"[DOC-PROCESS]   file_size: {doc.get('file_size')}")
            logger.info(f"[DOC-PROCESS]   collection_id: {doc.get('collection_id')}")
            
            # 文档处理流水线（在线程池中运行同步代码）
            await notify_progress("parsing", 0.2, "解析文档内容")
            
            if self.pipeline:
                logger.info(f"[DOC-PROCESS] [阶段1] 开始解析文档...")
                logger.debug(f"[DOC-PROCESS]   pipeline: {type(self.pipeline).__name__}")
                
                import asyncio
                import time
                parse_start = time.time()
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,  # 使用默认线程池
                    lambda: self.pipeline.process(
                        content=content,
                        filename=doc["filename"],
                        tenant_id=tenant_id,
                        collection_id=doc.get("collection_id", ""),
                    )
                )
                
                parse_time = time.time() - parse_start
                logger.info(f"[DOC-PROCESS] [阶段1] 文档解析完成，耗时: {parse_time:.2f}s")
                logger.info(f"[DOC-PROCESS]   解析成功: {result.success}")
                logger.info(f"[DOC-PROCESS]   chunks数量: {len(result.chunks) if result.chunks else 0}")
                if result.errors:
                    logger.warning(f"[DOC-PROCESS]   解析错误: {result.errors}")
                
                if not result.success:
                    logger.error(f"[DOC-PROCESS] 文档解析失败: {result.errors}")
                    if self.pg:
                        await self.pg.update_document_status(
                            doc_id, DocumentStatus.FAILED,
                            error_message="; ".join(result.errors)
                        )
                    # 发送错误通知
                    try:
                        from ..websocket_notify import notify_document_error
                        await notify_document_error(
                            tenant_id=tenant_id,
                            document_id=doc_id,
                            error="; ".join(result.errors),
                            stage="parsing",
                        )
                    except Exception:
                        pass
                    return False
                
                chunks = result.chunks
                logger.info(f"[DOC-PROCESS] [阶段2] 文档分块完成")
                logger.info(f"[DOC-PROCESS]   总块数: {len(chunks)}")
                if chunks:
                    # 显示前3个块的信息
                    for i, chunk in enumerate(chunks[:3]):
                        content_preview = chunk.content[:100].replace('\n', ' ') if chunk.content else ''
                        logger.info(f"[DOC-PROCESS]   chunk[{i}]: index={chunk.index}, page={chunk.page_number}, len={len(chunk.content)}")
                        logger.debug(f"[DOC-PROCESS]     preview: {content_preview}...")
                    if len(chunks) > 3:
                        logger.info(f"[DOC-PROCESS]   ... 还有 {len(chunks) - 3} 个块")
                
                await notify_progress("chunking", 0.5, f"文档分块完成，共 {len(chunks)} 块")
            else:
                logger.error(f"[DOC-PROCESS] 没有可用的 pipeline")
                return False
            
            # 存储块
            await notify_progress("indexing", 0.6, "保存文档块")
            
            logger.info(f"[DOC-PROCESS] [阶段3] 存储文档块到数据库...")
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
                import time
                chunk_start = time.time()
                await self.pg.create_chunks(doc_id, chunk_data, tenant_id=tenant_id)
                chunk_time = time.time() - chunk_start
                logger.info(f"[DOC-PROCESS] [阶段3] 文档块存储完成，耗时: {chunk_time:.2f}s")
                logger.info(f"[DOC-PROCESS]   存储块数: {len(chunk_data)}")
            else:
                logger.warning(f"[DOC-PROCESS] [阶段3] 跳过块存储 (pg={self.pg is not None}, chunks={len(chunks) if chunks else 0})")
            
            # 向量化
            if self.embedder and chunks:
                await notify_progress("embedding", 0.7, "生成向量嵌入")
                
                logger.info(f"[DOC-PROCESS] [阶段4] 开始向量化...")
                logger.info(f"[DOC-PROCESS]   embedder: {type(self.embedder).__name__}")
                logger.info(f"[DOC-PROCESS]   待嵌入文本数: {len(chunks)}")
                
                import time
                embed_start = time.time()
                embeddings = self.embedder.embed_documents(
                    [c.content for c in chunks]
                )
                embed_time = time.time() - embed_start
                
                logger.info(f"[DOC-PROCESS] [阶段4] 向量嵌入完成，耗时: {embed_time:.2f}s")
                logger.info(f"[DOC-PROCESS]   生成向量数: {len(embeddings)}")
                if embeddings:
                    first_emb = embeddings[0]
                    logger.info(f"[DOC-PROCESS]   dense维度: {len(first_emb.dense_embedding) if first_emb.dense_embedding else 0}")
                    logger.info(f"[DOC-PROCESS]   sparse存在: {first_emb.sparse_embedding is not None}")
                
                # 存储向量
                if self.milvus:
                    await notify_progress("embedding", 0.85, "存储向量索引")
                    
                    logger.info(f"[DOC-PROCESS] [阶段5] 存储向量到 Milvus...")
                    
                    # 获取块ID（从数据库）
                    db_chunks = await self.pg.get_chunks(doc_id)
                    chunk_ids = [c["id"] for c in db_chunks]
                    doc_ids = [doc_id] * len(chunks)
                    tenant_ids = [tenant_id] * len(chunks)
                    
                    logger.info(f"[DOC-PROCESS]   chunk_ids: {chunk_ids[:3]}{'...' if len(chunk_ids) > 3 else ''}")
                    
                    dense_vectors = [e.dense_embedding for e in embeddings]
                    sparse_vectors = [
                        e.sparse_embedding.to_dict() 
                        if e.sparse_embedding else {}
                        for e in embeddings
                    ]
                    
                    vector_start = time.time()
                    self.milvus.insert_vectors(
                        chunk_ids, doc_ids, dense_vectors, sparse_vectors, tenant_ids
                    )
                    vector_time = time.time() - vector_start
                    logger.info(f"[DOC-PROCESS] [阶段5] 向量存储完成，耗时: {vector_time:.2f}s")
                else:
                    logger.warning(f"[DOC-PROCESS] [阶段5] 跳过向量存储 (milvus not available)")
            else:
                logger.warning(f"[DOC-PROCESS] [阶段4] 跳过向量化 (embedder={self.embedder is not None}, chunks={len(chunks) if chunks else 0})")
            
            # 更新状态为完成
            if self.pg:
                await self.pg.update_document_status(
                    doc_id, DocumentStatus.COMPLETED
                )
                logger.info(f"[DOC-PROCESS] 状态已更新为 COMPLETED")
            
            # 发送完成通知
            try:
                from ..websocket_notify import notify_document_completed
                await notify_document_completed(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    filename=doc.get("filename", ""),
                    chunk_count=len(chunks) if chunks else 0,
                )
            except Exception as e:
                logger.debug(f"Failed to send completion notification: {e}")
            
            logger.info("=" * 60)
            logger.info(f"[DOC-PROCESS] 文档处理完成!")
            logger.info(f"[DOC-PROCESS]   doc_id: {doc_id}")
            logger.info(f"[DOC-PROCESS]   filename: {doc.get('filename')}")
            logger.info(f"[DOC-PROCESS]   总块数: {len(chunks) if chunks else 0}")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            import traceback
            logger.error("=" * 60)
            logger.error(f"[DOC-PROCESS] 文档处理失败!")
            logger.error(f"[DOC-PROCESS]   doc_id: {doc_id}")
            logger.error(f"[DOC-PROCESS]   error: {e}")
            logger.error(f"[DOC-PROCESS]   traceback:")
            logger.error(traceback.format_exc())
            logger.error("=" * 60)
            
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
        logger.info("Document processing worker started")
        
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
                        logger.info("Document processing worker idle, shutting down")
                        break
                    continue
                
                logger.info(f"Processing document: {task.doc_id}")
                
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
                
                logger.info(f"Document {task.doc_id} processing {'completed' if success else 'failed'}")
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
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
