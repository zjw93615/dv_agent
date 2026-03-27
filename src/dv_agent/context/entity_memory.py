"""实体记忆系统

从对话中提取和管理实体信息：
- 用户偏好
- 关键信息
- 持久化存储
- 上下文注入

Author: DV-Agent Team
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """实体类型"""
    USER_INFO = "user_info"           # 用户信息
    PREFERENCE = "preference"          # 用户偏好
    FACT = "fact"                      # 事实信息
    PROJECT = "project"                # 项目信息
    SKILL = "skill"                    # 技能信息
    RELATIONSHIP = "relationship"      # 关系信息
    CUSTOM = "custom"                  # 自定义


@dataclass
class Entity:
    """实体对象"""
    name: str                          # 实体名称
    value: Any                         # 实体值
    type: EntityType = EntityType.CUSTOM
    confidence: float = 1.0            # 置信度 (0.0 - 1.0)
    source: str = ""                   # 来源（如消息 ID）
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.type.value,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        """从字典创建"""
        entity_type = data.get("type", "custom")
        if isinstance(entity_type, str):
            entity_type = EntityType(entity_type)
        
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)
        
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now(timezone.utc)
        
        return cls(
            name=data["name"],
            value=data["value"],
            type=entity_type,
            confidence=data.get("confidence", 1.0),
            source=data.get("source", ""),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
        )


class EntityMemory:
    """实体记忆管理器
    
    管理从对话中提取的实体信息，支持：
    - 实体存储和检索
    - 持久化到文件
    - 基于相关性的实体注入
    
    Example:
        ```python
        memory = EntityMemory(user_id="user123")
        
        # 添加实体
        memory.add("name", "张三", EntityType.USER_INFO)
        memory.add("language", "Python", EntityType.PREFERENCE)
        
        # 获取实体
        name = memory.get("name")
        
        # 搜索相关实体
        related = memory.search("Python 编程")
        
        # 格式化为上下文
        context = memory.format_for_context()
        ```
    """
    
    def __init__(
        self,
        user_id: str,
        storage_dir: Optional[str] = None,
        auto_save: bool = True,
    ):
        """
        Args:
            user_id: 用户 ID
            storage_dir: 存储目录
            auto_save: 是否自动保存
        """
        self._user_id = user_id
        self._auto_save = auto_save
        self._entities: dict[str, Entity] = {}
        
        # 设置存储路径
        if storage_dir:
            self._storage_dir = Path(storage_dir)
        else:
            self._storage_dir = Path.cwd() / ".dv_agent" / "entity_memory"
        
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._storage_file = self._storage_dir / f"{user_id}.json"
        
        # 加载已有数据
        self._load()
    
    def add(
        self,
        name: str,
        value: Any,
        entity_type: EntityType = EntityType.CUSTOM,
        confidence: float = 1.0,
        source: str = "",
        **metadata,
    ) -> Entity:
        """添加或更新实体
        
        Args:
            name: 实体名称
            value: 实体值
            entity_type: 实体类型
            confidence: 置信度
            source: 来源
            **metadata: 额外元数据
            
        Returns:
            添加的实体对象
        """
        now = datetime.now(timezone.utc)
        
        if name in self._entities:
            # 更新现有实体
            entity = self._entities[name]
            entity.value = value
            entity.type = entity_type
            entity.confidence = confidence
            entity.source = source
            entity.updated_at = now
            entity.metadata.update(metadata)
        else:
            # 创建新实体
            entity = Entity(
                name=name,
                value=value,
                type=entity_type,
                confidence=confidence,
                source=source,
                created_at=now,
                updated_at=now,
                metadata=metadata,
            )
            self._entities[name] = entity
        
        if self._auto_save:
            self._save()
        
        logger.debug(f"Entity added/updated: {name} = {value}")
        return entity
    
    def get(self, name: str) -> Optional[Entity]:
        """获取实体
        
        Args:
            name: 实体名称
            
        Returns:
            实体对象，不存在返回 None
        """
        return self._entities.get(name)
    
    def get_value(self, name: str, default: Any = None) -> Any:
        """获取实体值
        
        Args:
            name: 实体名称
            default: 默认值
            
        Returns:
            实体值
        """
        entity = self.get(name)
        return entity.value if entity else default
    
    def remove(self, name: str) -> bool:
        """删除实体
        
        Args:
            name: 实体名称
            
        Returns:
            是否成功删除
        """
        if name in self._entities:
            del self._entities[name]
            if self._auto_save:
                self._save()
            return True
        return False
    
    def list_entities(
        self,
        entity_type: Optional[EntityType] = None,
    ) -> list[Entity]:
        """列出实体
        
        Args:
            entity_type: 筛选类型（可选）
            
        Returns:
            实体列表
        """
        entities = list(self._entities.values())
        if entity_type:
            entities = [e for e in entities if e.type == entity_type]
        return entities
    
    def search(
        self,
        query: str,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> list[Entity]:
        """搜索相关实体
        
        基于关键词匹配的简单搜索。
        
        Args:
            query: 搜索查询
            min_confidence: 最小置信度
            limit: 最大结果数
            
        Returns:
            匹配的实体列表
        """
        query_words = set(query.lower().split())
        results = []
        
        for entity in self._entities.values():
            if entity.confidence < min_confidence:
                continue
            
            # 计算匹配分数
            entity_text = f"{entity.name} {entity.value}".lower()
            entity_words = set(entity_text.split())
            
            overlap = len(query_words & entity_words)
            if overlap > 0:
                score = overlap / len(query_words)
                results.append((entity, score))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return [r[0] for r in results[:limit]]
    
    def format_for_context(
        self,
        entity_type: Optional[EntityType] = None,
        max_entities: int = 20,
    ) -> str:
        """格式化为上下文字符串
        
        Args:
            entity_type: 筛选类型
            max_entities: 最大实体数
            
        Returns:
            格式化的字符串
        """
        entities = self.list_entities(entity_type)
        
        if not entities:
            return ""
        
        # 按类型分组
        by_type: dict[EntityType, list[Entity]] = {}
        for entity in entities[:max_entities]:
            if entity.type not in by_type:
                by_type[entity.type] = []
            by_type[entity.type].append(entity)
        
        # 格式化输出
        lines = ["[Known Information about User]"]
        
        type_labels = {
            EntityType.USER_INFO: "User Info",
            EntityType.PREFERENCE: "Preferences",
            EntityType.FACT: "Facts",
            EntityType.PROJECT: "Projects",
            EntityType.SKILL: "Skills",
            EntityType.RELATIONSHIP: "Relationships",
            EntityType.CUSTOM: "Other",
        }
        
        for entity_type, type_entities in by_type.items():
            label = type_labels.get(entity_type, entity_type.value)
            lines.append(f"\n{label}:")
            for entity in type_entities:
                lines.append(f"  - {entity.name}: {entity.value}")
        
        return "\n".join(lines)
    
    def extract_from_text(
        self,
        text: str,
        source: str = "",
    ) -> list[Entity]:
        """从文本中提取实体（简单规则基础）
        
        Args:
            text: 输入文本
            source: 来源标识
            
        Returns:
            提取的实体列表
        """
        extracted = []
        
        # 模式匹配规则
        patterns = [
            # "我叫/我是 XXX"
            (r"我(?:叫|是|名字是)\s*([^\s,，。！？]+)", EntityType.USER_INFO, "name"),
            # "我喜欢/偏好 XXX"
            (r"我(?:喜欢|偏好|习惯)\s*(.+?)(?:[,，。！？]|$)", EntityType.PREFERENCE, None),
            # "我在做/开发 XXX 项目"
            (r"我(?:在做|正在开发|参与)\s*(.+?)(?:项目|系统)", EntityType.PROJECT, None),
            # "我会/熟悉 XXX"
            (r"我(?:会|熟悉|擅长)\s*(.+?)(?:[,，。！？]|$)", EntityType.SKILL, None),
        ]
        
        for pattern, entity_type, fixed_name in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                value = match.strip()
                if len(value) < 2 or len(value) > 50:
                    continue
                
                name = fixed_name or f"{entity_type.value}_{len(extracted)}"
                entity = self.add(
                    name=name,
                    value=value,
                    entity_type=entity_type,
                    confidence=0.7,  # 自动提取的置信度较低
                    source=source,
                )
                extracted.append(entity)
        
        return extracted
    
    def clear(self) -> None:
        """清空所有实体"""
        self._entities.clear()
        if self._auto_save:
            self._save()
    
    def _save(self) -> None:
        """保存到文件"""
        try:
            data = {
                "user_id": self._user_id,
                "entities": {
                    name: entity.to_dict()
                    for name, entity in self._entities.items()
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            self._storage_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug(f"Entity memory saved to {self._storage_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save entity memory: {e}")
    
    def _load(self) -> None:
        """从文件加载"""
        if not self._storage_file.exists():
            return
        
        try:
            data = json.loads(self._storage_file.read_text(encoding="utf-8"))
            entities_data = data.get("entities", {})
            
            for name, entity_data in entities_data.items():
                self._entities[name] = Entity.from_dict(entity_data)
            
            logger.debug(f"Loaded {len(self._entities)} entities for user {self._user_id}")
            
        except Exception as e:
            logger.warning(f"Failed to load entity memory: {e}")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        by_type = {}
        for entity in self._entities.values():
            type_name = entity.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        return {
            "user_id": self._user_id,
            "total_entities": len(self._entities),
            "by_type": by_type,
            "storage_file": str(self._storage_file),
        }


# ===== 实体记忆缓存 =====

_memory_cache: dict[str, EntityMemory] = {}


def get_entity_memory(
    user_id: str,
    storage_dir: Optional[str] = None,
) -> EntityMemory:
    """获取用户的实体记忆
    
    使用缓存避免重复加载。
    
    Args:
        user_id: 用户 ID
        storage_dir: 存储目录
        
    Returns:
        EntityMemory 实例
    """
    if user_id not in _memory_cache:
        _memory_cache[user_id] = EntityMemory(user_id, storage_dir)
    return _memory_cache[user_id]


def clear_memory_cache() -> None:
    """清空记忆缓存"""
    _memory_cache.clear()
