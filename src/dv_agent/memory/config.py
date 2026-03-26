"""
Memory System Configuration
记忆系统配置管理
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from ..config.logging import get_logger

logger = get_logger(__name__)


class ShortTermConfig(BaseModel):
    """短期记忆配置"""
    window_size: int = 20
    token_limit: int = 4000
    max_summary_tokens: int = 1000
    compress_model: str = "gpt-4o-mini"
    compress_threshold: int = 30


class PostgresConfig(BaseModel):
    """PostgreSQL 连接配置"""
    host: str = "localhost"
    port: int = 5432
    database: str = "dv_agent"
    user: str = "postgres"
    password: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    
    @property
    def dsn(self) -> str:
        """生成连接字符串"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def async_dsn(self) -> str:
        """生成异步连接字符串"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class MilvusConfig(BaseModel):
    """Milvus 连接配置"""
    host: str = "localhost"
    port: int = 19530
    user: str = ""
    password: str = ""
    user_memory_collection: str = "user_memory_vectors"
    enterprise_collection: str = "enterprise_knowledge"
    index_type: str = "IVF_FLAT"
    nlist: int = 1024
    metric_type: str = "COSINE"


class LongTermConfig(BaseModel):
    """长期记忆配置"""
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)


class EmbeddingConfig(BaseModel):
    """Embedding 配置"""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    batch_size: int = 32
    cache_ttl: int = 86400
    device: str = "cpu"


class RetrievalConfig(BaseModel):
    """检索配置"""
    vector_top_k: int = 20
    keyword_top_k: int = 10
    recency_top_k: int = 5
    recency_days: int = 7
    final_top_k: int = 10
    enable_rerank: bool = True
    max_rerank_candidates: int = 30
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    relevance_weight: float = 0.7
    cache_ttl: int = 300


class ExtractionConfig(BaseModel):
    """记忆提取配置"""
    enabled: bool = True
    min_turns: int = 3
    model: str = "gpt-4o-mini"


class ImportanceConfig(BaseModel):
    """重要性权重配置"""
    base_weights: dict[str, float] = Field(default_factory=lambda: {
        "entity": 0.7,
        "preference": 0.8,
        "fact": 0.6,
        "event": 0.5,
    })
    decay_rate: float = 0.01
    access_boost: float = 0.1


class ForgettingConfig(BaseModel):
    """遗忘配置"""
    soft_threshold: float = 0.1
    archive_days: int = 30
    delete_days: int = 180
    exempt_types: list[str] = Field(default_factory=lambda: ["entity"])
    exempt_access_count: int = 10


class LifecycleConfig(BaseModel):
    """生命周期管理配置"""
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    importance: ImportanceConfig = Field(default_factory=ImportanceConfig)
    forgetting: ForgettingConfig = Field(default_factory=ForgettingConfig)


class WorkerConfig(BaseModel):
    """后台任务配置"""
    importance_update_cron: str = "0 2 * * *"
    soft_forget_cron: str = "0 3 * * *"
    archive_cron: str = "0 4 * * 0"
    consistency_check_cron: str = "0 5 * * 0"
    batch_size: int = 1000


class MemoryConfig(BaseModel):
    """记忆系统总配置"""
    
    short_term: ShortTermConfig = Field(default_factory=ShortTermConfig)
    long_term: LongTermConfig = Field(default_factory=LongTermConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    
    # 功能开关
    enabled: bool = True
    
    @classmethod
    def from_yaml(cls, path: str | Path) -> "MemoryConfig":
        """从 YAML 文件加载配置"""
        path = Path(path)
        
        if not path.exists():
            logger.warning(f"Memory config file not found: {path}, using defaults")
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
        
        if raw_config is None:
            return cls()
        
        # 展开环境变量
        config = cls._expand_env_vars(raw_config)
        
        return cls(**config)
    
    @classmethod
    def _expand_env_vars(cls, config: dict) -> dict:
        """递归展开配置中的环境变量"""
        result = {}
        
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = cls._expand_env_vars(value)
            elif isinstance(value, str) and value.startswith("${"):
                # 解析 ${VAR:default} 格式
                result[key] = cls._parse_env_var(value)
            else:
                result[key] = value
        
        return result
    
    @staticmethod
    def _parse_env_var(value: str) -> Any:
        """解析 ${VAR:default} 格式的环境变量"""
        # 移除 ${ 和 }
        inner = value[2:-1]
        
        if ":" in inner:
            var_name, default = inner.split(":", 1)
        else:
            var_name = inner
            default = ""
        
        env_value = os.environ.get(var_name)
        
        if env_value is not None:
            # 尝试转换类型
            if env_value.lower() in ("true", "false"):
                return env_value.lower() == "true"
            try:
                return int(env_value)
            except ValueError:
                try:
                    return float(env_value)
                except ValueError:
                    return env_value
        
        return default


# 全局配置实例（懒加载）
_config: Optional[MemoryConfig] = None


def get_memory_config(config_path: str | Path | None = None) -> MemoryConfig:
    """
    获取记忆系统配置
    
    Args:
        config_path: 配置文件路径，默认为 config/memory.yaml
    
    Returns:
        MemoryConfig 实例
    """
    global _config
    
    if _config is None:
        if config_path is None:
            # 默认配置路径
            config_path = Path(__file__).parents[3] / "config" / "memory.yaml"
        
        _config = MemoryConfig.from_yaml(config_path)
        logger.info(f"Loaded memory config from: {config_path}")
    
    return _config


def reload_config(config_path: str | Path | None = None) -> MemoryConfig:
    """重新加载配置"""
    global _config
    _config = None
    return get_memory_config(config_path)
