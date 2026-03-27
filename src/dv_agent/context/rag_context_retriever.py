"""
RAG 上下文检索器

将历史对话向量化并通过 Milvus 检索相关上下文。
与 ContextBuilder 集成,增强 Agent 记忆。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RetrievedContext:
    """检索到的上下文"""
    content: str
    score: float
    chunk_id: str
    source: str  # "history" | "document"
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RAGContextRetriever:
    """
    RAG 上下文检索器
    
    功能:
    1. 向量化历史对话
    2. 基于相似度检索相关历史
    3. 支持混合检索 (向量 + BM25)
    4. 融合到上下文构建流程
    """
    
    def __init__(
        self,
        embedder,  # BGEM3Embedder
        milvus_store,  # MilvusDocumentStore
        pg_store=None,  # PostgresDocumentStore (可选)
        collection_name: str = "agent_history_embeddings",
        default_top_k: int = 5,
    ):
        """
        初始化
        
        Args:
            embedder: BGE-M3 嵌入器
            milvus_store: Milvus 向量存储
            pg_store: PostgreSQL 存储 (可选,用于 BM25)
            collection_name: 历史向量集合名
            default_top_k: 默认检索数量
        """
        self.embedder = embedder
        self.milvus = milvus_store
        self.pg_store = pg_store
        self.collection_name = collection_name
        self.default_top_k = default_top_k
        
        logger.info(f"RAGContextRetriever initialized with collection: {collection_name}")
    
    async def index_conversation(
        self,
        session_id: str,
        tenant_id: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        索引对话历史到向量数据库
        
        Args:
            session_id: 会话ID
            tenant_id: 租户ID
            messages: 消息列表 [{"role": "user/assistant", "content": "..."}]
            metadata: 额外元数据
            
        Returns:
            索引的消息数量
        """
        if not messages:
            return 0
        
        indexed_count = 0
        
        for idx, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # 跳过空消息和系统消息
            if not content or role == "system":
                continue
            
            try:
                # 生成向量
                embedding_result = self.embedder.embed(
                    content,
                    return_dense=True,
                    return_sparse=False,
                )
                
                if embedding_result.dense_embedding is None:
                    logger.warning(f"Failed to embed message {idx}")
                    continue
                
                # 构建元数据
                chunk_metadata = {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "role": role,
                    "message_index": idx,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                if metadata:
                    chunk_metadata.update(metadata)
                
                # 存储到 Milvus
                chunk_id = f"{session_id}_{idx}"
                await self.milvus.insert_dense(
                    chunk_id=chunk_id,
                    doc_id=session_id,  # 使用 session_id 作为 doc_id
                    tenant_id=tenant_id,
                    vector=embedding_result.dense_embedding,
                    metadata=chunk_metadata,
                )
                
                indexed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to index message {idx}: {e}")
        
        logger.info(f"Indexed {indexed_count} messages for session {session_id}")
        return indexed_count
    
    async def retrieve_relevant_history(
        self,
        query: str,
        tenant_id: str,
        session_id: Optional[str] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedContext]:
        """
        基于查询检索相关历史上下文
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            session_id: 会话ID (可选,用于过滤特定会话)
            top_k: 返回数量
            filters: 额外过滤条件
            
        Returns:
            检索到的上下文列表
        """
        top_k = top_k or self.default_top_k
        
        try:
            # 生成查询向量
            embedding_result = self.embedder.embed(
                query,
                return_dense=True,
                return_sparse=False,
            )
            
            if embedding_result.dense_embedding is None:
                logger.error("Failed to generate query embedding")
                return []
            
            # 构建过滤条件
            filter_expr = f'tenant_id == "{tenant_id}"'
            if session_id:
                filter_expr += f' && session_id == "{session_id}"'
            
            if filters:
                for key, value in filters.items():
                    if isinstance(value, str):
                        filter_expr += f' && {key} == "{value}"'
            
            # Milvus 检索
            results = await self.milvus.search_dense(
                vector=embedding_result.dense_embedding,
                tenant_id=tenant_id,
                top_k=top_k,
            )
            
            # 转换结果
            retrieved = []
            for hit in results:
                ctx = RetrievedContext(
                    content=hit.get("content", ""),
                    score=hit.get("score", 0.0),
                    chunk_id=hit.get("chunk_id", ""),
                    source="history",
                    metadata=hit.get("metadata", {}),
                )
                
                # 解析时间戳
                if "timestamp" in ctx.metadata:
                    try:
                        ctx.timestamp = datetime.fromisoformat(ctx.metadata["timestamp"])
                    except:
                        pass
                
                retrieved.append(ctx)
            
            logger.debug(
                f"Retrieved {len(retrieved)} relevant history items for query: {query[:50]}..."
            )
            
            return retrieved
            
        except Exception as e:
            logger.error(f"Failed to retrieve relevant history: {e}")
            return []
    
    async def retrieve_hybrid(
        self,
        query: str,
        tenant_id: str,
        session_id: Optional[str] = None,
        top_k: Optional[int] = None,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ) -> List[RetrievedContext]:
        """
        混合检索：向量相似度 + BM25
        
        Args:
            query: 查询文本
            tenant_id: 租户ID
            session_id: 会话ID
            top_k: 返回数量
            vector_weight: 向量检索权重
            bm25_weight: BM25 权重
            
        Returns:
            融合后的检索结果
        """
        top_k = top_k or self.default_top_k
        
        # 向量检索
        vector_results = await self.retrieve_relevant_history(
            query=query,
            tenant_id=tenant_id,
            session_id=session_id,
            top_k=top_k * 2,  # 多召回一些用于融合
        )
        
        # BM25 检索 (如果有 PG 存储)
        bm25_results = []
        if self.pg_store:
            try:
                bm25_hits = await self.pg_store.search_bm25(
                    query=query,
                    tenant_id=tenant_id,
                    collection_id=session_id,
                    top_k=top_k * 2,
                )
                
                for hit in bm25_hits:
                    bm25_results.append(RetrievedContext(
                        content=hit.get("content", ""),
                        score=hit.get("score", 0.0),
                        chunk_id=hit.get("chunk_id", ""),
                        source="history",
                        metadata=hit.get("metadata", {}),
                    ))
            except Exception as e:
                logger.warning(f"BM25 search failed: {e}")
        
        # RRF 融合
        merged = self._rrf_fusion(
            vector_results=vector_results,
            bm25_results=bm25_results,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            top_k=top_k,
        )
        
        return merged
    
    def _rrf_fusion(
        self,
        vector_results: List[RetrievedContext],
        bm25_results: List[RetrievedContext],
        vector_weight: float,
        bm25_weight: float,
        top_k: int,
        k: int = 60,
    ) -> List[RetrievedContext]:
        """
        Reciprocal Rank Fusion (RRF) 融合
        
        Args:
            vector_results: 向量检索结果
            bm25_results: BM25 检索结果
            vector_weight: 向量权重
            bm25_weight: BM25 权重
            top_k: 返回数量
            k: RRF 平滑参数
            
        Returns:
            融合后的结果
        """
        # 计算 RRF 分数
        scores = {}
        
        # 向量结果
        for rank, ctx in enumerate(vector_results):
            chunk_id = ctx.chunk_id
            rrf_score = vector_weight / (k + rank + 1)
            
            if chunk_id not in scores:
                scores[chunk_id] = {
                    "context": ctx,
                    "score": 0.0,
                }
            scores[chunk_id]["score"] += rrf_score
        
        # BM25 结果
        for rank, ctx in enumerate(bm25_results):
            chunk_id = ctx.chunk_id
            rrf_score = bm25_weight / (k + rank + 1)
            
            if chunk_id not in scores:
                scores[chunk_id] = {
                    "context": ctx,
                    "score": 0.0,
                }
            scores[chunk_id]["score"] += rrf_score
        
        # 排序并返回
        sorted_items = sorted(
            scores.values(),
            key=lambda x: x["score"],
            reverse=True,
        )
        
        results = []
        for item in sorted_items[:top_k]:
            ctx = item["context"]
            ctx.score = item["score"]  # 更新为融合分数
            results.append(ctx)
        
        return results
    
    async def delete_session_history(
        self,
        session_id: str,
        tenant_id: str,
    ) -> bool:
        """
        删除会话的历史向量
        
        Args:
            session_id: 会话ID
            tenant_id: 租户ID
            
        Returns:
            是否成功
        """
        try:
            # 删除 Milvus 中的向量
            await self.milvus.delete_dense_by_doc(doc_id=session_id)
            
            logger.info(f"Deleted history vectors for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session history: {e}")
            return False
    
    def format_for_context(
        self,
        retrieved: List[RetrievedContext],
        max_items: int = 5,
    ) -> str:
        """
        格式化检索结果为上下文字符串
        
        Args:
            retrieved: 检索结果列表
            max_items: 最多包含的项目数
            
        Returns:
            格式化的上下文字符串
        """
        if not retrieved:
            return ""
        
        lines = ["## 相关历史上下文\n"]
        
        for i, ctx in enumerate(retrieved[:max_items], 1):
            role = ctx.metadata.get("role", "unknown")
            timestamp = ctx.metadata.get("timestamp", "")
            
            lines.append(f"{i}. [{role}] (相似度: {ctx.score:.2f})")
            if timestamp:
                lines.append(f"   时间: {timestamp[:19]}")
            lines.append(f"   内容: {ctx.content}")
            lines.append("")
        
        return "\n".join(lines)


# 便捷函数
async def retrieve_relevant_context(
    query: str,
    tenant_id: str,
    embedder,
    milvus_store,
    top_k: int = 5,
) -> List[RetrievedContext]:
    """
    快速检索相关上下文
    
    Args:
        query: 查询文本
        tenant_id: 租户ID
        embedder: 嵌入器
        milvus_store: Milvus 存储
        top_k: 返回数量
        
    Returns:
        检索结果列表
    """
    retriever = RAGContextRetriever(embedder, milvus_store)
    return await retriever.retrieve_relevant_history(
        query=query,
        tenant_id=tenant_id,
        top_k=top_k,
    )
