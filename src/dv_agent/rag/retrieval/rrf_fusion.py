"""
Reciprocal Rank Fusion (RRF)

将多路检索结果融合为统一排序。

核心公式：
RRF(d) = Σ 1/(k + rank(d))

其中 k 是平滑参数（通常为60），rank(d) 是文档在某一检索结果中的排名。

优势：
1. 无需归一化不同检索器的分数
2. 对异常值鲁棒
3. 简单高效
"""

import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class FusionCandidate:
    """融合候选"""
    chunk_id: str
    doc_id: str
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 各路检索信息
    source_ranks: Dict[str, int] = field(default_factory=dict)  # {source: rank}
    source_scores: Dict[str, float] = field(default_factory=dict)  # {source: score}
    
    # 融合结果
    rrf_score: float = 0.0


@dataclass
class FusionResult:
    """融合结果"""
    candidates: List[FusionCandidate]
    total_sources: int  # 参与融合的检索源数量
    total_candidates: int  # 融合前的候选总数
    fusion_method: str = "rrf"
    
    def to_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表"""
        return [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "content": c.content,
                "metadata": c.metadata,
                "score": c.rrf_score,
                "source_ranks": c.source_ranks,
                "source_scores": c.source_scores
            }
            for c in self.candidates
        ]


class RRFFusion:
    """
    Reciprocal Rank Fusion 实现
    
    支持多路检索结果的融合，通过排名倒数求和计算最终分数。
    """
    
    def __init__(
        self,
        k: int = 60,  # RRF 平滑参数
        weights: Optional[Dict[str, float]] = None  # 各检索源权重
    ):
        """
        初始化
        
        Args:
            k: 平滑参数，控制高排名文档的权重
            weights: 各检索源的权重 {source_name: weight}
        """
        self.k = k
        self.weights = weights or {}
        
    def fuse(
        self,
        results_by_source: Dict[str, List[Dict[str, Any]]],
        top_k: int = 10,
        min_sources: int = 1
    ) -> FusionResult:
        """
        融合多路检索结果
        
        Args:
            results_by_source: 各检索源的结果 {source_name: [results]}
                每个 result 需要有 chunk_id, doc_id, score, content, metadata
            top_k: 返回的结果数量
            min_sources: 最少需要出现在几个源中才保留
            
        Returns:
            融合后的结果
        """
        if not results_by_source:
            return FusionResult(
                candidates=[],
                total_sources=0,
                total_candidates=0
            )
        
        # 收集所有候选
        candidates_map: Dict[str, FusionCandidate] = {}
        total_candidates = 0
        
        for source_name, results in results_by_source.items():
            weight = self.weights.get(source_name, 1.0)
            
            for rank, result in enumerate(results, start=1):
                chunk_id = result.get("chunk_id", "")
                if not chunk_id:
                    continue
                
                total_candidates += 1
                
                # 获取或创建候选
                if chunk_id not in candidates_map:
                    candidates_map[chunk_id] = FusionCandidate(
                        chunk_id=chunk_id,
                        doc_id=result.get("doc_id", ""),
                        content=result.get("content", ""),
                        metadata=result.get("metadata", {})
                    )
                
                candidate = candidates_map[chunk_id]
                
                # 记录源排名和分数
                candidate.source_ranks[source_name] = rank
                candidate.source_scores[source_name] = result.get("score", 0.0)
                
                # 计算该源的RRF贡献
                rrf_contribution = weight / (self.k + rank)
                candidate.rrf_score += rrf_contribution
        
        # 过滤：至少出现在 min_sources 个源中
        filtered_candidates = [
            c for c in candidates_map.values()
            if len(c.source_ranks) >= min_sources
        ]
        
        # 按RRF分数排序
        filtered_candidates.sort(key=lambda x: x.rrf_score, reverse=True)
        
        # 截取Top-K
        top_candidates = filtered_candidates[:top_k]
        
        logger.debug(
            f"RRF fusion: {total_candidates} candidates from {len(results_by_source)} sources "
            f"-> {len(filtered_candidates)} filtered -> {len(top_candidates)} returned"
        )
        
        return FusionResult(
            candidates=top_candidates,
            total_sources=len(results_by_source),
            total_candidates=total_candidates
        )
    
    def fuse_with_normalization(
        self,
        results_by_source: Dict[str, List[Dict[str, Any]]],
        top_k: int = 10,
        score_weight: float = 0.3
    ) -> FusionResult:
        """
        融合多路检索结果（带分数归一化）
        
        结合RRF排名分数和原始分数。
        
        Args:
            results_by_source: 各检索源的结果
            top_k: 返回数量
            score_weight: 原始分数的权重（0-1）
            
        Returns:
            融合结果
        """
        if not results_by_source:
            return FusionResult(candidates=[], total_sources=0, total_candidates=0)
        
        # 首先计算标准RRF
        rrf_result = self.fuse(results_by_source, top_k=top_k * 2)
        
        if not rrf_result.candidates:
            return rrf_result
        
        # 归一化原始分数
        for source_name, results in results_by_source.items():
            if not results:
                continue
            
            scores = [r.get("score", 0.0) for r in results]
            max_score = max(scores) if scores else 1.0
            min_score = min(scores) if scores else 0.0
            score_range = max_score - min_score if max_score > min_score else 1.0
            
            # 更新候选的归一化分数
            for candidate in rrf_result.candidates:
                if source_name in candidate.source_scores:
                    original_score = candidate.source_scores[source_name]
                    normalized_score = (original_score - min_score) / score_range
                    
                    # 混合RRF分数和归一化分数
                    candidate.rrf_score += score_weight * normalized_score
        
        # 重新排序
        rrf_result.candidates.sort(key=lambda x: x.rrf_score, reverse=True)
        rrf_result.candidates = rrf_result.candidates[:top_k]
        
        return rrf_result


class WeightedRRFFusion(RRFFusion):
    """
    加权RRF融合
    
    支持动态调整各检索源的权重。
    """
    
    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "dense": 1.0,     # 稠密向量
        "sparse": 0.8,    # 稀疏向量
        "bm25": 0.6       # 关键词检索
    }
    
    def __init__(
        self,
        k: int = 60,
        weights: Optional[Dict[str, float]] = None,
        use_default_weights: bool = True
    ):
        if use_default_weights and weights is None:
            weights = self.DEFAULT_WEIGHTS.copy()
        super().__init__(k, weights)
    
    def set_weight(self, source_name: str, weight: float):
        """设置单个源的权重"""
        self.weights[source_name] = weight
    
    def set_weights(self, weights: Dict[str, float]):
        """批量设置权重"""
        self.weights.update(weights)


class AdaptiveRRFFusion(RRFFusion):
    """
    自适应RRF融合
    
    根据查询特征动态调整权重。
    """
    
    def __init__(self, k: int = 60):
        super().__init__(k)
        
    def fuse(
        self,
        results_by_source: Dict[str, List[Dict[str, Any]]],
        top_k: int = 10,
        query: Optional[str] = None,
        min_sources: int = 1
    ) -> FusionResult:
        """
        自适应融合
        
        Args:
            results_by_source: 各检索源的结果
            top_k: 返回数量
            query: 原始查询（用于计算自适应权重）
            min_sources: 最少源数
            
        Returns:
            融合结果
        """
        # 根据查询计算自适应权重
        if query:
            self.weights = self._compute_adaptive_weights(query, results_by_source)
        
        return super().fuse(results_by_source, top_k, min_sources)
    
    def _compute_adaptive_weights(
        self,
        query: str,
        results_by_source: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, float]:
        """
        计算自适应权重
        
        策略：
        1. 查询较短时，提高BM25权重（关键词匹配更重要）
        2. 查询较长时，提高稠密向量权重（语义理解更重要）
        3. 某源结果较少时，降低其权重
        """
        weights = {}
        query_length = len(query.split())
        
        # 基础权重
        base_weights = {
            "dense": 1.0,
            "sparse": 0.8,
            "bm25": 0.6
        }
        
        for source_name in results_by_source.keys():
            base = base_weights.get(source_name, 1.0)
            
            # 根据查询长度调整
            if query_length <= 3:  # 短查询
                if source_name == "bm25":
                    base *= 1.3
                elif source_name == "dense":
                    base *= 0.8
            elif query_length >= 10:  # 长查询
                if source_name == "dense":
                    base *= 1.2
                elif source_name == "bm25":
                    base *= 0.7
            
            # 根据结果数量调整
            result_count = len(results_by_source.get(source_name, []))
            if result_count < 5:
                base *= 0.8
            
            weights[source_name] = base
        
        return weights


# 便捷函数
def rrf_fuse(
    results_by_source: Dict[str, List[Dict[str, Any]]],
    top_k: int = 10,
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    快速RRF融合
    
    Args:
        results_by_source: 各源结果 {source_name: [results]}
        top_k: 返回数量
        k: RRF平滑参数
        
    Returns:
        融合后的结果列表
    """
    fusion = RRFFusion(k=k)
    result = fusion.fuse(results_by_source, top_k)
    return result.to_list()


def weighted_rrf_fuse(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    top_k: int = 10,
    dense_weight: float = 1.0,
    sparse_weight: float = 0.8,
    bm25_weight: float = 0.6
) -> List[Dict[str, Any]]:
    """
    加权RRF融合（三路）
    
    Args:
        dense_results: 稠密向量结果
        sparse_results: 稀疏向量结果
        bm25_results: BM25结果
        top_k: 返回数量
        dense_weight: 稠密权重
        sparse_weight: 稀疏权重
        bm25_weight: BM25权重
        
    Returns:
        融合后的结果列表
    """
    results_by_source = {
        "dense": dense_results,
        "sparse": sparse_results,
        "bm25": bm25_results
    }
    
    weights = {
        "dense": dense_weight,
        "sparse": sparse_weight,
        "bm25": bm25_weight
    }
    
    fusion = WeightedRRFFusion(weights=weights)
    result = fusion.fuse(results_by_source, top_k)
    return result.to_list()
