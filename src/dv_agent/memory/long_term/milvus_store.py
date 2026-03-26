"""
Milvus Vector Store
长期记忆向量存储

提供记忆的向量存储和语义检索
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pymilvus import (
    Collection,
    connections,
    utility,
)

logger = logging.getLogger(__name__)


class MilvusMemoryStore:
    """
    Milvus 向量存储
    
    负责：
    - 向量写入（与 PG 记忆 ID 关联）
    - 语义相似度检索
    - 用户级分区隔离
    """
    
    # Collection 名称
    USER_MEMORY_COLLECTION = "user_memory_vectors"
    ENTERPRISE_KNOWLEDGE_COLLECTION = "enterprise_knowledge"
    
    def __init__(
        self,
        alias: str = "default",
        user_collection: Optional[Collection] = None,
        knowledge_collection: Optional[Collection] = None,
    ):
        """
        初始化存储
        
        Args:
            alias: Milvus 连接别名
            user_collection: 用户记忆 Collection（可选，用于测试注入）
            knowledge_collection: 企业知识 Collection（可选）
        """
        self.alias = alias
        self._user_collection = user_collection
        self._knowledge_collection = knowledge_collection
    
    @classmethod
    async def create(
        cls,
        host: str = "localhost",
        port: int = 19530,
        alias: str = "default",
    ) -> "MilvusMemoryStore":
        """
        创建存储实例
        
        Args:
            host: Milvus 服务器地址
            port: Milvus 服务器端口
            alias: 连接别名
            
        Returns:
            MilvusMemoryStore 实例
        """
        # 建立连接
        connections.connect(
            alias=alias,
            host=host,
            port=port,
        )
        
        store = cls(alias=alias)
        
        # 加载 Collections
        await store._load_collections()
        
        return store
    
    async def _load_collections(self) -> None:
        """加载 Collections 到内存"""
        # 用户记忆 Collection
        if utility.has_collection(self.USER_MEMORY_COLLECTION):
            self._user_collection = Collection(self.USER_MEMORY_COLLECTION)
            self._user_collection.load()
            logger.info(f"Loaded collection: {self.USER_MEMORY_COLLECTION}")
        else:
            logger.warning(
                f"Collection {self.USER_MEMORY_COLLECTION} not found. "
                "Run init_milvus.py to create it."
            )
        
        # 企业知识 Collection
        if utility.has_collection(self.ENTERPRISE_KNOWLEDGE_COLLECTION):
            self._knowledge_collection = Collection(self.ENTERPRISE_KNOWLEDGE_COLLECTION)
            self._knowledge_collection.load()
            logger.info(f"Loaded collection: {self.ENTERPRISE_KNOWLEDGE_COLLECTION}")
    
    async def close(self) -> None:
        """关闭连接"""
        if self._user_collection:
            self._user_collection.release()
        if self._knowledge_collection:
            self._knowledge_collection.release()
        connections.disconnect(self.alias)
    
    @property
    def user_collection(self) -> Collection:
        """获取用户记忆 Collection"""
        if not self._user_collection:
            raise RuntimeError(
                f"Collection {self.USER_MEMORY_COLLECTION} not loaded"
            )
        return self._user_collection
    
    @property
    def knowledge_collection(self) -> Collection:
        """获取企业知识 Collection"""
        if not self._knowledge_collection:
            raise RuntimeError(
                f"Collection {self.ENTERPRISE_KNOWLEDGE_COLLECTION} not loaded"
            )
        return self._knowledge_collection
    
    # ========== 用户记忆向量操作 ==========
    
    async def insert_memory_vector(
        self,
        memory_id: UUID,
        user_id: str,
        embedding: list[float],
        memory_type: str,
        importance: float = 0.5,
    ) -> None:
        """
        插入记忆向量
        
        Args:
            memory_id: 记忆 ID（与 PG 关联）
            user_id: 用户 ID（分区键）
            embedding: 向量
            memory_type: 记忆类型
            importance: 重要性分数
        """
        data = [
            [str(memory_id)],  # memory_id
            [user_id],        # user_id
            [embedding],      # embedding
            [memory_type],    # memory_type
            [importance],     # importance
        ]
        
        self.user_collection.insert(data)
        logger.debug(f"Inserted vector for memory {memory_id}")
    
    async def insert_memory_vectors(
        self,
        records: list[dict],
    ) -> None:
        """
        批量插入记忆向量
        
        Args:
            records: 记录列表，每条包含 memory_id, user_id, embedding, memory_type, importance
        """
        if not records:
            return
        
        data = [
            [str(r["memory_id"]) for r in records],
            [r["user_id"] for r in records],
            [r["embedding"] for r in records],
            [r["memory_type"] for r in records],
            [r.get("importance", 0.5) for r in records],
        ]
        
        self.user_collection.insert(data)
        logger.info(f"Inserted {len(records)} memory vectors")
    
    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 20,
        memory_types: Optional[list[str]] = None,
        min_importance: Optional[float] = None,
    ) -> list[dict]:
        """
        语义相似度检索
        
        Args:
            user_id: 用户 ID
            query_embedding: 查询向量
            top_k: 返回数量
            memory_types: 记忆类型过滤（可选）
            min_importance: 最小重要性过滤（可选）
            
        Returns:
            检索结果列表，每条包含 memory_id, score
        """
        # 构建过滤表达式
        expr_parts = [f'user_id == "{user_id}"']
        
        if memory_types:
            types_str = ", ".join(f'"{t}"' for t in memory_types)
            expr_parts.append(f"memory_type in [{types_str}]")
        
        if min_importance is not None:
            expr_parts.append(f"importance >= {min_importance}")
        
        expr = " and ".join(expr_parts)
        
        # 执行检索
        search_params = {
            "metric_type": "IP",  # 内积（适用于归一化向量）
            "params": {"nprobe": 16},
        }
        
        results = self.user_collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["memory_id", "memory_type", "importance"],
        )
        
        # 解析结果
        hits = []
        for hit in results[0]:
            hits.append({
                "memory_id": UUID(hit.entity.get("memory_id")),
                "memory_type": hit.entity.get("memory_type"),
                "importance": hit.entity.get("importance"),
                "score": hit.score,
            })
        
        return hits
    
    async def delete_memory_vector(self, memory_id: UUID) -> bool:
        """
        删除记忆向量
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        expr = f'memory_id == "{str(memory_id)}"'
        self.user_collection.delete(expr)
        logger.debug(f"Deleted vector for memory {memory_id}")
        return True
    
    async def delete_memory_vectors(self, memory_ids: list[UUID]) -> int:
        """
        批量删除记忆向量
        
        Args:
            memory_ids: 记忆 ID 列表
            
        Returns:
            删除数量
        """
        if not memory_ids:
            return 0
        
        ids_str = ", ".join(f'"{str(mid)}"' for mid in memory_ids)
        expr = f"memory_id in [{ids_str}]"
        
        self.user_collection.delete(expr)
        logger.info(f"Deleted {len(memory_ids)} memory vectors")
        return len(memory_ids)
    
    async def update_importance(
        self,
        memory_id: UUID,
        importance: float,
    ) -> None:
        """
        更新向量的重要性分数
        
        注意：Milvus 不支持直接更新，需要先删后插
        这里我们只更新 PG 中的 importance，Milvus 中的值作为缓存
        
        Args:
            memory_id: 记忆 ID
            importance: 新的重要性分数
        """
        # Milvus 2.x 不支持直接更新
        # 实际实现中，可以考虑：
        # 1. 接受数据不一致，以 PG 为准
        # 2. 周期性全量同步
        # 3. 使用 upsert（需要重新插入完整数据）
        logger.debug(
            f"Importance update for {memory_id} skipped in Milvus "
            "(use PG as source of truth)"
        )
    
    # ========== 企业知识向量操作 ==========
    
    async def insert_knowledge_vector(
        self,
        knowledge_id: UUID,
        embedding: list[float],
        category: Optional[str] = None,
        dept_id: Optional[str] = None,
    ) -> None:
        """
        插入企业知识向量
        
        Args:
            knowledge_id: 知识 ID
            embedding: 向量
            category: 分类
            dept_id: 部门 ID（None 表示全员可见）
        """
        data = [
            [str(knowledge_id)],
            [embedding],
            [category or ""],
            [dept_id or ""],
        ]
        
        self.knowledge_collection.insert(data)
        logger.debug(f"Inserted knowledge vector {knowledge_id}")
    
    async def search_knowledge(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        category: Optional[str] = None,
        dept_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        检索企业知识
        
        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            category: 分类过滤（可选）
            dept_ids: 部门 ID 列表（含 "" 表示全员）
            
        Returns:
            检索结果列表
        """
        # 构建过滤表达式
        expr_parts = []
        
        if category:
            expr_parts.append(f'category == "{category}"')
        
        if dept_ids:
            # 包含指定部门或全员可见
            dept_ids_with_public = list(dept_ids) + [""]
            depts_str = ", ".join(f'"{d}"' for d in dept_ids_with_public)
            expr_parts.append(f"dept_id in [{depts_str}]")
        
        expr = " and ".join(expr_parts) if expr_parts else ""
        
        search_params = {
            "metric_type": "IP",
            "params": {"nprobe": 16},
        }
        
        results = self.knowledge_collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr if expr else None,
            output_fields=["knowledge_id", "category", "dept_id"],
        )
        
        hits = []
        for hit in results[0]:
            hits.append({
                "knowledge_id": UUID(hit.entity.get("knowledge_id")),
                "category": hit.entity.get("category"),
                "dept_id": hit.entity.get("dept_id"),
                "score": hit.score,
            })
        
        return hits
    
    # ========== 工具方法 ==========
    
    async def get_collection_stats(self) -> dict:
        """获取 Collection 统计信息"""
        stats = {}
        
        if self._user_collection:
            stats["user_memory_vectors"] = {
                "num_entities": self._user_collection.num_entities,
            }
        
        if self._knowledge_collection:
            stats["enterprise_knowledge"] = {
                "num_entities": self._knowledge_collection.num_entities,
            }
        
        return stats
    
    async def flush(self) -> None:
        """刷新数据到磁盘"""
        if self._user_collection:
            self._user_collection.flush()
        if self._knowledge_collection:
            self._knowledge_collection.flush()
        logger.debug("Flushed Milvus collections")
