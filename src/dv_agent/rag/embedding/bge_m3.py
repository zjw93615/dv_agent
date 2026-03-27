"""
BGE-M3 Embedding Service
BGE-M3 向量化服务

提供稠密向量和稀疏向量的双重生成能力。
支持延迟加载、GPU/CPU自动检测、向量缓存。
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SparseVector:
    """稀疏向量表示"""
    
    indices: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    
    def __len__(self) -> int:
        return len(self.indices)
    
    def to_dict(self) -> dict:
        """转换为字典格式（Milvus 兼容）"""
        return {int(idx): float(val) for idx, val in zip(self.indices, self.values)}
    
    @classmethod
    def from_dict(cls, data: dict) -> "SparseVector":
        """从字典创建"""
        indices = list(data.keys())
        values = list(data.values())
        return cls(indices=indices, values=values)
    
    def filter_by_weight(
        self,
        min_weight: float = 0.0,
        top_k: Optional[int] = None,
    ) -> "SparseVector":
        """
        过滤稀疏向量
        
        Args:
            min_weight: 最小权重阈值
            top_k: 保留权重最高的 K 个元素
            
        Returns:
            过滤后的稀疏向量
        """
        # 过滤低权重
        pairs = [
            (idx, val) for idx, val in zip(self.indices, self.values)
            if val >= min_weight
        ]
        
        # 按权重排序并取 Top-K
        if top_k and len(pairs) > top_k:
            pairs = sorted(pairs, key=lambda x: x[1], reverse=True)[:top_k]
        
        if not pairs:
            return SparseVector()
        
        indices, values = zip(*pairs)
        return SparseVector(indices=list(indices), values=list(values))


@dataclass
class EmbeddingResult:
    """向量化结果"""
    
    text: str
    dense_embedding: list[float] = field(default_factory=list)
    sparse_embedding: Optional[SparseVector] = None
    
    @property
    def dense_dim(self) -> int:
        """稠密向量维度"""
        return len(self.dense_embedding)
    
    @property
    def sparse_len(self) -> int:
        """稀疏向量非零元素数量"""
        return len(self.sparse_embedding) if self.sparse_embedding else 0


class BGEM3Embedder:
    """
    BGE-M3 向量化服务
    
    基于 FlagEmbedding 库的 BGE-M3 模型，支持：
    - 稠密向量（1024维）
    - 稀疏向量（词汇级权重）
    - 延迟加载模型
    - GPU/CPU 自动检测
    - 向量缓存
    """
    
    DEFAULT_MODEL = "BAAI/bge-m3"
    DEFAULT_DIM = 1024
    
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        use_fp16: bool = True,
        max_length: int = 8192,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        sparse_weight_threshold: float = 0.0,
        sparse_top_k: Optional[int] = None,
    ):
        """
        初始化向量化服务
        
        Args:
            model_name: 模型名称或路径
            device: 设备（cuda/cpu/auto）
            use_fp16: 是否使用半精度
            max_length: 最大序列长度
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存过期时间（秒）
            sparse_weight_threshold: 稀疏向量权重过滤阈值
            sparse_top_k: 稀疏向量 Top-K 过滤
        """
        self.model_name = model_name
        self.device = device or self._detect_device()
        self.use_fp16 = use_fp16 and self.device == "cuda"
        self.max_length = max_length
        
        # 缓存配置
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[EmbeddingResult, float]] = {}
        
        # 稀疏向量过滤配置
        self.sparse_weight_threshold = sparse_weight_threshold
        self.sparse_top_k = sparse_top_k
        
        # 延迟加载
        self._model = None
        self._model_loaded = False
        
        logger.info(
            f"BGEM3Embedder initialized: model={model_name}, "
            f"device={self.device}, fp16={self.use_fp16}"
        )
    
    def _detect_device(self) -> str:
        """自动检测设备"""
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                logger.info(f"CUDA available: {device_name}")
                return "cuda"
        except ImportError:
            pass
        
        logger.info("Using CPU for embedding")
        return "cpu"
    
    def _load_model(self) -> None:
        """延迟加载模型"""
        print(f"\n[BGE-M3] >>> _load_model() called")
        print(f"[BGE-M3] >>> Model already loaded: {self._model_loaded}")
        
        if self._model_loaded:
            print(f"[BGE-M3] >>> Model already loaded, skipping")
            return
        
        print(f"[BGE-M3] >>> Starting model loading process...")
        
        try:
            from FlagEmbedding import BGEM3FlagModel
            import time
            
            print(f"\n{'='*60}")
            print(f"[BGE-M3] 🔄 Loading model: {self.model_name}")
            print(f"[BGE-M3] Device: {self.device}, FP16: {self.use_fp16}")
            print(f"[BGE-M3] This may take 30-60 seconds...")
            print(f"{'='*60}\n")
            
            logger.info(f"[BGE-M3] Loading model: {self.model_name}")
            logger.info(f"[BGE-M3] Device: {self.device}, FP16: {self.use_fp16}")
            logger.info(f"[BGE-M3] This may take a minute for first-time loading...")
            
            load_start = time.time()
            
            print(f"[BGE-M3] Step 1/4: Creating BGEM3FlagModel instance...")
            logger.info(f"[BGE-M3] Step 1/4: Creating BGEM3FlagModel instance...")
            init_start = time.time()
            
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16,
                device=self.device,
            )
            
            init_time = time.time() - init_start
            print(f"[BGE-M3] Step 1/4: ✅ Model instance created in {init_time:.2f}s")
            logger.info(f"[BGE-M3] Step 1/4: Model instance created in {init_time:.2f}s")
            
            # 强制将模型移动到指定设备（修复 FlagEmbedding 的 device 参数问题）
            import torch
            if self.device == "cuda" and torch.cuda.is_available():
                if hasattr(self._model, 'model'):
                    print(f"[BGE-M3] Step 2/4: Moving model to CUDA...")
                    logger.info(f"[BGE-M3] Step 2/4: Moving model to CUDA...")
                    cuda_start = time.time()
                    
                    self._model.model = self._model.model.to('cuda')
                    print(f"[BGE-M3]   - Main model moved to CUDA ({time.time() - cuda_start:.2f}s)")
                    logger.info(f"[BGE-M3]   - Main model moved ({time.time() - cuda_start:.2f}s)")
                    
                    if hasattr(self._model, 'colbert_linear') and self._model.colbert_linear is not None:
                        self._model.colbert_linear = self._model.colbert_linear.to('cuda')
                        print(f"[BGE-M3]   - ColBERT linear moved to CUDA")
                        logger.info(f"[BGE-M3]   - ColBERT linear moved")
                    
                    if hasattr(self._model, 'sparse_linear') and self._model.sparse_linear is not None:
                        self._model.sparse_linear = self._model.sparse_linear.to('cuda')
                        print(f"[BGE-M3]   - Sparse linear moved to CUDA")
                        logger.info(f"[BGE-M3]   - Sparse linear moved")
                    
                    cuda_time = time.time() - cuda_start
                    print(f"[BGE-M3] Step 2/4: ✅ CUDA transfer completed in {cuda_time:.2f}s")
                    logger.info(f"[BGE-M3] Step 2/4: CUDA transfer completed in {cuda_time:.2f}s")
            
            self._model_loaded = True
            load_time = time.time() - load_start
            
            # 验证设备
            try:
                if hasattr(self._model, 'model'):
                    actual_device = next(self._model.model.parameters()).device
                    logger.info(f"[BGE-M3] ✅ Model loaded successfully in {load_time:.2f}s on device: {actual_device}")
                    print(f"[BGE-M3] ✅ Model ready on {actual_device} (took {load_time:.2f}s)")
                    
                    # 如果设备不匹配，给出警告
                    if self.device == "cuda" and actual_device.type != "cuda":
                        logger.error(f"[BGE-M3] WARNING: Requested cuda but model is on {actual_device}")
                        logger.error(f"[BGE-M3] This will result in slow performance!")
                        print(f"[BGE-M3] ��️  WARNING: Model is on {actual_device}, not cuda!")
                else:
                    logger.info(f"[BGE-M3] ✅ Model loaded successfully in {load_time:.2f}s (device verification skipped)")
                    print(f"[BGE-M3] ✅ Model ready (took {load_time:.2f}s)")
            except Exception as e:
                logger.warning(f"[BGE-M3] Could not verify device: {e}")
                logger.info(f"[BGE-M3] Model loaded successfully in {load_time:.2f}s")
            
        except ImportError:
            raise ImportError(
                "FlagEmbedding not installed. "
                "Run: pip install FlagEmbedding"
            )
        except Exception as e:
            logger.error(f"Failed to load BGE-M3 model: {e}")
            raise
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _get_from_cache(self, text: str) -> Optional[EmbeddingResult]:
        """从缓存获取"""
        if not self.cache_enabled:
            return None
        
        import time
        
        key = self._get_cache_key(text)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return result
            else:
                del self._cache[key]
        
        return None
    
    def _set_cache(self, text: str, result: EmbeddingResult) -> None:
        """设置缓存"""
        if not self.cache_enabled:
            return
        
        import time
        
        key = self._get_cache_key(text)
        self._cache[key] = (result, time.time())
    
    def embed(
        self,
        text: str,
        return_sparse: bool = True,
        return_dense: bool = True,
    ) -> EmbeddingResult:
        """
        生成单个文本的向量
        
        Args:
            text: 输入文本
            return_sparse: 是否返回稀疏向量
            return_dense: 是否返回稠密向量
            
        Returns:
            向量化结果
        """
        # 检查缓存
        cached = self._get_from_cache(text)
        if cached:
            return cached
        
        # 确保模型已加载
        self._load_model()
        
        # 生成向量
        outputs = self._model.encode(
            [text],
            return_dense=return_dense,
            return_sparse=return_sparse,
            max_length=self.max_length,
        )
        
        result = EmbeddingResult(text=text)
        
        # 处理稠密向量
        if return_dense and "dense_vecs" in outputs:
            dense_vec = outputs["dense_vecs"][0]
            if isinstance(dense_vec, np.ndarray):
                result.dense_embedding = dense_vec.tolist()
            else:
                result.dense_embedding = list(dense_vec)
        
        # 处理稀疏向量
        if return_sparse and "lexical_weights" in outputs:
            lexical_weights = outputs["lexical_weights"][0]
            sparse = SparseVector(
                indices=list(lexical_weights.keys()),
                values=list(lexical_weights.values()),
            )
            
            # 应用过滤
            result.sparse_embedding = sparse.filter_by_weight(
                min_weight=self.sparse_weight_threshold,
                top_k=self.sparse_top_k,
            )
        
        # 缓存结果
        self._set_cache(text, result)
        
        return result
    
    def embed_batch(
        self,
        texts: list[str],
        return_sparse: bool = True,
        return_dense: bool = True,
        batch_size: int = 32,
    ) -> list[EmbeddingResult]:
        """
        批量生成向量
        
        Args:
            texts: 输入文本列表
            return_sparse: 是否返回稀疏向量
            return_dense: 是否返回稠密向量
            batch_size: 批处理大小
            
        Returns:
            向量化结果列表
        """
        results = []
        uncached_texts = []
        uncached_indices = []
        
        # 检查缓存
        for i, text in enumerate(texts):
            cached = self._get_from_cache(text)
            if cached:
                results.append((i, cached))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # 处理未缓存的文本
        if uncached_texts:
            logger.info(f"[EMBEDDING] 有 {len(uncached_texts)} 个未缓存文本需要处理")
            logger.info(f"[EMBEDDING] 正在加载模型...")
            
            self._load_model()
            
            logger.info(f"[EMBEDDING] 模型加载完成，开始嵌入...")
            
            total_batches = (len(uncached_texts) + batch_size - 1) // batch_size
            logger.info(f"[EMBEDDING] 开始批量嵌入: {len(uncached_texts)} 文本, {total_batches} 批次")
            
            # 分批处理
            for batch_start in range(0, len(uncached_texts), batch_size):
                batch_end = min(batch_start + batch_size, len(uncached_texts))
                batch_texts = uncached_texts[batch_start:batch_end]
                batch_num = batch_start // batch_size + 1
                
                batch_lengths = [len(t) for t in batch_texts]
                print(f"[EMBEDDING] 📦 批次 {batch_num}/{total_batches}: {len(batch_texts)} 文本, 总字符: {sum(batch_lengths):,}")
                logger.info(f"[EMBEDDING] 处理批次 {batch_num}/{total_batches} ({len(batch_texts)} 文本)...")
                
                import time
                encode_start = time.time()
                
                print(f"[EMBEDDING]   ⏳ 正在调用 model.encode()...")
                logger.info(f"[EMBEDDING]   调用 model.encode()...")
                outputs = self._model.encode(
                    batch_texts,
                    return_dense=return_dense,
                    return_sparse=return_sparse,
                    max_length=self.max_length,
                )
                encode_time = time.time() - encode_start
                print(f"[EMBEDDING]   ✅ 批次完成, 耗时: {encode_time:.2f}s, 速度: {len(batch_texts)/encode_time:.1f} 文本/秒")
                logger.info(f"[EMBEDDING]   model.encode() 返回")
                logger.info(f"[EMBEDDING] 批次 {batch_num} 完成, 耗时: {encode_time:.2f}s")
                
                for j, text in enumerate(batch_texts):
                    result = EmbeddingResult(text=text)
                    
                    if return_dense and "dense_vecs" in outputs:
                        dense_vec = outputs["dense_vecs"][j]
                        if isinstance(dense_vec, np.ndarray):
                            result.dense_embedding = dense_vec.tolist()
                        else:
                            result.dense_embedding = list(dense_vec)
                    
                    if return_sparse and "lexical_weights" in outputs:
                        lexical_weights = outputs["lexical_weights"][j]
                        sparse = SparseVector(
                            indices=list(lexical_weights.keys()),
                            values=list(lexical_weights.values()),
                        )
                        result.sparse_embedding = sparse.filter_by_weight(
                            min_weight=self.sparse_weight_threshold,
                            top_k=self.sparse_top_k,
                        )
                    
                    # 缓存结果
                    self._set_cache(text, result)
                    
                    idx = uncached_indices[batch_start + j]
                    results.append((idx, result))
        
        # 按原始顺序排序
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]
    
    def embed_query(self, query: str) -> EmbeddingResult:
        """
        生成查询向量（针对检索优化）
        
        Args:
            query: 查询文本
            
        Returns:
            向量化结果
        """
        # BGE-M3 对查询和文档使用相同的编码方式
        return self.embed(query, return_sparse=True, return_dense=True)
    
    def embed_documents(
        self,
        documents: list[str],
        batch_size: int = 32,
    ) -> list[EmbeddingResult]:
        """
        批量生成文档向量
        
        Args:
            documents: 文档列表
            batch_size: 批处理大小
            
        Returns:
            向量化结果列表
        """
        print(f"\n[EMBEDDING] 📝 embed_documents() 被调用:")
        print(f"[EMBEDDING]   - 文档数量: {len(documents)}")
        print(f"[EMBEDDING]   - 批处理大小: {batch_size}")
        
        # 显示文档长度统计
        if documents:
            lengths = [len(doc) for doc in documents]
            print(f"[EMBEDDING]   - 文档长度: min={min(lengths)}, max={max(lengths)}, avg={sum(lengths)//len(lengths)}")
            print(f"[EMBEDDING]   - 总字符数: {sum(lengths):,}")
            
            # 警告超长文档
            long_docs = [i for i, l in enumerate(lengths) if l > 10000]
            if long_docs:
                print(f"[EMBEDDING]   ⚠️  发现 {len(long_docs)} 个超长文档 (>10K字符): {long_docs[:5]}")
        
        logger.info(f"[EMBEDDING] embed_documents() 被调用: {len(documents)} 个文档")
        logger.info(f"[EMBEDDING] batch_size: {batch_size}")
        logger.info(f"[EMBEDDING] 模型已加载: {self._model_loaded}")
        
        result = self.embed_batch(
            documents,
            return_sparse=True,
            return_dense=True,
            batch_size=batch_size,
        )
        
        logger.info(f"[EMBEDDING] embed_documents() 完成，返回 {len(result)} 个结果")
        return result
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("Embedding cache cleared")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计"""
        import time
        
        total = len(self._cache)
        valid = sum(
            1 for _, (_, ts) in self._cache.items()
            if time.time() - ts < self.cache_ttl
        )
        
        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
            "cache_enabled": self.cache_enabled,
            "cache_ttl": self.cache_ttl,
        }
    
    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model_loaded
    
    @property
    def embedding_dim(self) -> int:
        """稠密向量维度"""
        return self.DEFAULT_DIM
    
    @classmethod
    def from_config(cls, config: dict) -> "BGEM3Embedder":
        """
        从配置创建
        
        Args:
            config: 配置字典
            
        Returns:
            BGEM3Embedder 实例
        """
        return cls(
            model_name=config.get("model_name", cls.DEFAULT_MODEL),
            device=config.get("device"),
            use_fp16=config.get("use_fp16", True),
            max_length=config.get("max_length", 8192),
            cache_enabled=config.get("cache_enabled", True),
            cache_ttl=config.get("cache_ttl", 3600),
            sparse_weight_threshold=config.get("sparse_weight_threshold", 0.0),
            sparse_top_k=config.get("sparse_top_k"),
        )
