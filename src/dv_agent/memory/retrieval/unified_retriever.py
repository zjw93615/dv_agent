"""
Unified Retriever
统一检索器 - 整合记忆检索与文档检索

将对话记忆检索（Memory）与知识文档检索（RAG）统一为一个检索接口，
使 Agent 能够同时利用历史对话和外部知识进行回答。

检索流程：
1. 并行执行记忆检索和文档检索
2. 对结果进行跨源融合
3. 重排序生成最终上下文

使用场景：
- Agent 需要同时参考历史对话和知识库
- 复杂问答需要多源信息支撑
- 知识增强的对话场景
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from ..config import MemoryConfig
from ..long_term import LongTermMemory
from ..models import Memory
from .retriever import MemoryRetriever, RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """检索来源类型"""
    MEMORY = "memory"      # 对话记忆
    DOCUMENT = "document"  # 知识文档
    HYBRID = "hybrid"      # 混合来源


@dataclass
class UnifiedQuery:
    """统一检索查询"""
    user_id: str
    tenant_id: str
    query: str
    
    # 检索数量
    top_k: int = 10
    
    # 来源配置
    sources: list[SourceType] = field(default_factory=lambda: [SourceType.MEMORY, SourceType.DOCUMENT])
    
    # 记忆检索配置
    memory_top_k: int = 20
    memory_weight: float = 0.4
    use_memory_vector: bool = True
    use_memory_keyword: bool = True
    use_memory_recency: bool = True
    
    # 文档检索配置
    document_top_k: int = 20
    document_weight: float = 0.6
    collection_ids: Optional[list[str]] = None  # 限定检索的文档集合
    document_filters: Optional[dict[str, Any]] = None
    
    # 高级配置
    use_reranking: bool = True
    rerank_top_k: int = 50  # 重排序前的候选数量
    min_score: float = 0.1  # 最小分数阈值
    
    # 缓存控制
    skip_cache: bool = False


@dataclass 
class UnifiedResult:
    """统一检索单条结果"""
    id: str
    content: str
    source: SourceType
    score: float
    
    # 来源特定数据
    memory: Optional[Memory] = None
    document_chunk: Optional[dict[str, Any]] = None
    
    # 元信息
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_context_string(self, include_source: bool = True) -> str:
        """转换为上下文字符串"""
        if include_source:
            source_label = "📝对话记忆" if self.source == SourceType.MEMORY else "📚知识文档"
            return f"[{source_label}] {self.content}"
        return self.content


@dataclass
class UnifiedResponse:
    """统一检索响应"""
    query: UnifiedQuery
    results: list[UnifiedResult] = field(default_factory=list)
    
    # 来源统计
    memory_count: int = 0
    document_count: int = 0
    
    # 性能指标
    latency_ms: float = 0.0
    memory_latency_ms: float = 0.0
    document_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0
    
    # 状态
    from_cache: bool = False
    errors: list[str] = field(default_factory=list)
    
    @property
    def total_count(self) -> int:
        return len(self.results)
    
    def to_context(
        self,
        max_tokens: int = 4000,
        include_source: bool = True,
        separator: str = "\n\n---\n\n"
    ) -> str:
        """
        将结果转换为 LLM 上下文
        
        Args:
            max_tokens: 最大 token 数（粗略估计）
            include_source: 是否包含来源标签
            separator: 分隔符
            
        Returns:
            格式化的上下文字符串
        """
        context_parts = []
        current_tokens = 0
        
        for result in self.results:
            part = result.to_context_string(include_source)
            # 粗略估计：1 token ≈ 4 字符（中文约 2 字符）
            part_tokens = len(part) // 2
            
            if current_tokens + part_tokens > max_tokens:
                break
            
            context_parts.append(part)
            current_tokens += part_tokens
        
        return separator.join(context_parts)
    
    def get_memory_results(self) -> list[UnifiedResult]:
        """获取记忆来源的结果"""
        return [r for r in self.results if r.source == SourceType.MEMORY]
    
    def get_document_results(self) -> list[UnifiedResult]:
        """获取文档来源的结果"""
        return [r for r in self.results if r.source == SourceType.DOCUMENT]


class UnifiedRetriever:
    """
    统一检索器
    
    整合 MemoryRetriever 和 RAG HybridRetriever，
    提供统一的检索接口。
    """
    
    def __init__(
        self,
        memory_retriever: Optional[MemoryRetriever] = None,
        rag_retriever: Optional[Any] = None,  # HybridRetriever from rag module
        reranker: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        config: Optional[MemoryConfig] = None,
    ):
        """
        初始化统一检索器
        
        Args:
            memory_retriever: 记忆检索器
            rag_retriever: RAG 文档检索器
            reranker: 重排序器（可选）
            redis_client: Redis 客户端
            config: 配置
        """
        self.memory_retriever = memory_retriever
        self.rag_retriever = rag_retriever
        self.reranker = reranker
        self.redis = redis_client
        self.config = config or MemoryConfig()
        
        # 缓存配置
        self._cache_ttl = 300  # 5分钟
        self._cache_prefix = "cache:unified"
    
    @classmethod
    async def create(
        cls,
        long_term: LongTermMemory,
        rag_retriever: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        config: Optional[MemoryConfig] = None,
    ) -> "UnifiedRetriever":
        """
        工厂方法创建统一检索器
        
        Args:
            long_term: 长期记忆存储
            rag_retriever: RAG 检索器（可选）
            redis_client: Redis 客户端
            config: 配置
        """
        memory_retriever = MemoryRetriever(
            long_term=long_term,
            redis_client=redis_client,
            config=config,
        )
        
        return cls(
            memory_retriever=memory_retriever,
            rag_retriever=rag_retriever,
            redis_client=redis_client,
            config=config,
        )
    
    def set_rag_retriever(self, rag_retriever: Any) -> None:
        """
        设置 RAG 检索器
        
        Args:
            rag_retriever: HybridRetriever 实例
        """
        self.rag_retriever = rag_retriever
    
    def set_reranker(self, reranker: Any) -> None:
        """
        设置重排序器
        
        Args:
            reranker: Reranker 实例
        """
        self.reranker = reranker
    
    async def retrieve(self, query: UnifiedQuery) -> UnifiedResponse:
        """
        执行统一检索
        
        Args:
            query: 统一检索查询
            
        Returns:
            统一检索响应
        """
        start_time = datetime.utcnow()
        response = UnifiedResponse(query=query)
        
        # 构建检索任务
        tasks = []
        task_names = []
        
        if SourceType.MEMORY in query.sources and self.memory_retriever:
            tasks.append(self._retrieve_memory(query))
            task_names.append("memory")
        
        if SourceType.DOCUMENT in query.sources and self.rag_retriever:
            tasks.append(self._retrieve_documents(query))
            task_names.append("document")
        
        if not tasks:
            logger.warning("No retrieval sources available")
            return response
        
        # 并行执行检索
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果
        all_candidates: list[UnifiedResult] = []
        
        for name, results in zip(task_names, results_list):
            if isinstance(results, Exception):
                error_msg = f"{name} retrieval failed: {results}"
                logger.error(error_msg)
                response.errors.append(error_msg)
                continue
            
            candidates, latency_ms = results
            
            if name == "memory":
                response.memory_latency_ms = latency_ms
                response.memory_count = len(candidates)
            else:
                response.document_latency_ms = latency_ms
                response.document_count = len(candidates)
            
            all_candidates.extend(candidates)
        
        # 跨源融合与排序
        if all_candidates:
            # 按分数排序
            all_candidates.sort(key=lambda x: x.score, reverse=True)
            
            # 重排序（如果启用且有重排序器）
            if query.use_reranking and self.reranker and len(all_candidates) > 1:
                rerank_start = datetime.utcnow()
                all_candidates = await self._rerank(query.query, all_candidates, query.rerank_top_k)
                response.rerank_latency_ms = (datetime.utcnow() - rerank_start).total_seconds() * 1000
            
            # 应用最小分数过滤
            all_candidates = [c for c in all_candidates if c.score >= query.min_score]
            
            # 取 top_k
            response.results = all_candidates[:query.top_k]
        
        response.latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.info(
            f"Unified retrieval completed: {response.total_count} results "
            f"(memory={response.memory_count}, document={response.document_count}) "
            f"in {response.latency_ms:.1f}ms"
        )
        
        return response
    
    async def _retrieve_memory(
        self,
        query: UnifiedQuery,
    ) -> tuple[list[UnifiedResult], float]:
        """
        执行记忆检索
        
        Returns:
            (结果列表, 延迟毫秒)
        """
        start = datetime.utcnow()
        
        memory_query = RetrievalQuery(
            user_id=query.user_id,
            query=query.query,
            top_k=query.memory_top_k,
            use_vector=query.use_memory_vector,
            use_keyword=query.use_memory_keyword,
            use_recency=query.use_memory_recency,
            skip_cache=query.skip_cache,
        )
        
        result = await self.memory_retriever.retrieve(memory_query)
        
        # 转换为统一结果
        candidates = []
        for search_result in result.results:
            memory = search_result.memory
            
            # 计算加权分数
            weighted_score = search_result.final_score * query.memory_weight
            
            candidates.append(UnifiedResult(
                id=str(memory.id),
                content=memory.content,
                source=SourceType.MEMORY,
                score=weighted_score,
                memory=memory,
                metadata={
                    "memory_type": memory.memory_type.value if memory.memory_type else None,
                    "importance": memory.importance,
                    "created_at": memory.created_at.isoformat() if memory.created_at else None,
                    "vector_score": search_result.vector_score,
                    "keyword_score": search_result.keyword_score,
                    "recency_score": search_result.recency_score,
                },
            ))
        
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return candidates, latency
    
    async def _retrieve_documents(
        self,
        query: UnifiedQuery,
    ) -> tuple[list[UnifiedResult], float]:
        """
        执行文档检索
        
        Returns:
            (结果列表, 延迟毫秒)
        """
        start = datetime.utcnow()
        
        # 调用 RAG HybridRetriever
        try:
            # 使用 simple_search 或 search 方法
            if hasattr(self.rag_retriever, 'simple_search'):
                rag_response = await self.rag_retriever.simple_search(
                    query=query.query,
                    tenant_id=query.tenant_id,
                    collection_id=query.collection_ids[0] if query.collection_ids else None,
                    top_k=query.document_top_k,
                )
            else:
                # 构建 RAG 查询
                from ...rag.retrieval import RetrievalQuery as RAGQuery
                
                rag_query = RAGQuery(
                    query=query.query,
                    tenant_id=query.tenant_id,
                    collection_id=query.collection_ids[0] if query.collection_ids else None,
                    top_k=query.document_top_k,
                    filters=query.document_filters,
                )
                rag_response = await self.rag_retriever.search(rag_query)
            
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            raise
        
        # 转换为统一结果
        candidates = []
        for rag_result in rag_response.results:
            # 计算加权分数
            weighted_score = rag_result.final_score * query.document_weight
            
            candidates.append(UnifiedResult(
                id=rag_result.chunk_id,
                content=rag_result.content,
                source=SourceType.DOCUMENT,
                score=weighted_score,
                document_chunk={
                    "chunk_id": rag_result.chunk_id,
                    "document_id": rag_result.document_id,
                    "chunk_index": rag_result.chunk_index,
                },
                metadata={
                    "document_id": rag_result.document_id,
                    "chunk_index": rag_result.chunk_index,
                    "dense_score": rag_result.dense_score,
                    "sparse_score": rag_result.sparse_score,
                    "bm25_score": rag_result.bm25_score,
                    "rerank_score": rag_result.rerank_score,
                    **rag_result.metadata,
                },
            ))
        
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return candidates, latency
    
    async def _rerank(
        self,
        query: str,
        candidates: list[UnifiedResult],
        top_k: int,
    ) -> list[UnifiedResult]:
        """
        跨源重排序
        
        Args:
            query: 查询文本
            candidates: 候选结果
            top_k: 重排序后保留数量
            
        Returns:
            重排序后的结果
        """
        if not self.reranker:
            return candidates
        
        try:
            # 准备文档列表
            documents = [c.content for c in candidates]
            
            # 调用重排序器
            if hasattr(self.reranker, 'rerank'):
                rerank_results = await self.reranker.rerank(
                    query=query,
                    documents=documents,
                    top_k=top_k,
                )
                
                # 根据重排序结果更新分数
                reranked = []
                for rr in rerank_results:
                    idx = rr.index
                    candidate = candidates[idx]
                    candidate.score = rr.score  # 使用重排序分数
                    candidate.metadata["original_score"] = candidates[idx].score
                    candidate.metadata["rerank_score"] = rr.score
                    reranked.append(candidate)
                
                return reranked
            else:
                # 如果重排序器没有 rerank 方法，返回原结果
                return candidates[:top_k]
                
        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
            return candidates[:top_k]
    
    async def retrieve_for_context(
        self,
        user_id: str,
        tenant_id: str,
        query: str,
        max_tokens: int = 4000,
        include_memory: bool = True,
        include_documents: bool = True,
        collection_ids: Optional[list[str]] = None,
    ) -> str:
        """
        便捷方法：检索并直接返回上下文字符串
        
        Args:
            user_id: 用户 ID
            tenant_id: 租户 ID
            query: 查询文本
            max_tokens: 最大 token 数
            include_memory: 是否包含记忆
            include_documents: 是否包含文档
            collection_ids: 文档集合 ID 列表
            
        Returns:
            格式化的上下文字符串
        """
        sources = []
        if include_memory:
            sources.append(SourceType.MEMORY)
        if include_documents:
            sources.append(SourceType.DOCUMENT)
        
        unified_query = UnifiedQuery(
            user_id=user_id,
            tenant_id=tenant_id,
            query=query,
            sources=sources,
            collection_ids=collection_ids,
        )
        
        response = await self.retrieve(unified_query)
        
        return response.to_context(max_tokens=max_tokens)
    
    async def search_memory_only(
        self,
        user_id: str,
        query: str,
        top_k: int = 10,
    ) -> UnifiedResponse:
        """
        仅检索记忆
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            统一检索响应
        """
        unified_query = UnifiedQuery(
            user_id=user_id,
            tenant_id="",  # 记忆检索不需要 tenant_id
            query=query,
            top_k=top_k,
            sources=[SourceType.MEMORY],
            memory_weight=1.0,
        )
        
        return await self.retrieve(unified_query)
    
    async def search_documents_only(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        collection_ids: Optional[list[str]] = None,
    ) -> UnifiedResponse:
        """
        仅检索文档
        
        Args:
            tenant_id: 租户 ID
            query: 查询文本
            top_k: 返回数量
            collection_ids: 集合 ID 列表
            
        Returns:
            统一检索响应
        """
        unified_query = UnifiedQuery(
            user_id="",  # 文档检索可能不需要 user_id
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            sources=[SourceType.DOCUMENT],
            document_weight=1.0,
            collection_ids=collection_ids,
        )
        
        return await self.retrieve(unified_query)
