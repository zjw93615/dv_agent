"""
RAG-Fusion Retrieval System

提供多路召回、RRF融合、精排等检索能力。

Components:
- QueryGenerator: 多查询生成器（LLM驱动）
- DenseSearcher: 稠密向量检索
- SparseSearcher: 稀疏向量检索
- BM25Searcher: 关键词检索（PostgreSQL TSVECTOR）
- RRFFusion: Reciprocal Rank Fusion 结果融合
- Reranker: Cross-Encoder 精排
- Retriever: 检索编排器（整合所有组件）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class SearchMode(Enum):
    """检索模式"""
    DENSE_ONLY = "dense_only"           # 仅稠密向量
    SPARSE_ONLY = "sparse_only"         # 仅稀疏向量
    BM25_ONLY = "bm25_only"             # 仅BM25
    HYBRID_DENSE_BM25 = "hybrid_db"     # 稠密 + BM25
    HYBRID_ALL = "hybrid_all"           # 全路召回（推荐）
    

@dataclass
class RetrievalQuery:
    """检索查询"""
    query: str                          # 原始查询
    tenant_id: str                      # 租户ID
    collection_id: Optional[str] = None # 文档集合ID（可选）
    top_k: int = 10                     # 返回数量
    mode: SearchMode = SearchMode.HYBRID_ALL  # 检索模式
    expand_queries: bool = True         # 是否启用查询扩展
    rerank: bool = True                 # 是否启用精排
    filters: Dict[str, Any] = field(default_factory=dict)  # 过滤条件
    

@dataclass
class RetrievalResult:
    """检索结果"""
    chunk_id: str                       # 文档片段ID
    doc_id: str                         # 文档ID
    content: str                        # 文本内容
    score: float                        # 融合分数
    source_scores: Dict[str, float] = field(default_factory=dict)  # 各路分数
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    

@dataclass
class RetrievalResponse:
    """检索响应"""
    query: str                          # 原始查询
    expanded_queries: List[str] = field(default_factory=list)  # 扩展查询
    results: List[RetrievalResult] = field(default_factory=list)  # 结果列表
    total_candidates: int = 0           # 召回候选总数
    latency_ms: float = 0.0             # 检索延迟(毫秒)
    debug_info: Dict[str, Any] = field(default_factory=dict)  # 调试信息


__all__ = [
    "SearchMode",
    "RetrievalQuery", 
    "RetrievalResult",
    "RetrievalResponse",
]
