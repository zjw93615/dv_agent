"""
Long-term Memory Module
长期记忆模块 - PostgreSQL + Milvus 联动存储
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from ..config import MemoryConfig
from ..models import Memory, MemoryType
from .embedding import EmbeddingService
from .milvus_store import MilvusMemoryStore
from .pg_store import PostgresMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """混合检索结果"""
    memory: Memory
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    recency_score: Optional[float] = None
    final_score: float = 0.0


class LongTermMemory:
    """
    长期记忆统一接口
    
    整合 PostgreSQL（结构化存储）和 Milvus（向量存储）：
    - PG: Source of Truth，存储完整记忆数据
    - Milvus: 向量索引，支持语义检索
    
    写入策略：
    - 先写 PG（主存储），成功后同步到 Milvus
    - Milvus 写入失败不影响主流程（eventual consistency）
    
    检索策略：
    - 向量检索走 Milvus
    - 关键词检索走 PG TSVECTOR
    - 时序检索走 PG
    - 结果合并后从 PG 获取完整数据
    """
    
    def __init__(
        self,
        pg: PostgresMemoryStore,
        milvus: MilvusMemoryStore,
        embedding: EmbeddingService,
        config: Optional[MemoryConfig] = None,
    ):
        """
        初始化长期记忆
        
        Args:
            pg: PostgreSQL 存储
            milvus: Milvus 向量存储
            embedding: 向量生成服务
            config: 配置（可选）
        """
        self.pg = pg
        self.milvus = milvus
        self.embedding = embedding
        self.config = config or MemoryConfig()
    
    @classmethod
    async def create(
        cls,
        pg_dsn: str,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        config: Optional[MemoryConfig] = None,
    ) -> "LongTermMemory":
        """
        创建长期记忆实例
        
        Args:
            pg_dsn: PostgreSQL 连接字符串
            milvus_host: Milvus 服务器地址
            milvus_port: Milvus 服务器端口
            embedding_model: Embedding 模型名称
            config: 配置
            
        Returns:
            LongTermMemory 实例
        """
        # 并行初始化各组件
        pg_task = PostgresMemoryStore.create(pg_dsn)
        milvus_task = MilvusMemoryStore.create(milvus_host, milvus_port)
        embedding_service = EmbeddingService(model_name=embedding_model)
        
        pg, milvus = await asyncio.gather(pg_task, milvus_task)
        
        logger.info("LongTermMemory initialized successfully")
        return cls(pg, milvus, embedding_service, config)
    
    async def close(self) -> None:
        """关闭所有连接"""
        await asyncio.gather(
            self.pg.close(),
            self.milvus.close(),
        )
        logger.info("LongTermMemory closed")
    
    # ========== 存储操作 ==========
    
    async def store(
        self,
        memory: Memory,
        generate_embedding: bool = True,
    ) -> Memory:
        """
        存储记忆
        
        Args:
            memory: 记忆对象
            generate_embedding: 是否自动生成向量
            
        Returns:
            存储后的记忆
        """
        # 1. 生成向量（如需要）
        if generate_embedding and memory.embedding is None:
            memory.embedding = await self.embedding.embed(memory.content)
        
        # 2. 先存 PG（Source of Truth）
        stored_memory = await self.pg.create(memory)
        
        # 3. 同步到 Milvus（eventual consistency）
        if stored_memory.embedding:
            try:
                await self.milvus.insert_memory_vector(
                    memory_id=stored_memory.id,
                    user_id=stored_memory.user_id,
                    embedding=stored_memory.embedding,
                    memory_type=stored_memory.memory_type.value,
                    importance=stored_memory.importance,
                )
            except Exception as e:
                # Milvus 写入失败，记录日志但不影响主流程
                logger.error(
                    f"Failed to sync memory {stored_memory.id} to Milvus: {e}",
                    exc_info=True,
                )
        
        logger.debug(f"Stored memory {stored_memory.id} for user {stored_memory.user_id}")
        return stored_memory
    
    async def store_many(
        self,
        memories: list[Memory],
        generate_embedding: bool = True,
    ) -> list[Memory]:
        """
        批量存储记忆
        
        Args:
            memories: 记忆列表
            generate_embedding: 是否自动生成向量
            
        Returns:
            存储后的记忆列表
        """
        if not memories:
            return []
        
        # 1. 批量生成向量
        if generate_embedding:
            contents = [m.content for m in memories if m.embedding is None]
            if contents:
                embeddings = await self.embedding.embed_batch(contents)
                embed_idx = 0
                for m in memories:
                    if m.embedding is None:
                        m.embedding = embeddings[embed_idx]
                        embed_idx += 1
        
        # 2. 批量存 PG
        stored_memories = await self.pg.create_many(memories)
        
        # 3. 批量同步 Milvus
        milvus_data = [
            (m.id, m.user_id, m.embedding, m.memory_type.value, m.importance)
            for m in stored_memories
            if m.embedding is not None
        ]
        
        if milvus_data:
            try:
                await self.milvus.insert_memory_vectors(milvus_data)
            except Exception as e:
                logger.error(f"Failed to batch sync to Milvus: {e}", exc_info=True)
        
        logger.info(f"Stored {len(stored_memories)} memories")
        return stored_memories
    
    # ========== 读取操作 ==========
    
    async def get(self, memory_id: UUID) -> Optional[Memory]:
        """
        获取单条记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            记忆对象，不存在返回 None
        """
        return await self.pg.get(memory_id)
    
    async def get_by_user(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """
        获取用户的记忆列表
        
        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤
            limit: 返回数量
            offset: 偏移量
            
        Returns:
            记忆列表
        """
        return await self.pg.get_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
    
    # ========== 混合检索 ==========
    
    async def search_hybrid(
        self,
        user_id: str,
        query: str,
        top_k: int = 20,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.3,
        recency_weight: float = 0.2,
        memory_types: Optional[list[MemoryType]] = None,
    ) -> list[SearchResult]:
        """
        混合检索（向量 + 关键词 + 时序）
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回数量
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            recency_weight: 时序检索权重
            memory_types: 记忆类型过滤
            
        Returns:
            排序后的检索结果
        """
        # 并行执行三路检索
        query_embedding = await self.embedding.embed(query)
        
        vector_task = self.milvus.search_by_vector(
            user_id=user_id,
            embedding=query_embedding,
            top_k=top_k,
            memory_types=[t.value for t in memory_types] if memory_types else None,
        )
        keyword_task = self.pg.search_fulltext(
            user_id=user_id,
            query=query,
            limit=top_k,
        )
        recency_task = self.pg.get_recent(
            user_id=user_id,
            limit=top_k,
        )
        
        vector_results, keyword_results, recency_results = await asyncio.gather(
            vector_task, keyword_task, recency_task,
            return_exceptions=True,
        )
        
        # 处理异常
        if isinstance(vector_results, Exception):
            logger.warning(f"Vector search failed: {vector_results}")
            vector_results = []
        if isinstance(keyword_results, Exception):
            logger.warning(f"Keyword search failed: {keyword_results}")
            keyword_results = []
        if isinstance(recency_results, Exception):
            logger.warning(f"Recency search failed: {recency_results}")
            recency_results = []
        
        # 合并结果
        memory_scores: dict[UUID, SearchResult] = {}
        
        # 向量检索结果
        for memory_id, score in vector_results:
            if memory_id not in memory_scores:
                memory_scores[memory_id] = SearchResult(memory=None, vector_score=score)
            else:
                memory_scores[memory_id].vector_score = score
        
        # 关键词检索结果
        for memory, score in keyword_results:
            if memory.id not in memory_scores:
                memory_scores[memory.id] = SearchResult(memory=memory, keyword_score=score)
            else:
                memory_scores[memory.id].keyword_score = score
                if memory_scores[memory.id].memory is None:
                    memory_scores[memory.id].memory = memory
        
        # 时序检索结果（按位置赋分，最近的分数最高）
        for idx, memory in enumerate(recency_results):
            recency_score = 1.0 - (idx / max(len(recency_results), 1))
            if memory.id not in memory_scores:
                memory_scores[memory.id] = SearchResult(memory=memory, recency_score=recency_score)
            else:
                memory_scores[memory.id].recency_score = recency_score
                if memory_scores[memory.id].memory is None:
                    memory_scores[memory.id].memory = memory
        
        # 补全缺失的记忆数据
        missing_ids = [
            mid for mid, result in memory_scores.items()
            if result.memory is None
        ]
        if missing_ids:
            missing_memories = await asyncio.gather(
                *[self.pg.get(mid) for mid in missing_ids]
            )
            for mid, mem in zip(missing_ids, missing_memories):
                if mem:
                    memory_scores[mid].memory = mem
                else:
                    # 记忆不存在（可能已删除），移除
                    del memory_scores[mid]
        
        # 计算最终分数并排序
        results = []
        for result in memory_scores.values():
            if result.memory is None:
                continue
            
            # 归一化各路分数
            v_score = result.vector_score or 0.0
            k_score = result.keyword_score or 0.0
            r_score = result.recency_score or 0.0
            
            # 加权求和
            result.final_score = (
                vector_weight * v_score +
                keyword_weight * k_score +
                recency_weight * r_score
            )
            results.append(result)
        
        # 按最终分数降序排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        return results[:top_k]
    
    async def search_vector(
        self,
        user_id: str,
        query: str,
        top_k: int = 10,
        memory_types: Optional[list[MemoryType]] = None,
    ) -> list[SearchResult]:
        """
        纯向量检索
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回数量
            memory_types: 记忆类型过滤
            
        Returns:
            检索结果
        """
        query_embedding = await self.embedding.embed(query)
        
        vector_results = await self.milvus.search_by_vector(
            user_id=user_id,
            embedding=query_embedding,
            top_k=top_k,
            memory_types=[t.value for t in memory_types] if memory_types else None,
        )
        
        # 获取完整记忆数据
        results = []
        for memory_id, score in vector_results:
            memory = await self.pg.get(memory_id)
            if memory:
                results.append(SearchResult(
                    memory=memory,
                    vector_score=score,
                    final_score=score,
                ))
        
        return results
    
    async def search_keyword(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        纯关键词检索
        
        Args:
            user_id: 用户 ID
            query: 查询关键词
            limit: 返回数量
            
        Returns:
            检索结果
        """
        keyword_results = await self.pg.search_fulltext(
            user_id=user_id,
            query=query,
            limit=limit,
        )
        
        return [
            SearchResult(
                memory=memory,
                keyword_score=score,
                final_score=score,
            )
            for memory, score in keyword_results
        ]
    
    # ========== 更新操作 ==========
    
    async def update(
        self,
        memory_id: UUID,
        **updates,
    ) -> Optional[Memory]:
        """
        更新记忆
        
        注意：content 更新会触发重新生成向量
        
        Args:
            memory_id: 记忆 ID
            **updates: 要更新的字段
            
        Returns:
            更新后的记忆
        """
        # 如果更新了 content，需要重新生成向量
        new_embedding = None
        if "content" in updates:
            new_embedding = await self.embedding.embed(updates["content"])
            updates["embedding"] = new_embedding
        
        # 更新 PG
        updated = await self.pg.update(memory_id, **updates)
        
        if updated and new_embedding:
            # 同步更新 Milvus（删除旧的，插入新的）
            try:
                await self.milvus.delete_memory_vector(memory_id)
                await self.milvus.insert_memory_vector(
                    memory_id=updated.id,
                    user_id=updated.user_id,
                    embedding=new_embedding,
                    memory_type=updated.memory_type.value,
                    importance=updated.importance,
                )
            except Exception as e:
                logger.error(f"Failed to update Milvus vector: {e}", exc_info=True)
        
        return updated
    
    async def touch(self, memory_id: UUID) -> None:
        """
        更新访问时间和计数
        
        Args:
            memory_id: 记忆 ID
        """
        await self.pg.touch(memory_id)
    
    async def update_importance(
        self,
        memory_id: UUID,
        importance: float,
    ) -> None:
        """
        更新重要性分数
        
        Args:
            memory_id: 记忆 ID
            importance: 新的重要性分数
        """
        await self.pg.update_importance(memory_id, importance)
        # 注：Milvus 中的 importance 仅用于过滤，不频繁同步
    
    # ========== 删除操作 ==========
    
    async def soft_delete(self, memory_id: UUID) -> bool:
        """
        软删除记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        success = await self.pg.soft_delete(memory_id)
        
        if success:
            # 同步删除 Milvus 中的向量
            try:
                await self.milvus.delete_memory_vector(memory_id)
            except Exception as e:
                logger.error(f"Failed to delete from Milvus: {e}", exc_info=True)
        
        return success
    
    async def hard_delete(self, memory_id: UUID) -> bool:
        """
        硬删除记忆（永久删除）
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        # 先删 Milvus
        try:
            await self.milvus.delete_memory_vector(memory_id)
        except Exception as e:
            logger.error(f"Failed to delete from Milvus: {e}", exc_info=True)
        
        # 再删 PG
        return await self.pg.hard_delete(memory_id)
    
    async def archive(self, memory_id: UUID) -> bool:
        """
        归档记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        success = await self.pg.archive(memory_id)
        
        if success:
            # 从 Milvus 删除（归档记忆不参与检索）
            try:
                await self.milvus.delete_memory_vector(memory_id)
            except Exception as e:
                logger.error(f"Failed to delete from Milvus on archive: {e}", exc_info=True)
        
        return success


# 导出
__all__ = [
    "PostgresMemoryStore",
    "MilvusMemoryStore",
    "EmbeddingService",
    "LongTermMemory",
    "SearchResult",
]