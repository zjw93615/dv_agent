"""
RAG Configuration

统一的RAG系统配置管理。

支持：
1. YAML配置文件加载
2. 环境变量覆盖
3. 配置验证
4. 运行时配置更新
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import yaml

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """向量化配置"""
    model_name: str = "BAAI/bge-m3"
    model_path: Optional[str] = None       # 本地模型路径
    device: str = "auto"                    # auto/cuda/cpu
    max_length: int = 8192
    batch_size: int = 32
    use_fp16: bool = True
    
    # 缓存配置
    cache_enabled: bool = True
    cache_max_size: int = 10000
    
    # 稀疏向量配置
    sparse_top_k: int = 256
    sparse_min_weight: float = 0.0


@dataclass
class PipelineConfig:
    """文档处理流水线配置"""
    # 切分配置
    chunk_size: int = 512
    chunk_overlap: int = 50
    min_chunk_size: int = 50
    
    # 清洗配置
    remove_extra_whitespace: bool = True
    remove_urls: bool = False
    normalize_unicode: bool = True
    
    # 元数据配置
    extract_titles: bool = True
    detect_language: bool = True
    
    # 处理限制
    max_file_size_mb: int = 100
    supported_formats: List[str] = field(default_factory=lambda: [
        "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
        "html", "htm", "md", "txt", "csv", "json"
    ])


@dataclass
class MilvusConfig:
    """Milvus配置"""
    host: str = "localhost"
    port: int = 19530
    user: str = ""
    password: str = ""
    
    # Collection配置
    dense_collection: str = "doc_dense_embeddings"
    sparse_collection: str = "doc_sparse_embeddings"
    
    # 索引配置
    dense_index_type: str = "HNSW"
    dense_metric_type: str = "IP"  # Inner Product
    hnsw_m: int = 16
    hnsw_ef_construction: int = 256
    
    # 搜索配置
    search_ef: int = 64
    consistency_level: str = "Strong"


@dataclass
class PostgresConfig:
    """PostgreSQL配置"""
    host: str = "localhost"
    port: int = 5432
    database: str = "dv_agent"
    user: str = "postgres"
    password: str = ""
    
    # 连接池配置
    min_pool_size: int = 5
    max_pool_size: int = 20
    
    # 全文搜索配置
    ts_config: str = "simple"


@dataclass
class MinIOConfig:
    """MinIO配置"""
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    secure: bool = False
    
    # Bucket配置
    bucket_name: str = "dv-agent-documents"
    
    # 上传配置
    part_size: int = 10 * 1024 * 1024  # 10MB


@dataclass
class RetrievalConfig:
    """检索配置"""
    # 召回配置
    dense_top_k: int = 30
    sparse_top_k: int = 30
    bm25_top_k: int = 30
    
    # RRF配置
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 0.8
    bm25_weight: float = 0.6
    
    # 查询扩展配置
    enable_query_expansion: bool = True
    num_query_variations: int = 3
    use_hyde: bool = False
    
    # Reranker配置
    enable_rerank: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_model_path: Optional[str] = None
    rerank_top_k: int = 50
    use_lightweight_rerank: bool = False
    
    # 缓存配置
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600


@dataclass
class QuotaConfig:
    """租户配额配置"""
    max_documents: int = 10000
    max_storage_gb: float = 10.0
    max_chunks_per_document: int = 1000


@dataclass
class RAGConfig:
    """RAG系统总配置"""
    # 子配置
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    minio: MinIOConfig = field(default_factory=MinIOConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    quota: QuotaConfig = field(default_factory=QuotaConfig)
    
    # 全局配置
    debug: bool = False
    log_level: str = "INFO"


class RAGConfigLoader:
    """
    RAG配置加载器
    
    支持从YAML文件和环境变量加载配置。
    """
    
    # 环境变量前缀
    ENV_PREFIX = "RAG_"
    
    # 默认配置文件路径
    DEFAULT_CONFIG_PATHS = [
        "config/rag.yaml",
        "config/rag.yml",
        "../config/rag.yaml",
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化
        
        Args:
            config_path: 配置文件路径（可选）
        """
        self.config_path = config_path
        self._config: Optional[RAGConfig] = None
    
    def load(self) -> RAGConfig:
        """
        加载配置
        
        优先级：环境变量 > 配置文件 > 默认值
        
        Returns:
            RAGConfig实例
        """
        # 从文件加载
        file_config = self._load_from_file()
        
        # 创建配置对象
        config = self._build_config(file_config)
        
        # 应用环境变量覆盖
        config = self._apply_env_overrides(config)
        
        self._config = config
        logger.info(f"RAG config loaded: debug={config.debug}, log_level={config.log_level}")
        
        return config
    
    def _load_from_file(self) -> Dict[str, Any]:
        """从YAML文件加载配置"""
        config_path = self.config_path
        
        # 自动查找配置文件
        if config_path is None:
            for path in self.DEFAULT_CONFIG_PATHS:
                if Path(path).exists():
                    config_path = path
                    break
        
        if config_path is None or not Path(config_path).exists():
            logger.warning("No RAG config file found, using defaults")
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            logger.info(f"Loaded RAG config from {config_path}")
            return config_data
        except Exception as e:
            logger.error(f"Failed to load RAG config from {config_path}: {e}")
            return {}
    
    def _build_config(self, file_config: Dict[str, Any]) -> RAGConfig:
        """从字典构建配置对象"""
        return RAGConfig(
            embedding=self._build_embedding_config(file_config.get("embedding", {})),
            pipeline=self._build_pipeline_config(file_config.get("pipeline", {})),
            milvus=self._build_milvus_config(file_config.get("milvus", {})),
            postgres=self._build_postgres_config(file_config.get("postgres", {})),
            minio=self._build_minio_config(file_config.get("minio", {})),
            retrieval=self._build_retrieval_config(file_config.get("retrieval", {})),
            quota=self._build_quota_config(file_config.get("quota", {})),
            debug=file_config.get("debug", False),
            log_level=file_config.get("log_level", "INFO")
        )
    
    def _build_embedding_config(self, data: Dict[str, Any]) -> EmbeddingConfig:
        """构建向量化配置"""
        # 支持嵌套的 model 配置
        model_config = data.get("model", {})
        sparse_config = data.get("sparse", {})
        cache_config = data.get("cache", {})
        
        return EmbeddingConfig(
            model_name=model_config.get("name") or data.get("model_name", "BAAI/bge-m3"),
            model_path=data.get("model_path"),
            device=model_config.get("device") or data.get("device", "auto"),
            max_length=data.get("max_length", 8192),
            batch_size=data.get("batch_size", 32),
            use_fp16=model_config.get("use_fp16", data.get("use_fp16", True)),
            cache_enabled=cache_config.get("enabled", data.get("cache_enabled", True)),
            cache_max_size=data.get("cache_max_size", 10000),
            sparse_top_k=sparse_config.get("max_features", data.get("sparse_top_k", 256)),
            sparse_min_weight=sparse_config.get("min_weight", data.get("sparse_min_weight", 0.0))
        )
    
    def _build_pipeline_config(self, data: Dict[str, Any]) -> PipelineConfig:
        """构建流水线配置"""
        return PipelineConfig(
            chunk_size=data.get("chunk_size", 512),
            chunk_overlap=data.get("chunk_overlap", 50),
            min_chunk_size=data.get("min_chunk_size", 50),
            remove_extra_whitespace=data.get("remove_extra_whitespace", True),
            remove_urls=data.get("remove_urls", False),
            normalize_unicode=data.get("normalize_unicode", True),
            extract_titles=data.get("extract_titles", True),
            detect_language=data.get("detect_language", True),
            max_file_size_mb=data.get("max_file_size_mb", 100),
            supported_formats=data.get("supported_formats", PipelineConfig().supported_formats)
        )
    
    def _build_milvus_config(self, data: Dict[str, Any]) -> MilvusConfig:
        """构建Milvus配置"""
        return MilvusConfig(
            host=data.get("host", "localhost"),
            port=data.get("port", 19530),
            user=data.get("user", ""),
            password=data.get("password", ""),
            dense_collection=data.get("dense_collection", "doc_dense_embeddings"),
            sparse_collection=data.get("sparse_collection", "doc_sparse_embeddings"),
            dense_index_type=data.get("dense_index_type", "HNSW"),
            dense_metric_type=data.get("dense_metric_type", "IP"),
            hnsw_m=data.get("hnsw_m", 16),
            hnsw_ef_construction=data.get("hnsw_ef_construction", 256),
            search_ef=data.get("search_ef", 64),
            consistency_level=data.get("consistency_level", "Strong")
        )
    
    def _build_postgres_config(self, data: Dict[str, Any]) -> PostgresConfig:
        """构建PostgreSQL配置"""
        return PostgresConfig(
            host=data.get("host", "localhost"),
            port=data.get("port", 5432),
            database=data.get("database", "dv_agent"),
            user=data.get("user", "postgres"),
            password=data.get("password", ""),
            min_pool_size=data.get("min_pool_size", 5),
            max_pool_size=data.get("max_pool_size", 20),
            ts_config=data.get("ts_config", "simple")
        )
    
    def _build_minio_config(self, data: Dict[str, Any]) -> MinIOConfig:
        """构建MinIO配置"""
        return MinIOConfig(
            endpoint=data.get("endpoint", "localhost:9000"),
            access_key=data.get("access_key", "minioadmin"),
            secret_key=data.get("secret_key", "minioadmin"),
            secure=data.get("secure", False),
            bucket_name=data.get("bucket_name", "dv-agent-documents"),
            part_size=data.get("part_size", 10 * 1024 * 1024)
        )
    
    def _build_retrieval_config(self, data: Dict[str, Any]) -> RetrievalConfig:
        """构建检索配置"""
        return RetrievalConfig(
            dense_top_k=data.get("dense_top_k", 30),
            sparse_top_k=data.get("sparse_top_k", 30),
            bm25_top_k=data.get("bm25_top_k", 30),
            rrf_k=data.get("rrf_k", 60),
            dense_weight=data.get("dense_weight", 1.0),
            sparse_weight=data.get("sparse_weight", 0.8),
            bm25_weight=data.get("bm25_weight", 0.6),
            enable_query_expansion=data.get("enable_query_expansion", True),
            num_query_variations=data.get("num_query_variations", 3),
            use_hyde=data.get("use_hyde", False),
            enable_rerank=data.get("enable_rerank", True),
            reranker_model=data.get("reranker_model", "BAAI/bge-reranker-v2-m3"),
            reranker_model_path=data.get("reranker_model_path"),
            rerank_top_k=data.get("rerank_top_k", 50),
            use_lightweight_rerank=data.get("use_lightweight_rerank", False),
            cache_enabled=data.get("cache_enabled", True),
            cache_ttl_seconds=data.get("cache_ttl_seconds", 3600)
        )
    
    def _build_quota_config(self, data: Dict[str, Any]) -> QuotaConfig:
        """构建配额配置"""
        return QuotaConfig(
            max_documents=data.get("max_documents", 10000),
            max_storage_gb=data.get("max_storage_gb", 10.0),
            max_chunks_per_document=data.get("max_chunks_per_document", 1000)
        )
    
    def _apply_env_overrides(self, config: RAGConfig) -> RAGConfig:
        """应用环境变量覆盖"""
        # Embedding配置
        if os.getenv(f"{self.ENV_PREFIX}EMBEDDING_MODEL_PATH"):
            config.embedding.model_path = os.getenv(f"{self.ENV_PREFIX}EMBEDDING_MODEL_PATH")
        if os.getenv(f"{self.ENV_PREFIX}EMBEDDING_DEVICE"):
            config.embedding.device = os.getenv(f"{self.ENV_PREFIX}EMBEDDING_DEVICE")
        
        # Milvus配置
        if os.getenv(f"{self.ENV_PREFIX}MILVUS_HOST"):
            config.milvus.host = os.getenv(f"{self.ENV_PREFIX}MILVUS_HOST")
        if os.getenv(f"{self.ENV_PREFIX}MILVUS_PORT"):
            config.milvus.port = int(os.getenv(f"{self.ENV_PREFIX}MILVUS_PORT"))
        if os.getenv(f"{self.ENV_PREFIX}MILVUS_USER"):
            config.milvus.user = os.getenv(f"{self.ENV_PREFIX}MILVUS_USER")
        if os.getenv(f"{self.ENV_PREFIX}MILVUS_PASSWORD"):
            config.milvus.password = os.getenv(f"{self.ENV_PREFIX}MILVUS_PASSWORD")
        
        # PostgreSQL配置
        if os.getenv(f"{self.ENV_PREFIX}POSTGRES_HOST"):
            config.postgres.host = os.getenv(f"{self.ENV_PREFIX}POSTGRES_HOST")
        if os.getenv(f"{self.ENV_PREFIX}POSTGRES_PORT"):
            config.postgres.port = int(os.getenv(f"{self.ENV_PREFIX}POSTGRES_PORT"))
        if os.getenv(f"{self.ENV_PREFIX}POSTGRES_DATABASE"):
            config.postgres.database = os.getenv(f"{self.ENV_PREFIX}POSTGRES_DATABASE")
        if os.getenv(f"{self.ENV_PREFIX}POSTGRES_USER"):
            config.postgres.user = os.getenv(f"{self.ENV_PREFIX}POSTGRES_USER")
        if os.getenv(f"{self.ENV_PREFIX}POSTGRES_PASSWORD"):
            config.postgres.password = os.getenv(f"{self.ENV_PREFIX}POSTGRES_PASSWORD")
        
        # MinIO配置
        if os.getenv(f"{self.ENV_PREFIX}MINIO_ENDPOINT"):
            config.minio.endpoint = os.getenv(f"{self.ENV_PREFIX}MINIO_ENDPOINT")
        if os.getenv(f"{self.ENV_PREFIX}MINIO_ACCESS_KEY"):
            config.minio.access_key = os.getenv(f"{self.ENV_PREFIX}MINIO_ACCESS_KEY")
        if os.getenv(f"{self.ENV_PREFIX}MINIO_SECRET_KEY"):
            config.minio.secret_key = os.getenv(f"{self.ENV_PREFIX}MINIO_SECRET_KEY")
        
        # Reranker配置
        if os.getenv(f"{self.ENV_PREFIX}RERANKER_MODEL_PATH"):
            config.retrieval.reranker_model_path = os.getenv(f"{self.ENV_PREFIX}RERANKER_MODEL_PATH")
        
        # 全局配置
        if os.getenv(f"{self.ENV_PREFIX}DEBUG"):
            config.debug = os.getenv(f"{self.ENV_PREFIX}DEBUG", "").lower() in ("true", "1", "yes")
        if os.getenv(f"{self.ENV_PREFIX}LOG_LEVEL"):
            config.log_level = os.getenv(f"{self.ENV_PREFIX}LOG_LEVEL")
        
        return config
    
    @property
    def config(self) -> RAGConfig:
        """获取配置（延迟加载）"""
        if self._config is None:
            self._config = self.load()
        return self._config


# 全局配置实例
_config_loader: Optional[RAGConfigLoader] = None


def get_rag_config(config_path: Optional[str] = None) -> RAGConfig:
    """
    获取RAG配置
    
    Args:
        config_path: 配置文件路径（首次调用时有效）
        
    Returns:
        RAGConfig实例
    """
    global _config_loader
    
    if _config_loader is None:
        _config_loader = RAGConfigLoader(config_path)
    
    return _config_loader.config


def reload_rag_config(config_path: Optional[str] = None) -> RAGConfig:
    """
    重新加载RAG配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        新的RAGConfig实例
    """
    global _config_loader
    
    _config_loader = RAGConfigLoader(config_path)
    return _config_loader.load()
