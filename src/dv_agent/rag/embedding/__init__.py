"""
RAG Embedding Module
向量化服务模块

提供 BGE-M3 双向量（稠密+稀疏）生成能力。
"""

from .bge_m3 import BGEM3Embedder, EmbeddingResult

__all__ = [
    "BGEM3Embedder",
    "EmbeddingResult",
]
