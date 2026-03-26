"""
Cross-Encoder Reranker
交叉编码器重排序

使用 Cross-Encoder 模型对检索结果进行精排，
提高 Top-K 结果的相关性。
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from ..long_term import SearchResult
from ..models import Memory

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """重排序结果"""
    memory: Memory
    original_score: float
    rerank_score: float
    final_score: float


class CrossEncoderReranker:
    """
    Cross-Encoder 重排序器
    
    使用交叉编码器模型计算 query-document 的精确相关性分数，
    对初步检索结果进行重排序。
    
    特点：
    - 比双塔模型更精确（直接计算 query-doc 交互）
    - 计算成本更高（适合对小规模候选集精排）
    - 支持异步执行
    """
    
    # 默认模型
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        max_length: int = 512,
        batch_size: int = 32,
        device: Optional[str] = None,
    ):
        """
        初始化重排序器
        
        Args:
            model_name: Cross-Encoder 模型名称
            max_length: 最大输入长度
            batch_size: 批处理大小
            device: 设备（cuda/cpu）
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.max_length = max_length
        self.batch_size = batch_size
        self.device = device
        
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                
                self._model = CrossEncoder(
                    self.model_name,
                    max_length=self.max_length,
                    device=self.device,
                )
                logger.info(f"Loaded Cross-Encoder model: {self.model_name}")
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to load Cross-Encoder model: {e}")
                raise
        
        return self._model
    
    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: Optional[int] = None,
        original_weight: float = 0.3,
        rerank_weight: float = 0.7,
    ) -> list[RerankResult]:
        """
        重排序检索结果
        
        Args:
            query: 查询文本
            results: 初步检索结果
            top_k: 返回数量（默认全部）
            original_weight: 原始分数权重
            rerank_weight: 重排分数权重
            
        Returns:
            重排序后的结果
        """
        if not results:
            return []
        
        # 在线程池中执行 Cross-Encoder 推理
        loop = asyncio.get_event_loop()
        reranked = await loop.run_in_executor(
            self._executor,
            self._rerank_sync,
            query,
            results,
            original_weight,
            rerank_weight,
        )
        
        # 限制返回数量
        if top_k is not None:
            reranked = reranked[:top_k]
        
        return reranked
    
    def _rerank_sync(
        self,
        query: str,
        results: list[SearchResult],
        original_weight: float,
        rerank_weight: float,
    ) -> list[RerankResult]:
        """
        同步重排序（在线程池中执行）
        
        Args:
            query: 查询文本
            results: 初步检索结果
            original_weight: 原始分数权重
            rerank_weight: 重排分数权重
            
        Returns:
            重排序后的结果
        """
        model = self._load_model()
        
        # 准备输入对
        pairs = [
            (query, result.memory.content)
            for result in results
        ]
        
        # 批量计算分数
        try:
            scores = model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.error(f"Cross-Encoder prediction failed: {e}")
            # 降级：返回原始排序
            return [
                RerankResult(
                    memory=r.memory,
                    original_score=r.final_score,
                    rerank_score=0.0,
                    final_score=r.final_score,
                )
                for r in results
            ]
        
        # 归一化 rerank 分数到 [0, 1]
        if len(scores) > 0:
            min_score = min(scores)
            max_score = max(scores)
            score_range = max_score - min_score
            
            if score_range > 0:
                normalized_scores = [
                    (s - min_score) / score_range
                    for s in scores
                ]
            else:
                normalized_scores = [0.5] * len(scores)
        else:
            normalized_scores = []
        
        # 构建结果
        reranked = []
        for result, rerank_score in zip(results, normalized_scores):
            # 原始分数也归一化到 [0, 1]（假设已经是了）
            original_score = result.final_score
            
            # 加权融合
            final_score = (
                original_weight * original_score +
                rerank_weight * rerank_score
            )
            
            reranked.append(RerankResult(
                memory=result.memory,
                original_score=original_score,
                rerank_score=rerank_score,
                final_score=final_score,
            ))
        
        # 按最终分数降序排序
        reranked.sort(key=lambda x: x.final_score, reverse=True)
        
        logger.debug(
            f"Reranked {len(reranked)} results "
            f"(original_weight={original_weight}, rerank_weight={rerank_weight})"
        )
        
        return reranked
    
    async def rerank_with_diversity(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 10,
        diversity_threshold: float = 0.8,
    ) -> list[RerankResult]:
        """
        带多样性的重排序
        
        使用 Maximal Marginal Relevance (MMR) 算法，
        在相关性和多样性之间取得平衡。
        
        Args:
            query: 查询文本
            results: 初步检索结果
            top_k: 返回数量
            diversity_threshold: 多样性阈值（越低越多样）
            
        Returns:
            重排序后的结果
        """
        # 先进行标准重排序
        reranked = await self.rerank(query, results)
        
        if len(reranked) <= 1:
            return reranked[:top_k]
        
        # MMR 选择
        selected = [reranked[0]]  # 选择分数最高的
        candidates = reranked[1:]
        
        while len(selected) < top_k and candidates:
            best_candidate = None
            best_mmr_score = float('-inf')
            
            for candidate in candidates:
                # 计算与已选择项的最大相似度
                max_sim = max(
                    self._content_similarity(candidate.memory.content, s.memory.content)
                    for s in selected
                )
                
                # MMR 分数
                mmr_score = (
                    diversity_threshold * candidate.final_score -
                    (1 - diversity_threshold) * max_sim
                )
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_candidate = candidate
            
            if best_candidate:
                selected.append(best_candidate)
                candidates.remove(best_candidate)
            else:
                break
        
        return selected
    
    def _content_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的简单相似度
        
        使用 Jaccard 相似度作为快速估计
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度 [0, 1]
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def close(self):
        """关闭资源"""
        self._executor.shutdown(wait=False)
        self._model = None
