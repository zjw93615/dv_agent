"""
Cross-Encoder Reranker

使用交叉编码器对候选结果进行精排。

模型：bge-reranker-v2-m3
特性：
1. 深度交互：query和document同时输入模型
2. 更精准的相关性判断
3. 支持长文本（最大8192 tokens）
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import torch
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """重排结果"""
    chunk_id: str
    doc_id: str
    content: str
    original_score: float  # 原始融合分数
    rerank_score: float    # 重排分数
    final_score: float     # 最终分数
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Reranker:
    """
    Cross-Encoder 重排器
    
    使用BGE-Reranker-v2-m3进行精准相关性排序。
    """
    
    # 支持的模型
    SUPPORTED_MODELS = {
        "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
        "bge-reranker-large": "BAAI/bge-reranker-large",
        "bge-reranker-base": "BAAI/bge-reranker-base",
    }
    
    def __init__(
        self,
        model_name: str = "bge-reranker-v2-m3",
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        max_length: int = 1024,
        batch_size: int = 32,
        use_fp16: bool = True
    ):
        """
        初始化
        
        Args:
            model_name: 模型名称
            model_path: 本地模型路径（可选）
            device: 设备（cuda/cpu，自动检测）
            max_length: 最大序列长度
            batch_size: 批处理大小
            use_fp16: 是否使用FP16
        """
        self.model_name = model_name
        self.model_path = model_path or self.SUPPORTED_MODELS.get(model_name, model_name)
        self.max_length = max_length
        self.batch_size = batch_size
        self.use_fp16 = use_fp16
        
        # 设备检测
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        # 模型延迟加载
        self._model = None
        self._tokenizer = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        
        logger.info(f"Reranker initialized: model={model_name}, device={self.device}")
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return
        
        logger.info(f"Loading reranker model: {self.model_path}")
        
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if self.use_fp16 and self.device == "cuda" else torch.float32
            )
            self._model.to(self.device)
            self._model.eval()
            
            logger.info(f"Reranker model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load reranker model: {e}")
            raise
    
    def _compute_scores(
        self,
        query: str,
        documents: List[str]
    ) -> List[float]:
        """
        计算相关性分数（同步）
        
        Args:
            query: 查询文本
            documents: 文档列表
            
        Returns:
            分数列表
        """
        self._load_model()
        
        if not documents:
            return []
        
        scores = []
        
        # 批处理
        for i in range(0, len(documents), self.batch_size):
            batch_docs = documents[i:i + self.batch_size]
            
            # 构建输入对
            pairs = [[query, doc] for doc in batch_docs]
            
            # Tokenize
            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 推理
            with torch.no_grad():
                outputs = self._model(**inputs)
                # 获取相关性分数（logits的第一列或softmax后的正类概率）
                if outputs.logits.shape[-1] == 1:
                    batch_scores = outputs.logits.squeeze(-1).cpu().tolist()
                else:
                    batch_scores = torch.softmax(outputs.logits, dim=-1)[:, 1].cpu().tolist()
            
            if isinstance(batch_scores, float):
                batch_scores = [batch_scores]
            
            scores.extend(batch_scores)
        
        return scores
    
    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        original_score_weight: float = 0.0
    ) -> List[RerankResult]:
        """
        重排候选结果
        
        Args:
            query: 查询文本
            candidates: 候选列表，每个需要有 content, chunk_id, doc_id, score
            top_k: 返回数量（None则全部返回）
            score_threshold: 分数阈值（低于此值的结果被过滤）
            original_score_weight: 原始分数权重（0-1）
            
        Returns:
            重排后的结果列表
        """
        if not candidates:
            return []
        
        # 提取文档内容
        documents = [c.get("content", "") for c in candidates]
        
        # 异步执行重排（在线程池中运行）
        loop = asyncio.get_event_loop()
        rerank_scores = await loop.run_in_executor(
            self._executor,
            self._compute_scores,
            query,
            documents
        )
        
        # 构建结果
        results = []
        for i, (candidate, rerank_score) in enumerate(zip(candidates, rerank_scores)):
            original_score = candidate.get("score", 0.0)
            
            # 计算最终分数
            if original_score_weight > 0:
                # 归一化rerank分数到0-1
                normalized_rerank = self._sigmoid(rerank_score)
                final_score = (1 - original_score_weight) * normalized_rerank + original_score_weight * original_score
            else:
                final_score = rerank_score
            
            result = RerankResult(
                chunk_id=candidate.get("chunk_id", ""),
                doc_id=candidate.get("doc_id", ""),
                content=candidate.get("content", ""),
                original_score=original_score,
                rerank_score=rerank_score,
                final_score=final_score,
                metadata=candidate.get("metadata", {})
            )
            results.append(result)
        
        # 按最终分数排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        # 过滤低分结果
        if score_threshold is not None:
            results = [r for r in results if r.final_score >= score_threshold]
        
        # 截取Top-K
        if top_k is not None:
            results = results[:top_k]
        
        logger.debug(f"Reranked {len(candidates)} candidates -> {len(results)} results")
        return results
    
    async def rerank_with_diversity(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
        diversity_weight: float = 0.1
    ) -> List[RerankResult]:
        """
        带多样性的重排
        
        使用MMR (Maximal Marginal Relevance) 思想，
        在相关性和多样性之间取得平衡。
        
        Args:
            query: 查询文本
            candidates: 候选列表
            top_k: 返回数量
            diversity_weight: 多样性权重（0-1）
            
        Returns:
            重排结果
        """
        # 首先获取相关性分数
        base_results = await self.rerank(query, candidates)
        
        if len(base_results) <= top_k:
            return base_results
        
        # MMR选择
        selected = []
        remaining = list(base_results)
        
        while len(selected) < top_k and remaining:
            if not selected:
                # 选择最相关的
                selected.append(remaining.pop(0))
            else:
                # 计算每个候选与已选的最大相似度
                best_candidate = None
                best_mmr_score = float('-inf')
                
                for candidate in remaining:
                    # 简单的多样性度量：与已选内容的词重叠
                    max_similarity = max(
                        self._text_similarity(candidate.content, s.content)
                        for s in selected
                    )
                    
                    # MMR分数
                    mmr_score = (1 - diversity_weight) * candidate.final_score - diversity_weight * max_similarity
                    
                    if mmr_score > best_mmr_score:
                        best_mmr_score = mmr_score
                        best_candidate = candidate
                
                if best_candidate:
                    selected.append(best_candidate)
                    remaining.remove(best_candidate)
        
        return selected
    
    def _sigmoid(self, x: float) -> float:
        """Sigmoid函数"""
        import math
        return 1 / (1 + math.exp(-x))
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        简单的文本相似度（词重叠）
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def __del__(self):
        """清理资源"""
        if self._executor:
            self._executor.shutdown(wait=False)


class LightweightReranker:
    """
    轻量级重排器
    
    不使用Cross-Encoder，通过规则和简单模型进行重排。
    适用于资源受限或低延迟场景。
    """
    
    def __init__(
        self,
        boost_exact_match: float = 0.5,
        boost_title_match: float = 0.3,
        length_penalty: float = 0.1
    ):
        """
        初始化
        
        Args:
            boost_exact_match: 精确匹配加分
            boost_title_match: 标题匹配加分
            length_penalty: 长度惩罚系数
        """
        self.boost_exact_match = boost_exact_match
        self.boost_title_match = boost_title_match
        self.length_penalty = length_penalty
    
    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """轻量级重排"""
        if not candidates:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        results = []
        for candidate in candidates:
            content = candidate.get("content", "")
            content_lower = content.lower()
            original_score = candidate.get("score", 0.0)
            
            # 计算加分
            boost = 0.0
            
            # 精确匹配加分
            if query_lower in content_lower:
                boost += self.boost_exact_match
            
            # 标题匹配加分
            title = candidate.get("metadata", {}).get("title", "")
            if title and any(w in title.lower() for w in query_words):
                boost += self.boost_title_match
            
            # 长度惩罚（太短或太长的内容）
            content_length = len(content)
            if content_length < 50:
                boost -= self.length_penalty
            elif content_length > 2000:
                boost -= self.length_penalty * 0.5
            
            # 计算最终分数
            final_score = original_score + boost
            
            results.append(RerankResult(
                chunk_id=candidate.get("chunk_id", ""),
                doc_id=candidate.get("doc_id", ""),
                content=content,
                original_score=original_score,
                rerank_score=boost,
                final_score=final_score,
                metadata=candidate.get("metadata", {})
            ))
        
        # 排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        if top_k:
            results = results[:top_k]
        
        return results


# 便捷函数
async def rerank_results(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = 10,
    use_lightweight: bool = False
) -> List[Dict[str, Any]]:
    """
    快速重排
    
    Args:
        query: 查询文本
        candidates: 候选列表
        top_k: 返回数量
        use_lightweight: 是否使用轻量级重排
        
    Returns:
        重排后的结果列表
    """
    if use_lightweight:
        reranker = LightweightReranker()
    else:
        reranker = Reranker()
    
    results = await reranker.rerank(query, candidates, top_k=top_k)
    
    return [
        {
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "content": r.content,
            "score": r.final_score,
            "rerank_score": r.rerank_score,
            "original_score": r.original_score,
            "metadata": r.metadata
        }
        for r in results
    ]
