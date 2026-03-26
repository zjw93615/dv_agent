"""
意图识别数据模型
定义意图类型、识别结果和路由规则
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """意图类型"""
    # 信息查询
    QUERY = "query"                    # 通用查询
    SEARCH = "search"                  # 搜索
    KNOWLEDGE = "knowledge"            # 知识问答
    
    # 任务执行
    TASK = "task"                      # 通用任务
    CODE = "code"                      # 代码相关
    FILE = "file"                      # 文件操作
    DATA = "data"                      # 数据处理
    
    # 创作生成
    CREATIVE = "creative"              # 创意写作
    SUMMARY = "summary"                # 总结摘要
    TRANSLATE = "translate"            # 翻译
    
    # 对话控制
    CHAT = "chat"                      # 闲聊
    GREETING = "greeting"              # 问候
    FAREWELL = "farewell"              # 告别
    CLARIFY = "clarify"                # 澄清/追问
    
    # 系统控制
    COMMAND = "command"                # 系统命令
    SETTINGS = "settings"              # 设置
    HELP = "help"                      # 帮助
    CANCEL = "cancel"                  # 取消
    
    # 特殊
    UNKNOWN = "unknown"                # 未知意图
    MULTI = "multi"                    # 多意图


class IntentConfidence(str, Enum):
    """置信度级别"""
    HIGH = "high"          # > 0.8
    MEDIUM = "medium"      # 0.5 - 0.8
    LOW = "low"            # < 0.5


class Intent(BaseModel):
    """意图"""
    type: IntentType = Field(..., description="意图类型")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    
    # 提取的实体
    entities: dict[str, Any] = Field(default_factory=dict, description="实体")
    
    # 元数据
    source: str = Field("unknown", description="识别来源")
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    @property
    def confidence_level(self) -> IntentConfidence:
        if self.confidence > 0.8:
            return IntentConfidence.HIGH
        elif self.confidence > 0.5:
            return IntentConfidence.MEDIUM
        else:
            return IntentConfidence.LOW


class IntentResult(BaseModel):
    """意图识别结果"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="结果ID")
    
    # 主意图
    primary_intent: Intent = Field(..., description="主要意图")
    
    # 候选意图
    candidates: list[Intent] = Field(default_factory=list, description="候选意图")
    
    # 原始输入
    input_text: str = Field(..., description="原始输入")
    
    # 处理信息
    processing_time_ms: Optional[float] = Field(None, description="处理耗时")
    used_method: str = Field("unknown", description="使用的识别方法")
    
    # 缓存
    cached: bool = Field(False, description="是否来自缓存")
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def intent_type(self) -> IntentType:
        return IntentType(self.primary_intent.type)
    
    @property
    def confidence(self) -> float:
        return self.primary_intent.confidence
    
    @property
    def is_confident(self) -> bool:
        return self.confidence > 0.7
    
    def get_entity(self, name: str, default: Any = None) -> Any:
        """获取实体"""
        return self.primary_intent.entities.get(name, default)


class IntentExample(BaseModel):
    """意图示例（用于少样本学习）"""
    text: str = Field(..., description="示例文本")
    intent_type: IntentType = Field(..., description="意图类型")
    entities: dict[str, Any] = Field(default_factory=dict, description="实体")
    
    class Config:
        use_enum_values = True


class IntentRule(BaseModel):
    """意图规则（静态匹配）"""
    name: str = Field(..., description="规则名称")
    intent_type: IntentType = Field(..., description="意图类型")
    
    # 匹配条件
    keywords: list[str] = Field(default_factory=list, description="关键词")
    patterns: list[str] = Field(default_factory=list, description="正则模式")
    prefixes: list[str] = Field(default_factory=list, description="前缀")
    
    # 优先级
    priority: int = Field(0, description="优先级（越大越高）")
    
    # 条件
    min_length: int = Field(0, description="最小长度")
    max_length: int = Field(1000, description="最大长度")
    
    class Config:
        use_enum_values = True


class AgentRoute(BaseModel):
    """Agent 路由配置"""
    intent_type: IntentType = Field(..., description="意图类型")
    agent_id: str = Field(..., description="目标 Agent ID")
    
    # 条件
    min_confidence: float = Field(0.5, description="最小置信度")
    required_entities: list[str] = Field(default_factory=list, description="必需实体")
    
    # 元数据
    description: str = Field("", description="描述")
    enabled: bool = Field(True, description="是否启用")
    
    class Config:
        use_enum_values = True


class IntentConfig(BaseModel):
    """意图识别配置"""
    # 方法启用
    enable_rules: bool = Field(True, description="启用规则匹配")
    enable_embedding: bool = Field(True, description="启用 Embedding 匹配")
    enable_llm: bool = Field(True, description="启用 LLM 分类")
    
    # 阈值
    rule_confidence: float = Field(0.95, description="规则匹配置信度")
    embedding_threshold: float = Field(0.85, description="Embedding 相似度阈值")
    llm_min_confidence: float = Field(0.6, description="LLM 最小置信度")
    
    # 缓存
    enable_cache: bool = Field(True, description="启用缓存")
    cache_ttl: int = Field(3600, description="缓存 TTL（秒）")
    
    # 性能
    max_candidates: int = Field(5, description="最大候选数")
    timeout: float = Field(5.0, description="超时时间（秒）")


# 预定义的意图示例
DEFAULT_INTENT_EXAMPLES = [
    # 搜索
    IntentExample(text="搜索一下最新的AI新闻", intent_type=IntentType.SEARCH, entities={"query": "最新的AI新闻"}),
    IntentExample(text="帮我查一下天气", intent_type=IntentType.SEARCH, entities={"query": "天气"}),
    IntentExample(text="找一些关于Python的教程", intent_type=IntentType.SEARCH, entities={"query": "Python教程"}),
    
    # 代码
    IntentExample(text="写一个Python函数", intent_type=IntentType.CODE, entities={"language": "python"}),
    IntentExample(text="帮我调试这段代码", intent_type=IntentType.CODE, entities={"action": "debug"}),
    IntentExample(text="解释一下这个算法", intent_type=IntentType.CODE, entities={"action": "explain"}),
    
    # 文件
    IntentExample(text="读取config.json文件", intent_type=IntentType.FILE, entities={"filename": "config.json", "action": "read"}),
    IntentExample(text="创建一个新文件", intent_type=IntentType.FILE, entities={"action": "create"}),
    
    # 总结
    IntentExample(text="总结一下这篇文章", intent_type=IntentType.SUMMARY, entities={}),
    IntentExample(text="概括要点", intent_type=IntentType.SUMMARY, entities={}),
    
    # 翻译
    IntentExample(text="把这段话翻译成英文", intent_type=IntentType.TRANSLATE, entities={"target_lang": "english"}),
    IntentExample(text="translate to Chinese", intent_type=IntentType.TRANSLATE, entities={"target_lang": "chinese"}),
    
    # 问候
    IntentExample(text="你好", intent_type=IntentType.GREETING, entities={}),
    IntentExample(text="Hi", intent_type=IntentType.GREETING, entities={}),
    
    # 帮助
    IntentExample(text="你能做什么", intent_type=IntentType.HELP, entities={}),
    IntentExample(text="帮助", intent_type=IntentType.HELP, entities={}),
    
    # 取消
    IntentExample(text="取消", intent_type=IntentType.CANCEL, entities={}),
    IntentExample(text="停止", intent_type=IntentType.CANCEL, entities={}),
]


# 预定义的意图规则
DEFAULT_INTENT_RULES = [
    # 问候
    IntentRule(
        name="greeting",
        intent_type=IntentType.GREETING,
        keywords=["你好", "您好", "hi", "hello", "hey", "早上好", "晚上好"],
        priority=10,
        max_length=20,
    ),
    # 告别
    IntentRule(
        name="farewell",
        intent_type=IntentType.FAREWELL,
        keywords=["再见", "拜拜", "bye", "goodbye", "晚安"],
        priority=10,
        max_length=20,
    ),
    # 取消
    IntentRule(
        name="cancel",
        intent_type=IntentType.CANCEL,
        keywords=["取消", "停止", "cancel", "stop", "算了"],
        priority=20,
        max_length=20,
    ),
    # 帮助
    IntentRule(
        name="help",
        intent_type=IntentType.HELP,
        keywords=["帮助", "help", "你能做什么", "功能"],
        prefixes=["怎么", "如何"],
        priority=5,
    ),
    # 搜索
    IntentRule(
        name="search",
        intent_type=IntentType.SEARCH,
        prefixes=["搜索", "搜一下", "查一下", "找一下", "search"],
        priority=8,
    ),
    # 翻译
    IntentRule(
        name="translate",
        intent_type=IntentType.TRANSLATE,
        keywords=["翻译", "translate"],
        prefixes=["翻译成", "译成"],
        priority=8,
    ),
]
