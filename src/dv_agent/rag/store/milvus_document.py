"""
Milvus Document Vector Store
Milvus 文档向量存储

管理文档块的稠密和稀疏向量。
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """向量搜索结果"""
    
    chunk_id: int
    doc_id: str
    score: float
    content: Optional[str] = None
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MilvusDocumentStore:
    """
    Milvus 文档向量存储
    
    管理文档块的稠密和稀疏向量索引。
    """
    
    # Collection 名称
    DENSE_COLLECTION = "doc_embeddings"
    SPARSE_COLLECTION = "doc_sparse_embeddings"
    
    # 向量维度
    DENSE_DIM = 1024
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        alias: str = "default",
        dense_collection: str = DENSE_COLLECTION,
        sparse_collection: str = SPARSE_COLLECTION,
    ):
        """
        初始化存储
        
        Args:
            host: Milvus 主机
            port: Milvus 端口
            alias: 连接别名
            dense_collection: 稠密向量集合名
            sparse_collection: 稀疏向量集合名
        """
        self.host = host
        self.port = port
        self.alias = alias
        self.dense_collection = dense_collection
        self.sparse_collection = sparse_collection
        
        self._connected = False
    
    def connect(self) -> bool:
        """建立连接"""
        try:
            from pymilvus import connections
            
            connections.connect(
                alias=self.alias,
                host=self.host,
                port=self.port,
            )
            self._connected = True
            logger.info(f"Connected to Milvus: {self.host}:{self.port}")
            return True
        except ImportError:
            raise ImportError(
                "pymilvus not installed. Run: pip install pymilvus"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            return False
    
    def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            self.connect()
    
    def _get_collection(self, name: str):
        """获取集合"""
        from pymilvus import Collection
        
        self._ensure_connected()
        return Collection(name, using=self.alias)
    
    # ==================== 稠密向量操作 ====================
    
    def insert_dense_vectors(
        self,
        chunk_ids: list[int],
        doc_ids: list[str],
        vectors: list[list[float]],
        tenant_ids: list[str],
    ) -> int:
        """
        插入稠密向量
        
        Args:
            chunk_ids: 块ID列表
            doc_ids: 文档ID列表
            vectors: 向量列表
            tenant_ids: 租户ID列表
            
        Returns:
            插入的数量
        """
        collection = self._get_collection(self.dense_collection)
        
        try:
            data = [
                chunk_ids,
                doc_ids,
                tenant_ids,
                vectors,
            ]
            
            result = collection.insert(data)
            collection.flush()
            
            return result.insert_count
        except Exception as e:
            logger.error(f"Failed to insert dense vectors: {e}")
            return 0
    
    def search_dense(
        self,
        vector: list[float],
        tenant_id: str,
        top_k: int = 20,
        collection_id: Optional[str] = None,
    ) -> list[VectorSearchResult]:
        """
        稠密向量搜索
        
        Args:
            vector: 查询向量
            tenant_id: 租户ID
            top_k: 返回数量
            collection_id: 集合ID（用于过滤）
            
        Returns:
            搜索结果列表
        """
        collection = self._get_collection(self.dense_collection)
        
        try:
            # 构建过滤表达式
            expr = f'tenant_id == "{tenant_id}"'
            if collection_id:
                expr += f' && collection_id == "{collection_id}"'
            
            # 加载集合
            collection.load()
            
            # 搜索
            results = collection.search(
                data=[vector],
                anns_field="embedding",
                param={
                    "metric_type": "IP",  # 内积
                    "params": {"ef": 64},
                },
                limit=top_k,
                expr=expr,
                output_fields=["chunk_id", "doc_id"],
            )
            
            search_results = []
            for hits in results:
                for hit in hits:
                    search_results.append(VectorSearchResult(
                        chunk_id=hit.entity.get("chunk_id"),
                        doc_id=hit.entity.get("doc_id"),
                        score=hit.score,
                    ))
            
            return search_results
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            return []
    
    def delete_dense_by_doc(self, doc_id: str) -> bool:
        """
        删除文档的稠密向量
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否成功
        """
        collection = self._get_collection(self.dense_collection)
        
        try:
            collection.delete(f'doc_id == "{doc_id}"')
            return True
        except Exception as e:
            logger.error(f"Failed to delete dense vectors for {doc_id}: {e}")
            return False
    
    # ==================== 稀疏向量操作 ====================
    
    def insert_sparse_vectors(
        self,
        chunk_ids: list[int],
        doc_ids: list[str],
        vectors: list[dict],
        tenant_ids: list[str],
    ) -> int:
        """
        插入稀疏向量
        
        Args:
            chunk_ids: 块ID列表
            doc_ids: 文档ID列表
            vectors: 稀疏向量列表（dict 格式）
            tenant_ids: 租户ID列表
            
        Returns:
            插入的数量
        """
        collection = self._get_collection(self.sparse_collection)
        
        try:
            data = [
                chunk_ids,
                doc_ids,
                tenant_ids,
                vectors,
            ]
            
            result = collection.insert(data)
            collection.flush()
            
            return result.insert_count
        except Exception as e:
            logger.error(f"Failed to insert sparse vectors: {e}")
            return 0
    
    def search_sparse(
        self,
        vector: dict,
        tenant_id: str,
        top_k: int = 20,
        collection_id: Optional[str] = None,
    ) -> list[VectorSearchResult]:
        """
        稀疏向量搜索
        
        Args:
            vector: 查询向量（dict 格式）
            tenant_id: 租户ID
            top_k: 返回数量
            collection_id: 集合ID
            
        Returns:
            搜索结果列表
        """
        collection = self._get_collection(self.sparse_collection)
        
        try:
            # 构建过滤表达式
            expr = f'tenant_id == "{tenant_id}"'
            if collection_id:
                expr += f' && collection_id == "{collection_id}"'
            
            collection.load()
            
            results = collection.search(
                data=[vector],
                anns_field="sparse_embedding",
                param={
                    "metric_type": "IP",
                },
                limit=top_k,
                expr=expr,
                output_fields=["chunk_id", "doc_id"],
            )
            
            search_results = []
            for hits in results:
                for hit in hits:
                    search_results.append(VectorSearchResult(
                        chunk_id=hit.entity.get("chunk_id"),
                        doc_id=hit.entity.get("doc_id"),
                        score=hit.score,
                    ))
            
            return search_results
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            return []
    
    def delete_sparse_by_doc(self, doc_id: str) -> bool:
        """
        删除文档的稀疏向量
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否成功
        """
        collection = self._get_collection(self.sparse_collection)
        
        try:
            collection.delete(f'doc_id == "{doc_id}"')
            return True
        except Exception as e:
            logger.error(f"Failed to delete sparse vectors for {doc_id}: {e}")
            return False
    
    # ==================== 混合操作 ====================
    
    def insert_vectors(
        self,
        chunk_ids: list[int],
        doc_ids: list[str],
        dense_vectors: list[list[float]],
        sparse_vectors: list[dict],
        tenant_ids: list[str],
    ) -> tuple[int, int]:
        """
        同时插入稠密和稀疏向量
        
        Args:
            chunk_ids: 块ID列表
            doc_ids: 文档ID列表
            dense_vectors: 稠密向量列表
            sparse_vectors: 稀疏向量列表
            tenant_ids: 租户ID列表
            
        Returns:
            (稠密插入数, 稀疏插入数)
        """
        dense_count = self.insert_dense_vectors(
            chunk_ids, doc_ids, dense_vectors, tenant_ids
        )
        sparse_count = self.insert_sparse_vectors(
            chunk_ids, doc_ids, sparse_vectors, tenant_ids
        )
        
        return dense_count, sparse_count
    
    def delete_vectors_by_doc(self, doc_id: str) -> bool:
        """
        删除文档的所有向量
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否成功
        """
        dense_ok = self.delete_dense_by_doc(doc_id)
        sparse_ok = self.delete_sparse_by_doc(doc_id)
        
        return dense_ok and sparse_ok
    
    def get_collection_stats(self) -> dict:
        """
        获取集合统计信息
        
        Returns:
            统计信息字典
        """
        stats = {}
        
        try:
            dense_col = self._get_collection(self.dense_collection)
            stats["dense"] = {
                "name": self.dense_collection,
                "num_entities": dense_col.num_entities,
            }
        except Exception as e:
            stats["dense"] = {"error": str(e)}
        
        try:
            sparse_col = self._get_collection(self.sparse_collection)
            stats["sparse"] = {
                "name": self.sparse_collection,
                "num_entities": sparse_col.num_entities,
            }
        except Exception as e:
            stats["sparse"] = {"error": str(e)}
        
        return stats
    
    def close(self):
        """关闭连接"""
        try:
            from pymilvus import connections
            connections.disconnect(self.alias)
            self._connected = False
        except Exception:
            pass
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @classmethod
    def from_config(cls, config: dict) -> "MilvusDocumentStore":
        """
        从配置创建存储
        
        Args:
            config: 配置字典
            
        Returns:
            MilvusDocumentStore 实例
        """
        return cls(
            host=config.get("host", "localhost"),
            port=config.get("port", 19530),
            alias=config.get("alias", "default"),
            dense_collection=config.get("dense_collection", cls.DENSE_COLLECTION),
            sparse_collection=config.get("sparse_collection", cls.SPARSE_COLLECTION),
        )
