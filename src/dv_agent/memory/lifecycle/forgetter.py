"""
Memory Forgetter
记忆遗忘器 - 实现三级遗忘策略

三级遗忘机制：
1. 软遗忘 (Soft Forget): 标记 expired_at，不再参与检索，但数据保留
2. 归档 (Archive): 移动到 archive 表，可恢复
3. 硬删除 (Hard Delete): 永久删除，不可恢复

遗忘豁免：
- 用户标记为永久的记忆
- 高于重要性阈值的记忆
- 最近访问过的记忆
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from ..long_term.pg_store import PostgresMemoryStore
from ..long_term.milvus_store import MilvusMemoryStore
from ..models import Memory

logger = logging.getLogger(__name__)


@dataclass
class ForgetPolicy:
    """遗忘策略配置"""
    # 软遗忘阈值
    soft_forget_importance: float = 0.1  # 重要性低于此值触发软遗忘
    soft_forget_days: int = 30           # 超过此天数未访问触发软遗忘
    
    # 归档阈值
    archive_after_soft_days: int = 30    # 软遗忘后多少天归档
    
    # 硬删除阈值
    hard_delete_after_archive_days: int = 90  # 归档后多少天硬删除
    
    # 豁免条件
    exempt_importance: float = 0.8       # 高于此重要性免于遗忘
    exempt_access_days: int = 7          # 最近N天访问过的免于遗忘
    
    # 批处理配置
    batch_size: int = 100                # 每批处理数量


@dataclass
class ForgetResult:
    """遗忘操作结果"""
    soft_forgotten: int = 0
    archived: int = 0
    hard_deleted: int = 0
    exempted: int = 0
    errors: int = 0
    
    @property
    def total_processed(self) -> int:
        return self.soft_forgotten + self.archived + self.hard_deleted + self.exempted


class MemoryForgetter:
    """
    记忆遗忘器
    
    实现渐进式遗忘策略，模拟人类记忆的自然遗忘过程。
    
    遗忘流程：
    活跃记忆 -> [软遗忘] -> 已过期 -> [归档] -> 归档表 -> [硬删除] -> 永久删除
    
    豁免规则：
    - permanent=true 的记忆永不遗忘
    - 高重要性记忆跳过遗忘
    - 最近访问的记忆跳过遗忘
    """
    
    def __init__(
        self,
        pg_store: PostgresMemoryStore,
        milvus_store: Optional[MilvusMemoryStore] = None,
        policy: Optional[ForgetPolicy] = None,
    ):
        """
        初始化遗忘器
        
        Args:
            pg_store: PostgreSQL 存储
            milvus_store: Milvus 存储（用于删除向量）
            policy: 遗忘策略
        """
        self.pg = pg_store
        self.milvus = milvus_store
        self.policy = policy or ForgetPolicy()
    
    async def run_forget_cycle(
        self,
        user_id: Optional[str] = None,
    ) -> ForgetResult:
        """
        执行完整的遗忘周期
        
        Args:
            user_id: 限定用户（可选）
            
        Returns:
            遗忘结果
        """
        result = ForgetResult()
        
        # 1. 执行软遗忘
        soft_result = await self._soft_forget(user_id)
        result.soft_forgotten = soft_result["forgotten"]
        result.exempted += soft_result["exempted"]
        result.errors += soft_result["errors"]
        
        # 2. 执行归档
        archive_result = await self._archive_expired(user_id)
        result.archived = archive_result["archived"]
        result.errors += archive_result["errors"]
        
        # 3. 执行硬删除
        delete_result = await self._hard_delete_archived(user_id)
        result.hard_deleted = delete_result["deleted"]
        result.errors += delete_result["errors"]
        
        logger.info(
            f"Forget cycle completed: soft={result.soft_forgotten}, "
            f"archive={result.archived}, delete={result.hard_deleted}, "
            f"exempt={result.exempted}, errors={result.errors}"
        )
        
        return result
    
    async def _soft_forget(
        self,
        user_id: Optional[str] = None,
    ) -> dict[str, int]:
        """
        执行软遗忘
        
        将低重要性或长期未访问的记忆标记为过期
        
        Args:
            user_id: 限定用户
            
        Returns:
            统计信息
        """
        stats = {"forgotten": 0, "exempted": 0, "errors": 0}
        
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=self.policy.soft_forget_days)
        
        # 获取候选记忆
        candidates = await self.pg.get_forget_candidates(
            user_id=user_id,
            max_importance=self.policy.soft_forget_importance,
            last_accessed_before=cutoff_date,
            limit=self.policy.batch_size,
        )
        
        for memory in candidates:
            try:
                # 检查豁免条件
                if self._is_exempt(memory, now):
                    stats["exempted"] += 1
                    continue
                
                # 执行软遗忘
                success = await self.pg.soft_delete(memory.id)
                if success:
                    # 同步删除 Milvus 向量
                    if self.milvus:
                        try:
                            await self.milvus.delete_memory_vector(memory.id)
                        except Exception as e:
                            logger.warning(f"Failed to delete Milvus vector: {e}")
                    
                    stats["forgotten"] += 1
                    logger.debug(f"Soft forgot memory {memory.id}")
                    
            except Exception as e:
                logger.warning(f"Failed to soft forget memory {memory.id}: {e}")
                stats["errors"] += 1
        
        return stats
    
    async def _archive_expired(
        self,
        user_id: Optional[str] = None,
    ) -> dict[str, int]:
        """
        归档已过期的记忆
        
        将软遗忘后超过一定时间的记忆移动到归档表
        
        Args:
            user_id: 限定用户
            
        Returns:
            统计信息
        """
        stats = {"archived": 0, "errors": 0}
        
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=self.policy.archive_after_soft_days)
        
        # 获取待归档记忆
        expired_memories = await self.pg.get_expired_memories(
            user_id=user_id,
            expired_before=cutoff_date,
            limit=self.policy.batch_size,
        )
        
        for memory in expired_memories:
            try:
                success = await self.pg.archive(memory.id)
                if success:
                    stats["archived"] += 1
                    logger.debug(f"Archived memory {memory.id}")
                    
            except Exception as e:
                logger.warning(f"Failed to archive memory {memory.id}: {e}")
                stats["errors"] += 1
        
        return stats
    
    async def _hard_delete_archived(
        self,
        user_id: Optional[str] = None,
    ) -> dict[str, int]:
        """
        硬删除归档记忆
        
        将归档超过一定时间的记忆永久删除
        
        Args:
            user_id: 限定用户
            
        Returns:
            统计信息
        """
        stats = {"deleted": 0, "errors": 0}
        
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=self.policy.hard_delete_after_archive_days)
        
        # 获取待删除的归档记忆
        archived_memories = await self.pg.get_old_archived_memories(
            user_id=user_id,
            archived_before=cutoff_date,
            limit=self.policy.batch_size,
        )
        
        for memory in archived_memories:
            try:
                success = await self.pg.hard_delete_archived(memory.id)
                if success:
                    stats["deleted"] += 1
                    logger.debug(f"Hard deleted archived memory {memory.id}")
                    
            except Exception as e:
                logger.warning(f"Failed to hard delete memory {memory.id}: {e}")
                stats["errors"] += 1
        
        return stats
    
    def _is_exempt(self, memory: Memory, now: datetime) -> bool:
        """
        检查记忆是否豁免遗忘
        
        Args:
            memory: 记忆对象
            now: 当前时间
            
        Returns:
            是否豁免
        """
        # 永久记忆豁免
        if memory.metadata.get("permanent", False):
            return True
        
        # 高重要性豁免
        if memory.importance >= self.policy.exempt_importance:
            return True
        
        # 最近访问豁免
        if memory.last_accessed:
            days_since_access = (now - memory.last_accessed).days
            if days_since_access <= self.policy.exempt_access_days:
                return True
        
        return False
    
    async def restore_memory(self, memory_id: UUID) -> Optional[Memory]:
        """
        恢复软遗忘的记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            恢复后的记忆
        """
        memory = await self.pg.restore(memory_id)
        
        if memory and memory.embedding and self.milvus:
            # 重新插入 Milvus
            try:
                await self.milvus.insert_memory_vector(
                    memory_id=memory.id,
                    user_id=memory.user_id,
                    embedding=memory.embedding,
                    memory_type=memory.memory_type.value,
                    importance=memory.importance,
                )
            except Exception as e:
                logger.warning(f"Failed to restore Milvus vector: {e}")
        
        return memory
    
    async def restore_from_archive(self, memory_id: UUID) -> Optional[Memory]:
        """
        从归档恢复记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            恢复后的记忆
        """
        memory = await self.pg.restore_from_archive(memory_id)
        
        if memory and memory.embedding and self.milvus:
            # 重新插入 Milvus
            try:
                await self.milvus.insert_memory_vector(
                    memory_id=memory.id,
                    user_id=memory.user_id,
                    embedding=memory.embedding,
                    memory_type=memory.memory_type.value,
                    importance=memory.importance,
                )
            except Exception as e:
                logger.warning(f"Failed to restore Milvus vector: {e}")
        
        return memory
    
    async def force_forget(
        self,
        memory_id: UUID,
        hard_delete: bool = False,
    ) -> bool:
        """
        强制遗忘指定记忆
        
        忽略豁免规则，直接遗忘
        
        Args:
            memory_id: 记忆 ID
            hard_delete: 是否直接硬删除
            
        Returns:
            是否成功
        """
        if hard_delete:
            # 直接硬删除
            if self.milvus:
                try:
                    await self.milvus.delete_memory_vector(memory_id)
                except Exception as e:
                    logger.warning(f"Failed to delete Milvus vector: {e}")
            
            return await self.pg.hard_delete(memory_id)
        else:
            # 软遗忘
            success = await self.pg.soft_delete(memory_id)
            
            if success and self.milvus:
                try:
                    await self.milvus.delete_memory_vector(memory_id)
                except Exception as e:
                    logger.warning(f"Failed to delete Milvus vector: {e}")
            
            return success
    
    async def check_duplicates(
        self,
        user_id: str,
        similarity_threshold: float = 0.9,
    ) -> list[tuple[Memory, Memory, float]]:
        """
        检测重复记忆
        
        Args:
            user_id: 用户 ID
            similarity_threshold: 相似度阈值
            
        Returns:
            重复记忆对列表 [(memory1, memory2, similarity)]
        """
        duplicates = []
        
        memories = await self.pg.get_by_user(user_id, limit=1000)
        
        for i, m1 in enumerate(memories):
            for m2 in memories[i + 1:]:
                similarity = self._text_similarity(m1.content, m2.content)
                
                if similarity >= similarity_threshold:
                    duplicates.append((m1, m2, similarity))
        
        return duplicates
    
    async def merge_duplicates(
        self,
        memory1_id: UUID,
        memory2_id: UUID,
        keep_first: bool = True,
    ) -> Optional[Memory]:
        """
        合并重复记忆
        
        保留一个，删除另一个，合并元数据
        
        Args:
            memory1_id: 记忆1 ID
            memory2_id: 记忆2 ID
            keep_first: 是否保留第一个
            
        Returns:
            保留的记忆
        """
        m1 = await self.pg.get(memory1_id)
        m2 = await self.pg.get(memory2_id)
        
        if not m1 or not m2:
            return None
        
        keep, delete = (m1, m2) if keep_first else (m2, m1)
        
        # 合并元数据
        merged_metadata = {**delete.metadata, **keep.metadata}
        merged_metadata["merged_from"] = str(delete.id)
        
        # 取最高重要性
        new_importance = max(keep.importance, delete.importance)
        
        # 合并访问次数
        new_access_count = keep.access_count + delete.access_count
        
        # 更新保留的记忆
        await self.pg.update(
            keep.id,
            importance=new_importance,
            access_count=new_access_count,
            metadata=merged_metadata,
        )
        
        # 删除重复的
        await self.force_forget(delete.id, hard_delete=True)
        
        return await self.pg.get(keep.id)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            Jaccard 相似度
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
