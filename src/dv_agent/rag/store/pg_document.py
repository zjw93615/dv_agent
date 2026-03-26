"""
PostgreSQL Document Store
PostgreSQL 文档元数据存储

管理文档和文档块的元数据。
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DocumentStatus(str, Enum):
    """文档处理状态"""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PostgresDocumentStore:
    """
    PostgreSQL 文档存储
    
    管理文档和文档块的 CRUD 操作。
    """
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool: Any = None,
    ):
        """
        初始化存储
        
        Args:
            connection_string: PostgreSQL 连接字符串
            pool: 连接池（可选）
        """
        self.connection_string = connection_string
        self._pool = pool
        self._conn = None
    
    async def _get_connection(self):
        """获取数据库连接"""
        if self._pool:
            return await self._pool.acquire()
        
        if self._conn is None:
            try:
                import asyncpg
                self._conn = await asyncpg.connect(self.connection_string)
            except ImportError:
                raise ImportError(
                    "asyncpg not installed. Run: pip install asyncpg"
                )
        
        return self._conn
    
    async def _release_connection(self, conn):
        """释放连接"""
        if self._pool:
            await self._pool.release(conn)
    
    # ==================== 文档操作 ====================
    
    async def create_document(
        self,
        doc_id: str,
        tenant_id: str,
        filename: str,
        file_type: str,
        file_size: int,
        content_hash: str,
        storage_path: str,
        collection_id: str = "",
        title: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        创建文档记录
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            filename: 文件名
            file_type: 文件类型
            file_size: 文件大小
            content_hash: 内容哈希
            storage_path: 存储路径
            collection_id: 集合ID
            title: 标题
            metadata: 元数据
            
        Returns:
            创建的文档记录
        """
        conn = await self._get_connection()
        
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO documents (
                    doc_id, tenant_id, filename, file_type, file_size,
                    content_hash, storage_path, collection_id, title,
                    status, metadata, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $12)
                RETURNING *
                """,
                doc_id, tenant_id, filename, file_type, file_size,
                content_hash, storage_path, collection_id, title,
                DocumentStatus.PENDING.value,
                json.dumps(metadata or {}),
                datetime.utcnow(),
            )
            
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            return None
        finally:
            await self._release_connection(conn)
    
    async def get_document(
        self,
        doc_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        获取文档
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID（用于隔离验证）
            
        Returns:
            文档记录
        """
        conn = await self._get_connection()
        
        try:
            if tenant_id:
                row = await conn.fetchrow(
                    "SELECT * FROM documents WHERE doc_id = $1 AND tenant_id = $2",
                    doc_id, tenant_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM documents WHERE doc_id = $1",
                    doc_id
                )
            
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None
        finally:
            await self._release_connection(conn)
    
    async def update_document_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新文档状态
        
        Args:
            doc_id: 文档ID
            status: 新状态
            error_message: 错误信息
            
        Returns:
            是否成功
        """
        conn = await self._get_connection()
        
        try:
            if error_message:
                await conn.execute(
                    """
                    UPDATE documents 
                    SET status = $2, error_message = $3, updated_at = $4
                    WHERE doc_id = $1
                    """,
                    doc_id, status.value, error_message, datetime.utcnow()
                )
            else:
                await conn.execute(
                    """
                    UPDATE documents 
                    SET status = $2, updated_at = $3
                    WHERE doc_id = $1
                    """,
                    doc_id, status.value, datetime.utcnow()
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update document status: {e}")
            return False
        finally:
            await self._release_connection(conn)
    
    async def delete_document(
        self,
        doc_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        删除文档
        
        Args:
            doc_id: 文档ID
            tenant_id: 租户ID
            
        Returns:
            是否成功
        """
        conn = await self._get_connection()
        
        try:
            if tenant_id:
                await conn.execute(
                    "DELETE FROM documents WHERE doc_id = $1 AND tenant_id = $2",
                    doc_id, tenant_id
                )
            else:
                await conn.execute(
                    "DELETE FROM documents WHERE doc_id = $1",
                    doc_id
                )
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
        finally:
            await self._release_connection(conn)
    
    async def list_documents(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
        status: Optional[DocumentStatus] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        """
        列出文档
        
        Args:
            tenant_id: 租户ID
            collection_id: 集合ID
            status: 状态过滤
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            文档列表
        """
        conn = await self._get_connection()
        
        try:
            query = "SELECT * FROM documents WHERE tenant_id = $1"
            params = [tenant_id]
            param_idx = 2
            
            if collection_id:
                query += f" AND collection_id = ${param_idx}"
                params.append(collection_id)
                param_idx += 1
            
            if status:
                query += f" AND status = ${param_idx}"
                params.append(status.value)
                param_idx += 1
            
            query += f" ORDER BY created_at DESC OFFSET ${param_idx} LIMIT ${param_idx + 1}"
            params.extend([offset, limit])
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []
        finally:
            await self._release_connection(conn)
    
    async def count_documents(
        self,
        tenant_id: str,
        collection_id: Optional[str] = None,
    ) -> int:
        """
        统计文档数量
        
        Args:
            tenant_id: 租户ID
            collection_id: 集合ID
            
        Returns:
            文档数量
        """
        conn = await self._get_connection()
        
        try:
            if collection_id:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM documents WHERE tenant_id = $1 AND collection_id = $2",
                    tenant_id, collection_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM documents WHERE tenant_id = $1",
                    tenant_id
                )
            
            return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Failed to count documents: {e}")
            return 0
        finally:
            await self._release_connection(conn)
    
    # ==================== 文档块操作 ====================
    
    async def create_chunks(
        self,
        doc_id: str,
        chunks: list[dict],
    ) -> int:
        """
        批量创建文档块
        
        Args:
            doc_id: 文档ID
            chunks: 块列表，每个包含 chunk_index, content, page_number, metadata
            
        Returns:
            创建的块数量
        """
        if not chunks:
            return 0
        
        conn = await self._get_connection()
        
        try:
            # 使用 executemany
            values = [
                (
                    doc_id,
                    chunk.get("chunk_index", i),
                    chunk.get("content", ""),
                    chunk.get("page_number"),
                    json.dumps(chunk.get("metadata", {})),
                    datetime.utcnow(),
                )
                for i, chunk in enumerate(chunks)
            ]
            
            await conn.executemany(
                """
                INSERT INTO document_chunks (
                    doc_id, chunk_index, content, page_number, metadata, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                values
            )
            
            return len(chunks)
        except Exception as e:
            logger.error(f"Failed to create chunks: {e}")
            return 0
        finally:
            await self._release_connection(conn)
    
    async def get_chunks(
        self,
        doc_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """
        获取文档块
        
        Args:
            doc_id: 文档ID
            offset: 偏移量
            limit: 限制数量
            
        Returns:
            块列表
        """
        conn = await self._get_connection()
        
        try:
            rows = await conn.fetch(
                """
                SELECT * FROM document_chunks 
                WHERE doc_id = $1 
                ORDER BY chunk_index 
                OFFSET $2 LIMIT $3
                """,
                doc_id, offset, limit
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get chunks: {e}")
            return []
        finally:
            await self._release_connection(conn)
    
    async def get_chunk_by_id(self, chunk_id: int) -> Optional[dict]:
        """
        根据ID获取块
        
        Args:
            chunk_id: 块ID
            
        Returns:
            块记录
        """
        conn = await self._get_connection()
        
        try:
            row = await conn.fetchrow(
                "SELECT * FROM document_chunks WHERE id = $1",
                chunk_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get chunk {chunk_id}: {e}")
            return None
        finally:
            await self._release_connection(conn)
    
    async def delete_chunks(self, doc_id: str) -> bool:
        """
        删除文档的所有块
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否成功
        """
        conn = await self._get_connection()
        
        try:
            await conn.execute(
                "DELETE FROM document_chunks WHERE doc_id = $1",
                doc_id
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete chunks for {doc_id}: {e}")
            return False
        finally:
            await self._release_connection(conn)
    
    async def count_chunks(self, doc_id: str) -> int:
        """
        统计文档块数量
        
        Args:
            doc_id: 文档ID
            
        Returns:
            块数量
        """
        conn = await self._get_connection()
        
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM document_chunks WHERE doc_id = $1",
                doc_id
            )
            return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Failed to count chunks: {e}")
            return 0
        finally:
            await self._release_connection(conn)
    
    # ==================== BM25 全文检索 ====================
    
    async def search_bm25(
        self,
        query: str,
        tenant_id: str,
        collection_id: Optional[str] = None,
        top_k: int = 20,
    ) -> list[dict]:
        """
        BM25 全文检索
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            collection_id: 集合ID
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        conn = await self._get_connection()
        
        try:
            # 构建查询
            if collection_id:
                rows = await conn.fetch(
                    """
                    SELECT 
                        c.id as chunk_id,
                        c.doc_id,
                        c.chunk_index,
                        c.content,
                        c.page_number,
                        d.filename,
                        d.title,
                        ts_rank_cd(c.content_tsv, plainto_tsquery('simple', $1)) as score
                    FROM document_chunks c
                    JOIN documents d ON c.doc_id = d.doc_id
                    WHERE d.tenant_id = $2 
                      AND d.collection_id = $3
                      AND c.content_tsv @@ plainto_tsquery('simple', $1)
                    ORDER BY score DESC
                    LIMIT $4
                    """,
                    query, tenant_id, collection_id, top_k
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT 
                        c.id as chunk_id,
                        c.doc_id,
                        c.chunk_index,
                        c.content,
                        c.page_number,
                        d.filename,
                        d.title,
                        ts_rank_cd(c.content_tsv, plainto_tsquery('simple', $1)) as score
                    FROM document_chunks c
                    JOIN documents d ON c.doc_id = d.doc_id
                    WHERE d.tenant_id = $2
                      AND c.content_tsv @@ plainto_tsquery('simple', $1)
                    ORDER BY score DESC
                    LIMIT $3
                    """,
                    query, tenant_id, top_k
                )
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
        finally:
            await self._release_connection(conn)
    
    async def close(self):
        """关闭连接"""
        if self._conn:
            await self._conn.close()
            self._conn = None
    
    @classmethod
    def from_config(cls, config: dict) -> "PostgresDocumentStore":
        """
        从配置创建存储
        
        Args:
            config: 配置字典
            
        Returns:
            PostgresDocumentStore 实例
        """
        return cls(
            connection_string=config.get("connection_string"),
        )
