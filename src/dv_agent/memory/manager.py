"""
Memory Manager
记忆管理器 - 统一入口

整合短期记忆、长期记忆、检索和生命周期管理，
提供统一的记忆操作接口。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from .config import MemoryConfig
from .models import Memory, MemoryType
from .short_term import ShortTermMemory
from .long_term import LongTermMemory, SearchResult
from .retrieval import MemoryRetriever, RetrievalQuery, RetrievalResult, CrossEncoderReranker
from .lifecycle import MemoryExtractor, ImportanceUpdater, MemoryForgetter

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    """记忆上下文"""
    # 短期记忆
    short_term_messages: list[dict[str, str]]
    summary: Optional[str] = None
    
    # 长期记忆
    long_term_memories: list[Memory] = None
    
    # 元信息
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # 兼容别名
    @property
    def recent_messages(self) -> list[dict[str, str]]:
        return self.short_term_messages
    
    @property
    def relevant_memories(self) -> list[Memory]:
        return self.long_term_memories
    
    def __post_init__(self):
        if self.long_term_memories is None:
            self.long_term_memories = []
    
    def to_prompt_context(self) -> str:
        """
        转换为可插入 Prompt 的上下文字符串
        
        Returns:
            格式化的上下文
        """
        parts = []
        
        # 会话摘要
        if self.summary:
            parts.append(f"## 会话摘要\n{self.summary}")
        
        # 相关记忆
        if self.relevant_memories:
            memory_lines = []
            for result in self.relevant_memories[:5]:
                memory_lines.append(f"- {result.memory.content}")
            
            if memory_lines:
                parts.append("## 相关记忆\n" + "\n".join(memory_lines))
        
        return "\n\n".join(parts)


class MemoryManager:
    """
    记忆管理器
    
    统一管理短期记忆和长期记忆的主入口类。
    
    主要功能：
    - add_to_short_term(): 添加消息到短期记忆
    - get_context(): 获取完整上下文（摘要 + 相关记忆）
    - retrieve(): 检索相关记忆
    - extract_and_store(): 提取并存储长期记忆
    """
    
    def __init__(
        self,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        retriever: MemoryRetriever,
        extractor: MemoryExtractor,
        updater: Optional[ImportanceUpdater] = None,
        forgetter: Optional[MemoryForgetter] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        config: Optional[MemoryConfig] = None,
    ):
        """
        初始化管理器
        
        Args:
            short_term: 短期记忆
            long_term: 长期记忆
            retriever: 检索器
            extractor: 提取器
            updater: 重要性更新器
            forgetter: 遗忘器
            reranker: 重排序器
            config: 配置
        """
        self.short_term = short_term
        self.long_term = long_term
        self.retriever = retriever
        self.extractor = extractor
        self.updater = updater
        self.forgetter = forgetter
        self.reranker = reranker
        self.config = config or MemoryConfig()
    
    @classmethod
    async def create(
        cls,
        redis_client,
        llm_client,
        pg_dsn: str,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        config: Optional[MemoryConfig] = None,
    ) -> "MemoryManager":
        """
        创建 MemoryManager 实例
        
        Args:
            redis_client: Redis 客户端
            llm_client: LLM 客户端
            pg_dsn: PostgreSQL 连接字符串
            milvus_host: Milvus 服务器地址
            milvus_port: Milvus 服务器端口
            config: 配置
            
        Returns:
            MemoryManager 实例
        """
        config = config or MemoryConfig()
        
        # 初始化各组件
        short_term = ShortTermMemory(
            redis_client=redis_client,
            llm_client=llm_client,
            config=config,
        )
        
        long_term = await LongTermMemory.create(
            pg_dsn=pg_dsn,
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            config=config,
        )
        
        retriever = MemoryRetriever(
            long_term=long_term,
            redis_client=redis_client,
            config=config,
        )
        
        extractor = MemoryExtractor(
            llm_client=llm_client,
        )
        
        updater = ImportanceUpdater(pg_store=long_term.pg)
        
        forgetter = MemoryForgetter(
            pg_store=long_term.pg,
            milvus_store=long_term.milvus,
        )
        
        reranker = CrossEncoderReranker()
        
        logger.info("MemoryManager initialized successfully")
        
        return cls(
            short_term=short_term,
            long_term=long_term,
            retriever=retriever,
            extractor=extractor,
            updater=updater,
            forgetter=forgetter,
            reranker=reranker,
            config=config,
        )
    
    async def close(self) -> None:
        """关闭所有连接"""
        await self.long_term.close()
        if self.reranker:
            self.reranker.close()
        logger.info("MemoryManager closed")
    
    # ========== 短期记忆操作 ==========
    
    async def add_to_short_term(
        self,
        session_id: str,
        message: dict[str, str],
    ) -> bool:
        """
        添加消息到短期记忆
        
        Args:
            session_id: 会话 ID
            message: 消息 {"role": "user/assistant", "content": "..."}
            
        Returns:
            是否触发了压缩
        """
        return await self.short_term.add_message(session_id, message)
    
    async def get_short_term_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """
        获取短期记忆中的消息
        
        Args:
            session_id: 会话 ID
            limit: 返回数量限制
            
        Returns:
            消息列表
        """
        return await self.short_term.get_messages(session_id, limit)
    
    async def get_summary(self, session_id: str) -> Optional[str]:
        """
        获取会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            摘要文本
        """
        return await self.short_term.get_summary(session_id)
    
    async def compress_short_term(self, session_id: str) -> bool:
        """
        压缩短期记忆
        
        强制触发压缩，将当前消息窗口压缩为摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功压缩
        """
        try:
            # 获取当前消息
            messages = await self.short_term.get_messages(session_id)
            
            if not messages:
                return False
            
            # 获取现有摘要
            existing_summary = await self.short_term.get_summary(session_id)
            
            # 触发压缩
            new_summary = await self.short_term.compress_messages(
                session_id=session_id,
                messages=messages,
                existing_summary=existing_summary,
            )
            
            logger.info(
                f"Compressed short-term memory for session {session_id}",
                message_count=len(messages),
                summary_length=len(new_summary) if new_summary else 0,
            )
            
            return True
        except Exception as e:
            logger.error(
                f"Failed to compress short-term memory: {e}",
                session_id=session_id,
            )
            return False
    
    # ========== 上下文获取 ==========
    
    async def get_context(
        self,
        session_id: str,
        user_id: str,
        query: Optional[str] = None,
        include_summary: bool = True,
        include_memories: bool = True,
        memory_top_k: int = 5,
    ) -> MemoryContext:
        """
        获取完整的记忆上下文
        
        融合短期记忆摘要和相关长期记忆
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            query: 检索查询（用于获取相关记忆）
            include_summary: 是否包含摘要
            include_memories: 是否包含长期记忆
            memory_top_k: 返回的记忆数量
            
        Returns:
            记忆上下文
        """
        # 并行获取各部分
        tasks = []
        
        # 短期记忆
        tasks.append(self.short_term.get_messages(session_id))
        
        # 摘要
        if include_summary:
            tasks.append(self.short_term.get_summary(session_id))
        else:
            tasks.append(asyncio.coroutine(lambda: None)())
        
        # 长期记忆
        if include_memories and query:
            tasks.append(self._retrieve_relevant_memories(
                user_id=user_id,
                query=query,
                top_k=memory_top_k,
            ))
        else:
            tasks.append(asyncio.coroutine(lambda: [])())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        messages = results[0] if not isinstance(results[0], Exception) else []
        summary = results[1] if not isinstance(results[1], Exception) else None
        memories = results[2] if not isinstance(results[2], Exception) else []
        
        # 更新访问记录
        if memories:
            asyncio.create_task(self._touch_memories(memories))
        
        # 提取 Memory 对象
        memory_objects = [r.memory for r in memories] if memories else []
        
        return MemoryContext(
            short_term_messages=messages,
            summary=summary,
            long_term_memories=memory_objects,
            user_id=user_id,
            session_id=session_id,
        )
    
    async def _retrieve_relevant_memories(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        """
        检索相关记忆
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            检索结果
        """
        retrieval_query = RetrievalQuery(
            user_id=user_id,
            query=query,
            top_k=top_k * 2,  # 多取一些用于重排
        )
        
        result = await self.retriever.retrieve(retrieval_query)
        
        # 使用 reranker 重排序
        if self.reranker and result.results:
            reranked = await self.reranker.rerank(
                query=query,
                results=result.results,
                top_k=top_k,
            )
            # 转换回 SearchResult
            return [
                SearchResult(
                    memory=r.memory,
                    final_score=r.final_score,
                )
                for r in reranked
            ]
        
        return result.results[:top_k]
    
    async def _touch_memories(self, memories: list[SearchResult]) -> None:
        """更新记忆访问时间"""
        for result in memories:
            try:
                await self.long_term.touch(result.memory.id)
            except Exception as e:
                logger.warning(f"Failed to touch memory {result.memory.id}: {e}")
    
    # ========== 检索操作 ==========
    
    async def retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = 10,
        memory_types: Optional[list[MemoryType]] = None,
        use_reranker: bool = True,
    ) -> list[SearchResult]:
        """
        检索用户记忆
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回数量
            memory_types: 记忆类型过滤
            use_reranker: 是否使用重排序
            
        Returns:
            检索结果
        """
        retrieval_query = RetrievalQuery(
            user_id=user_id,
            query=query,
            top_k=top_k * 2 if use_reranker else top_k,
            memory_types=memory_types,
        )
        
        result = await self.retriever.retrieve(retrieval_query)
        
        if use_reranker and self.reranker and result.results:
            reranked = await self.reranker.rerank(
                query=query,
                results=result.results,
                top_k=top_k,
            )
            return [
                SearchResult(
                    memory=r.memory,
                    final_score=r.final_score,
                )
                for r in reranked
            ]
        
        return result.results[:top_k]
    
    # ========== 提取与存储 ==========
    
    async def extract_and_store(
        self,
        conversation: list[dict[str, str]],
        user_id: str,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
    ) -> list[Memory]:
        """
        从对话中提取记忆并存储
        
        Args:
            conversation: 对话消息列表
            user_id: 用户 ID
            session_id: 会话 ID
            turn_id: 轮次 ID
            
        Returns:
            存储的记忆列表
        """
        # 获取用户已有记忆（用于去重）
        existing = await self.long_term.get_by_user(user_id, limit=100)
        self.extractor.existing_memories = existing
        
        # 提取记忆
        extraction_result = await self.extractor.extract(
            conversation=conversation,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
        )
        
        if extraction_result.has_errors:
            logger.warning(
                f"Memory extraction had errors: {extraction_result.errors}"
            )
        
        if not extraction_result.memories:
            return []
        
        # 存储到长期记忆
        stored = await self.long_term.store_many(extraction_result.memories)
        
        # 使检索缓存失效
        await self.retriever.invalidate_cache(user_id)
        
        logger.info(
            f"Extracted and stored {len(stored)} memories for user {user_id}"
        )
        
        return stored
    
    # ========== 记忆管理 ==========
    
    async def get_user_memories(
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
        return await self.long_term.get_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
    
    async def update_memory(
        self,
        memory_id: UUID,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        permanent: Optional[bool] = None,
    ) -> Optional[Memory]:
        """
        更新记忆
        
        Args:
            memory_id: 记忆 ID
            content: 新内容
            importance: 新重要性
            permanent: 是否标记为永久
            
        Returns:
            更新后的记忆
        """
        updates = {}
        
        if content is not None:
            updates["content"] = content
        
        if importance is not None:
            updates["importance"] = importance
        
        if permanent is not None:
            # 需要先获取现有 metadata
            memory = await self.long_term.get(memory_id)
            if memory:
                metadata = memory.metadata.copy()
                metadata["permanent"] = permanent
                updates["metadata"] = metadata
        
        if updates:
            return await self.long_term.update(memory_id, **updates)
        
        return await self.long_term.get(memory_id)
    
    async def delete_memory(
        self,
        memory_id: UUID,
        hard_delete: bool = False,
    ) -> bool:
        """
        删除记忆
        
        Args:
            memory_id: 记忆 ID
            hard_delete: 是否硬删除
            
        Returns:
            是否成功
        """
        if hard_delete:
            return await self.long_term.hard_delete(memory_id)
        else:
            return await self.long_term.soft_delete(memory_id)
    
    # ========== 后台任务入口 ==========
    
    async def run_maintenance(self, user_id: Optional[str] = None) -> dict[str, Any]:
        """
        运行维护任务
        
        Args:
            user_id: 限定用户（可选）
            
        Returns:
            统计信息
        """
        stats = {}
        
        # 更新重要性
        if self.updater:
            update_stats = await self.updater.batch_update(user_id)
            stats["importance_update"] = update_stats
        
        # 遗忘周期
        if self.forgetter:
            forget_result = await self.forgetter.run_forget_cycle(user_id)
            stats["forget"] = {
                "soft_forgotten": forget_result.soft_forgotten,
                "archived": forget_result.archived,
                "hard_deleted": forget_result.hard_deleted,
            }
        
        return stats
