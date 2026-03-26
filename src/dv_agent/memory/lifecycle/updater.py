"""
Importance Updater
重要性更新器 - 动态调整记忆的重要性权重

基于多种信号动态更新记忆的重要性分数：
- 访问频率
- 时间衰减
- 用户反馈
- 关联强度
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from ..long_term.pg_store import PostgresMemoryStore
from ..models import Memory

logger = logging.getLogger(__name__)


@dataclass
class ImportanceFactors:
    """重要性计算因子"""
    # 基础权重
    base_importance: float = 0.5
    
    # 访问频率因子
    access_frequency: float = 0.0
    
    # 时间衰减因子
    time_decay: float = 1.0
    
    # 显式强化（用户标记重要）
    explicit_boost: float = 0.0
    
    # 关联强度（与其他记忆的关联数）
    relation_strength: float = 0.0
    
    # 最终分数
    final_score: float = 0.0


class ImportanceUpdater:
    """
    重要性更新器
    
    使用加权公式计算记忆的综合重要性：
    
    importance = base * time_decay + α * access_freq + β * relation + γ * boost
    
    其中：
    - base: 初始重要性
    - time_decay: 时间衰减函数 exp(-λt)
    - access_freq: 访问频率归一化
    - relation: 关联记忆数量归一化
    - boost: 用户显式标记
    """
    
    # 权重参数
    ACCESS_WEIGHT = 0.2      # α: 访问频率权重
    RELATION_WEIGHT = 0.1    # β: 关联强度权重
    BOOST_WEIGHT = 0.3       # γ: 显式强化权重
    
    # 衰减参数
    DECAY_LAMBDA = 0.001     # λ: 衰减速率（每天）
    
    # 归一化参数
    MAX_ACCESS_COUNT = 100   # 访问次数上限（归一化用）
    MAX_RELATION_COUNT = 20  # 关联数量上限（归一化用）
    
    def __init__(
        self,
        pg_store: PostgresMemoryStore,
    ):
        """
        初始化更新器
        
        Args:
            pg_store: PostgreSQL 存储
        """
        self.pg = pg_store
    
    async def update_importance(
        self,
        memory_id: UUID,
        explicit_boost: Optional[float] = None,
    ) -> Optional[float]:
        """
        更新单条记忆的重要性
        
        Args:
            memory_id: 记忆 ID
            explicit_boost: 显式强化值（用户标记）
            
        Returns:
            新的重要性分数
        """
        # 获取记忆
        memory = await self.pg.get(memory_id)
        if not memory:
            logger.warning(f"Memory {memory_id} not found")
            return None
        
        # 计算因子
        factors = await self._calculate_factors(memory, explicit_boost)
        
        # 更新数据库
        await self.pg.update_importance(memory_id, factors.final_score)
        
        logger.debug(
            f"Updated importance for memory {memory_id}: "
            f"{memory.importance:.3f} -> {factors.final_score:.3f}"
        )
        
        return factors.final_score
    
    async def batch_update(
        self,
        user_id: Optional[str] = None,
        limit: int = 1000,
    ) -> dict[str, int]:
        """
        批量更新重要性（用于定时任务）
        
        Args:
            user_id: 限定用户（可选）
            limit: 每批处理数量
            
        Returns:
            统计信息 {"updated": N, "errors": M}
        """
        stats = {"updated": 0, "errors": 0}
        
        # 获取待更新的记忆
        if user_id:
            memories = await self.pg.get_by_user(user_id, limit=limit)
        else:
            # 获取所有活跃记忆（最近30天有访问）
            memories = await self.pg.get_active_memories(
                days=30,
                limit=limit,
            )
        
        for memory in memories:
            try:
                factors = await self._calculate_factors(memory)
                
                # 只有变化超过阈值才更新
                if abs(factors.final_score - memory.importance) > 0.01:
                    await self.pg.update_importance(memory.id, factors.final_score)
                    stats["updated"] += 1
                    
            except Exception as e:
                logger.warning(f"Failed to update memory {memory.id}: {e}")
                stats["errors"] += 1
        
        logger.info(
            f"Batch importance update completed: "
            f"updated={stats['updated']}, errors={stats['errors']}"
        )
        
        return stats
    
    async def _calculate_factors(
        self,
        memory: Memory,
        explicit_boost: Optional[float] = None,
    ) -> ImportanceFactors:
        """
        计算重要性因子
        
        Args:
            memory: 记忆对象
            explicit_boost: 显式强化值
            
        Returns:
            重要性因子
        """
        factors = ImportanceFactors(base_importance=memory.importance)
        
        # 1. 时间衰减
        now = datetime.utcnow()
        age_days = (now - memory.created_at).days
        decay_rate = memory.decay_rate or self.DECAY_LAMBDA
        factors.time_decay = math.exp(-decay_rate * age_days)
        
        # 2. 访问频率（归一化到 [0, 1]）
        factors.access_frequency = min(
            memory.access_count / self.MAX_ACCESS_COUNT,
            1.0
        )
        
        # 3. 关联强度
        try:
            relation_count = await self.pg.count_relations(memory.id)
            factors.relation_strength = min(
                relation_count / self.MAX_RELATION_COUNT,
                1.0
            )
        except Exception:
            factors.relation_strength = 0.0
        
        # 4. 显式强化
        if explicit_boost is not None:
            factors.explicit_boost = max(0.0, min(1.0, explicit_boost))
        elif memory.metadata.get("permanent", False):
            # 标记为永久的记忆
            factors.explicit_boost = 1.0
        
        # 计算最终分数
        factors.final_score = self._compute_final_score(factors)
        
        return factors
    
    def _compute_final_score(self, factors: ImportanceFactors) -> float:
        """
        计算最终重要性分数
        
        公式：
        score = base * decay + α * access + β * relation + γ * boost
        
        Args:
            factors: 重要性因子
            
        Returns:
            最终分数 [0, 1]
        """
        # 基础分数（受时间衰减影响）
        base_score = factors.base_importance * factors.time_decay
        
        # 加权求和
        score = (
            base_score +
            self.ACCESS_WEIGHT * factors.access_frequency +
            self.RELATION_WEIGHT * factors.relation_strength +
            self.BOOST_WEIGHT * factors.explicit_boost
        )
        
        # 归一化到 [0, 1]
        return max(0.0, min(1.0, score))
    
    async def recalculate_all(
        self,
        user_id: str,
        reset_base: bool = False,
    ) -> int:
        """
        重新计算用户所有记忆的重要性
        
        Args:
            user_id: 用户 ID
            reset_base: 是否重置基础分数
            
        Returns:
            更新的记忆数量
        """
        memories = await self.pg.get_by_user(user_id, limit=10000)
        updated = 0
        
        for memory in memories:
            try:
                if reset_base:
                    # 重置为默认基础分数
                    memory.importance = 0.5
                
                factors = await self._calculate_factors(memory)
                await self.pg.update_importance(memory.id, factors.final_score)
                updated += 1
                
            except Exception as e:
                logger.warning(f"Failed to recalculate memory {memory.id}: {e}")
        
        logger.info(f"Recalculated importance for {updated} memories of user {user_id}")
        return updated
    
    def calculate_expected_lifetime(
        self,
        importance: float,
        decay_rate: float = DECAY_LAMBDA,
        threshold: float = 0.1,
    ) -> int:
        """
        计算记忆的预期生命周期（天数）
        
        基于当前重要性和衰减率，预测记忆何时会低于阈值。
        
        Args:
            importance: 当前重要性
            decay_rate: 衰减率
            threshold: 阈值
            
        Returns:
            预期天数
        """
        if importance <= threshold:
            return 0
        
        if decay_rate <= 0:
            return 365 * 100  # 永久
        
        # I * e^(-λt) = threshold
        # t = -ln(threshold/I) / λ
        try:
            days = -math.log(threshold / importance) / decay_rate
            return int(max(0, days))
        except (ValueError, ZeroDivisionError):
            return 0
