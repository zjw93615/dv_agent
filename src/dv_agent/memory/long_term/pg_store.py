"""
PostgreSQL Memory Store
长期记忆 PostgreSQL 存储

提供记忆的持久化存储，支持 CRUD 操作和全文检索
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..models import Memory, MemoryRelation, MemoryType, RelationType

logger = logging.getLogger(__name__)


class PostgresMemoryStore:
    """
    PostgreSQL 记忆存储
    
    负责：
    - 记忆的 CRUD 操作
    - 关系管理
    - 全文检索（TSVECTOR）
    - 软删除和归档
    """
    
    def __init__(
        self,
        pool: AsyncConnectionPool,
    ):
        """
        初始化存储
        
        Args:
            pool: PostgreSQL 连接池
        """
        self.pool = pool
    
    @classmethod
    async def create(
        cls,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
    ) -> "PostgresMemoryStore":
        """
        创建存储实例
        
        Args:
            dsn: PostgreSQL 连接字符串
            min_size: 最小连接数
            max_size: 最大连接数
            
        Returns:
            PostgresMemoryStore 实例
        """
        pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            open=False,
        )
        await pool.open()
        return cls(pool)
    
    async def close(self) -> None:
        """关闭连接池"""
        await self.pool.close()
    
    # ========== Create ==========
    
    async def create(self, memory: Memory) -> Memory:
        """
        创建记忆
        
        Args:
            memory: 记忆对象
            
        Returns:
            创建后的记忆（含数据库生成的字段）
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO user_memories (
                        id, user_id, memory_type, content,
                        source_session, source_turn,
                        confidence, importance, access_count, decay_rate,
                        created_at, updated_at, last_accessed,
                        metadata
                    ) VALUES (
                        %(id)s, %(user_id)s, %(memory_type)s, %(content)s,
                        %(source_session)s, %(source_turn)s,
                        %(confidence)s, %(importance)s, %(access_count)s, %(decay_rate)s,
                        %(created_at)s, %(updated_at)s, %(last_accessed)s,
                        %(metadata)s
                    )
                    RETURNING *
                    """,
                    {
                        "id": str(memory.id),
                        "user_id": memory.user_id,
                        "memory_type": memory.memory_type.value,
                        "content": memory.content,
                        "source_session": memory.source_session,
                        "source_turn": memory.source_turn,
                        "confidence": memory.confidence,
                        "importance": memory.importance,
                        "access_count": memory.access_count,
                        "decay_rate": memory.decay_rate,
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                        "last_accessed": memory.last_accessed,
                        "metadata": psycopg.types.json.Json(memory.metadata),
                    },
                )
                row = await cur.fetchone()
                
        logger.debug(f"Created memory {memory.id} for user {memory.user_id}")
        return self._row_to_memory(row)
    
    async def create_many(self, memories: list[Memory]) -> list[Memory]:
        """
        批量创建记忆
        
        Args:
            memories: 记忆列表
            
        Returns:
            创建后的记忆列表
        """
        if not memories:
            return []
        
        created = []
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                for memory in memories:
                    await cur.execute(
                        """
                        INSERT INTO user_memories (
                            id, user_id, memory_type, content,
                            source_session, source_turn,
                            confidence, importance, access_count, decay_rate,
                            created_at, updated_at, last_accessed,
                            metadata
                        ) VALUES (
                            %(id)s, %(user_id)s, %(memory_type)s, %(content)s,
                            %(source_session)s, %(source_turn)s,
                            %(confidence)s, %(importance)s, %(access_count)s, %(decay_rate)s,
                            %(created_at)s, %(updated_at)s, %(last_accessed)s,
                            %(metadata)s
                        )
                        RETURNING *
                        """,
                        {
                            "id": str(memory.id),
                            "user_id": memory.user_id,
                            "memory_type": memory.memory_type.value,
                            "content": memory.content,
                            "source_session": memory.source_session,
                            "source_turn": memory.source_turn,
                            "confidence": memory.confidence,
                            "importance": memory.importance,
                            "access_count": memory.access_count,
                            "decay_rate": memory.decay_rate,
                            "created_at": memory.created_at,
                            "updated_at": memory.updated_at,
                            "last_accessed": memory.last_accessed,
                            "metadata": psycopg.types.json.Json(memory.metadata),
                        },
                    )
                    row = await cur.fetchone()
                    created.append(self._row_to_memory(row))
        
        logger.info(f"Created {len(created)} memories")
        return created
    
    # ========== Read ==========
    
    async def get(self, memory_id: UUID) -> Optional[Memory]:
        """
        获取单条记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            记忆对象，不存在返回 None
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT * FROM user_memories
                    WHERE id = %s AND expired_at IS NULL
                    """,
                    (str(memory_id),),
                )
                row = await cur.fetchone()
        
        return self._row_to_memory(row) if row else None
    
    async def get_by_user(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
        offset: int = 0,
        include_expired: bool = False,
    ) -> list[Memory]:
        """
        获取用户的记忆列表
        
        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤（可选）
            limit: 返回数量限制
            offset: 偏移量
            include_expired: 是否包含已过期的
            
        Returns:
            记忆列表
        """
        conditions = ["user_id = %(user_id)s"]
        params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}
        
        if not include_expired:
            conditions.append("expired_at IS NULL")
        
        if memory_type:
            conditions.append("memory_type = %(memory_type)s")
            params["memory_type"] = memory_type.value
        
        where_clause = " AND ".join(conditions)
        
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""
                    SELECT * FROM user_memories
                    WHERE {where_clause}
                    ORDER BY importance DESC, created_at DESC
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    params,
                )
                rows = await cur.fetchall()
        
        return [self._row_to_memory(row) for row in rows]
    
    async def get_recent(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[Memory]:
        """
        获取最近访问的记忆
        
        Args:
            user_id: 用户 ID
            limit: 返回数量
            
        Returns:
            按最近访问排序的记忆列表
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT * FROM user_memories
                    WHERE user_id = %s AND expired_at IS NULL
                    ORDER BY COALESCE(last_accessed, created_at) DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = await cur.fetchall()
        
        return [self._row_to_memory(row) for row in rows]
    
    async def search_fulltext(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list[tuple[Memory, float]]:
        """
        全文检索
        
        使用 PostgreSQL TSVECTOR 进行全文检索
        
        Args:
            user_id: 用户 ID
            query: 检索查询
            limit: 返回数量
            
        Returns:
            (记忆, 相关性分数) 元组列表
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT *, ts_rank(content_tsv, plainto_tsquery('simple', %s)) AS rank
                    FROM user_memories
                    WHERE user_id = %s
                      AND expired_at IS NULL
                      AND content_tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    (query, user_id, query, limit),
                )
                rows = await cur.fetchall()
        
        results = []
        for row in rows:
            rank = row.pop("rank", 0.0)
            memory = self._row_to_memory(row)
            results.append((memory, float(rank)))
        
        return results
    
    # ========== Update ==========
    
    async def update(
        self,
        memory_id: UUID,
        **updates,
    ) -> Optional[Memory]:
        """
        更新记忆
        
        Args:
            memory_id: 记忆 ID
            **updates: 要更新的字段
            
        Returns:
            更新后的记忆
        """
        if not updates:
            return await self.get(memory_id)
        
        # 总是更新 updated_at
        updates["updated_at"] = datetime.utcnow()
        
        # 构建 SET 子句
        set_parts = []
        params: dict[str, Any] = {"id": str(memory_id)}
        
        for key, value in updates.items():
            if key == "metadata":
                set_parts.append(f"{key} = %({key})s::jsonb")
                params[key] = psycopg.types.json.Json(value)
            elif key == "memory_type" and isinstance(value, MemoryType):
                set_parts.append(f"{key} = %({key})s")
                params[key] = value.value
            else:
                set_parts.append(f"{key} = %({key})s")
                params[key] = value
        
        set_clause = ", ".join(set_parts)
        
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""
                    UPDATE user_memories
                    SET {set_clause}
                    WHERE id = %(id)s AND expired_at IS NULL
                    RETURNING *
                    """,
                    params,
                )
                row = await cur.fetchone()
        
        return self._row_to_memory(row) if row else None
    
    async def touch(self, memory_id: UUID) -> None:
        """
        更新访问时间和计数
        
        Args:
            memory_id: 记忆 ID
        """
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE user_memories
                    SET last_accessed = %s,
                        access_count = access_count + 1
                    WHERE id = %s
                    """,
                    (datetime.utcnow(), str(memory_id)),
                )
    
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
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE user_memories
                    SET importance = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (importance, datetime.utcnow(), str(memory_id)),
                )
    
    # ========== Delete (Soft) ==========
    
    async def soft_delete(self, memory_id: UUID) -> bool:
        """
        软删除记忆
        
        设置 expired_at 而不是真正删除
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                result = await cur.execute(
                    """
                    UPDATE user_memories
                    SET expired_at = %s
                    WHERE id = %s AND expired_at IS NULL
                    """,
                    (datetime.utcnow(), str(memory_id)),
                )
                return cur.rowcount > 0
    
    async def soft_delete_many(self, memory_ids: list[UUID]) -> int:
        """
        批量软删除
        
        Args:
            memory_ids: 记忆 ID 列表
            
        Returns:
            删除数量
        """
        if not memory_ids:
            return 0
        
        ids_str = [str(mid) for mid in memory_ids]
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE user_memories
                    SET expired_at = %s
                    WHERE id = ANY(%s) AND expired_at IS NULL
                    """,
                    (datetime.utcnow(), ids_str),
                )
                return cur.rowcount
    
    async def hard_delete(self, memory_id: UUID) -> bool:
        """
        硬删除记忆（永久删除）
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM user_memories WHERE id = %s",
                    (str(memory_id),),
                )
                return cur.rowcount > 0
    
    # ========== Archive ==========
    
    async def archive(self, memory_id: UUID) -> bool:
        """
        归档记忆
        
        将记忆移动到归档表
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功
        """
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 复制到归档表
                await cur.execute(
                    """
                    INSERT INTO user_memories_archive
                    SELECT *, NOW() as archived_at
                    FROM user_memories
                    WHERE id = %s
                    """,
                    (str(memory_id),),
                )
                
                if cur.rowcount > 0:
                    # 从主表删除
                    await cur.execute(
                        "DELETE FROM user_memories WHERE id = %s",
                        (str(memory_id),),
                    )
                    return True
                return False
    
    async def get_expired_memories(
        self,
        older_than_days: int = 30,
        limit: int = 100,
    ) -> list[Memory]:
        """
        获取过期的记忆（用于归档/删除）
        
        Args:
            older_than_days: 过期天数阈值
            limit: 返回数量
            
        Returns:
            过期的记忆列表
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT * FROM user_memories
                    WHERE expired_at IS NOT NULL
                      AND expired_at < NOW() - INTERVAL '%s days'
                    LIMIT %s
                    """,
                    (older_than_days, limit),
                )
                rows = await cur.fetchall()
        
        return [self._row_to_memory(row) for row in rows]
    
    # ========== Relations ==========
    
    async def create_relation(self, relation: MemoryRelation) -> MemoryRelation:
        """
        创建记忆关系
        
        Args:
            relation: 关系对象
            
        Returns:
            创建后的关系
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO memory_relations (
                        id, source_id, target_id, relation_type, strength, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, target_id, relation_type) 
                    DO UPDATE SET strength = EXCLUDED.strength
                    RETURNING *
                    """,
                    (
                        str(relation.id),
                        str(relation.source_id),
                        str(relation.target_id),
                        relation.relation_type.value,
                        relation.strength,
                        relation.created_at,
                    ),
                )
                row = await cur.fetchone()
        
        return MemoryRelation(
            id=UUID(row["id"]),
            source_id=UUID(row["source_id"]),
            target_id=UUID(row["target_id"]),
            relation_type=RelationType(row["relation_type"]),
            strength=row["strength"],
            created_at=row["created_at"],
        )
    
    async def get_related_memories(
        self,
        memory_id: UUID,
        relation_type: Optional[RelationType] = None,
    ) -> list[tuple[Memory, MemoryRelation]]:
        """
        获取相关记忆
        
        Args:
            memory_id: 源记忆 ID
            relation_type: 关系类型过滤（可选）
            
        Returns:
            (记忆, 关系) 元组列表
        """
        conditions = ["r.source_id = %(source_id)s"]
        params: dict[str, Any] = {"source_id": str(memory_id)}
        
        if relation_type:
            conditions.append("r.relation_type = %(relation_type)s")
            params["relation_type"] = relation_type.value
        
        where_clause = " AND ".join(conditions)
        
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""
                    SELECT m.*, r.id as rel_id, r.source_id, r.target_id,
                           r.relation_type, r.strength, r.created_at as rel_created_at
                    FROM user_memories m
                    JOIN memory_relations r ON m.id = r.target_id
                    WHERE {where_clause}
                      AND m.expired_at IS NULL
                    ORDER BY r.strength DESC
                    """,
                    params,
                )
                rows = await cur.fetchall()
        
        results = []
        for row in rows:
            # 分离关系字段
            rel_data = {
                "id": row.pop("rel_id"),
                "source_id": row.pop("source_id"),
                "target_id": row.pop("target_id"),
                "relation_type": row.pop("relation_type"),
                "strength": row.pop("strength"),
                "created_at": row.pop("rel_created_at"),
            }
            
            memory = self._row_to_memory(row)
            relation = MemoryRelation(
                id=UUID(rel_data["id"]),
                source_id=UUID(rel_data["source_id"]),
                target_id=UUID(rel_data["target_id"]),
                relation_type=RelationType(rel_data["relation_type"]),
                strength=rel_data["strength"],
                created_at=rel_data["created_at"],
            )
            results.append((memory, relation))
        
        return results
    
    # ========== Helpers ==========
    
    def _row_to_memory(self, row: dict) -> Memory:
        """将数据库行转换为 Memory 对象"""
        return Memory(
            id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            user_id=row["user_id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            source_session=row.get("source_session"),
            source_turn=row.get("source_turn"),
            confidence=row["confidence"],
            importance=row["importance"],
            access_count=row["access_count"],
            decay_rate=row["decay_rate"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed=row.get("last_accessed"),
            expired_at=row.get("expired_at"),
            metadata=row.get("metadata") or {},
        )
    
    async def count_by_user(self, user_id: str) -> int:
        """获取用户记忆总数"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM user_memories
                    WHERE user_id = %s AND expired_at IS NULL
                    """,
                    (user_id,),
                )
                result = await cur.fetchone()
                return result[0] if result else 0
