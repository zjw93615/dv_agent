"""
Memory Data Models
记忆系统数据模型
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """记忆类型枚举"""
    FACT = "fact"           # 事实信息
    PREFERENCE = "preference"  # 用户偏好
    EVENT = "event"         # 事件记录
    ENTITY = "entity"       # 实体信息


class RelationType(str, Enum):
    """记忆关系类型"""
    RELATED = "related"       # 相关
    CONTRADICTS = "contradicts"  # 矛盾
    SUPERSEDES = "supersedes"    # 替代


class MemorySource(str, Enum):
    """记忆来源"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SHARED_KNOWLEDGE = "shared_knowledge"


class Memory(BaseModel):
    """长期记忆实体"""
    
    id: UUID = Field(default_factory=uuid4)
    user_id: str
    memory_type: MemoryType
    content: str
    
    # 来源追踪
    source_session: Optional[str] = None
    source_turn: Optional[int] = None
    
    # 评分和生命周期
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = Field(default=0, ge=0)
    decay_rate: float = Field(default=0.01, ge=0.0)
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: Optional[datetime] = None
    expired_at: Optional[datetime] = None  # 软删除标记
    
    # 扩展元数据
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    
    # 向量（可选，用于缓存）
    embedding: Optional[list[float]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: str,
        }
    
    @property
    def is_expired(self) -> bool:
        """是否已软删除"""
        return self.expired_at is not None
    
    def touch(self) -> None:
        """更新访问时间和计数"""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1
    
    def to_db_dict(self) -> dict:
        """转换为数据库字典（不含embedding）"""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "source_session": self.source_session,
            "source_turn": self.source_turn,
            "confidence": self.confidence,
            "importance": self.importance,
            "access_count": self.access_count,
            "decay_rate": self.decay_rate,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "expired_at": self.expired_at,
            "metadata": self.metadata,
        }


class MemoryRelation(BaseModel):
    """记忆关系"""
    
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    relation_type: RelationType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemorySearchResult(BaseModel):
    """记忆检索结果"""
    
    memory: Memory
    score: float = Field(ge=0.0, le=1.0)
    source: MemorySource
    
    # 可选的额外信息
    relevance_score: Optional[float] = None  # 相关性分数
    importance_score: Optional[float] = None  # 重要性分数


class ShortTermMessage(BaseModel):
    """短期记忆消息"""
    
    role: str  # user, assistant, tool, system
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    token_count: int = 0
    
    # 可选元数据
    name: Optional[str] = None  # tool name
    tool_call_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WindowConfig(BaseModel):
    """滑动窗口配置"""
    
    window_size: int = Field(default=20, ge=1)
    token_limit: int = Field(default=4000, ge=100)
    max_summary_tokens: int = Field(default=1000, ge=100)
    compress_model: str = "gpt-4o-mini"
    compress_threshold: int = Field(default=30, ge=1)


class SessionMemoryConfig(BaseModel):
    """Session级别的记忆配置"""
    
    # 短期记忆配置
    window_config: WindowConfig = Field(default_factory=WindowConfig)
    
    # 功能开关
    enable_short_term: bool = True
    enable_extraction: bool = True
    enable_long_term: bool = True
    
    # 检索配置
    retrieval_top_k: int = Field(default=10, ge=1)
    enable_rerank: bool = True


class ExtractedMemory(BaseModel):
    """从对话中提取的记忆（LLM输出格式）"""
    
    memory_type: MemoryType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class EnterpriseKnowledge(BaseModel):
    """企业知识条目"""
    
    id: UUID = Field(default_factory=uuid4)
    title: str
    content: str
    category: Optional[str] = None
    dept_id: Optional[str] = None  # None表示全员可见
    
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # 向量
    embedding: Optional[list[float]] = None
