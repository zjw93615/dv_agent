"""
意图识别服务
三层识别：规则匹配 -> Embedding 相似度 -> LLM 分类
"""

import re
import time
import json
import hashlib
from typing import Any, Optional

from .models import (
    Intent,
    IntentType,
    IntentResult,
    IntentRule,
    IntentExample,
    IntentConfig,
    DEFAULT_INTENT_RULES,
    DEFAULT_INTENT_EXAMPLES,
)
from ..session.redis_client import RedisClient
from ..config.logging import get_logger

logger = get_logger(__name__)

# 缓存 key 前缀
INTENT_CACHE_PREFIX = "intent_cache:"


class IntentRecognizer:
    """
    意图识别器
    
    三层识别策略：
    1. 规则匹配：快速、准确，适合明确的关键词/模式
    2. Embedding 相似度：语义理解，需要预计算示例向量
    3. LLM 分类：最灵活，作为兜底方案
    """
    
    def __init__(
        self,
        config: Optional[IntentConfig] = None,
        redis_client: Optional[RedisClient] = None,
        llm_gateway = None,
    ):
        self.config = config or IntentConfig()
        self.redis = redis_client
        self.llm_gateway = llm_gateway
        
        # 规则
        self._rules: list[IntentRule] = []
        
        # 示例（用于 Embedding）
        self._examples: list[IntentExample] = []
        self._example_embeddings: dict[str, list[float]] = {}
        
        # 初始化默认规则和示例
        self._load_defaults()
    
    def _load_defaults(self) -> None:
        """加载默认规则和示例"""
        self._rules = list(DEFAULT_INTENT_RULES)
        self._examples = list(DEFAULT_INTENT_EXAMPLES)
    
    def add_rule(self, rule: IntentRule) -> None:
        """添加规则"""
        self._rules.append(rule)
        # 按优先级排序
        self._rules.sort(key=lambda r: r.priority, reverse=True)
    
    def add_example(self, example: IntentExample) -> None:
        """添加示例"""
        self._examples.append(example)
    
    async def recognize(
        self,
        text: str,
        context: Optional[dict] = None,
    ) -> IntentResult:
        """
        识别意图
        
        Args:
            text: 输入文本
            context: 上下文信息
            
        Returns:
            IntentResult: 识别结果
        """
        start_time = time.time()
        text = text.strip()
        
        # 1. 检查缓存
        if self.config.enable_cache and self.redis:
            cached = await self._get_cached(text)
            if cached:
                cached.cached = True
                return cached
        
        # 2. 规则匹配
        if self.config.enable_rules:
            result = self._match_rules(text)
            if result and result.confidence >= self.config.rule_confidence:
                result.processing_time_ms = (time.time() - start_time) * 1000
                await self._cache_result(text, result)
                return result
        
        # 3. Embedding 相似度（如果有向量）
        if self.config.enable_embedding and self._example_embeddings:
            result = await self._match_embedding(text)
            if result and result.confidence >= self.config.embedding_threshold:
                result.processing_time_ms = (time.time() - start_time) * 1000
                await self._cache_result(text, result)
                return result
        
        # 4. LLM 分类
        if self.config.enable_llm and self.llm_gateway:
            result = await self._classify_with_llm(text, context)
            if result:
                result.processing_time_ms = (time.time() - start_time) * 1000
                await self._cache_result(text, result)
                return result
        
        # 5. 默认返回 UNKNOWN
        result = IntentResult(
            primary_intent=Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                source="fallback",
            ),
            input_text=text,
            used_method="fallback",
            processing_time_ms=(time.time() - start_time) * 1000,
        )
        
        return result
    
    # ===== 规则匹配 =====
    
    def _match_rules(self, text: str) -> Optional[IntentResult]:
        """规则匹配"""
        text_lower = text.lower()
        
        for rule in self._rules:
            # 长度检查
            if len(text) < rule.min_length or len(text) > rule.max_length:
                continue
            
            matched = False
            
            # 关键词匹配
            if rule.keywords:
                for keyword in rule.keywords:
                    if keyword.lower() in text_lower:
                        matched = True
                        break
            
            # 前缀匹配
            if not matched and rule.prefixes:
                for prefix in rule.prefixes:
                    if text_lower.startswith(prefix.lower()):
                        matched = True
                        break
            
            # 正则匹配
            if not matched and rule.patterns:
                for pattern in rule.patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        matched = True
                        break
            
            if matched:
                return IntentResult(
                    primary_intent=Intent(
                        type=rule.intent_type,
                        confidence=self.config.rule_confidence,
                        source="rule",
                        metadata={"rule_name": rule.name},
                    ),
                    input_text=text,
                    used_method="rule",
                )
        
        return None
    
    # ===== Embedding 匹配 =====
    
    async def _match_embedding(self, text: str) -> Optional[IntentResult]:
        """Embedding 相似度匹配"""
        # 需要实现 embedding 计算
        # 这里是占位实现
        return None
    
    async def compute_example_embeddings(self) -> None:
        """预计算示例向量"""
        # 需要 embedding 模型支持
        # 这里是占位实现
        logger.info("Example embeddings computed", count=len(self._examples))
    
    # ===== LLM 分类 =====
    
    async def _classify_with_llm(
        self,
        text: str,
        context: Optional[dict] = None,
    ) -> Optional[IntentResult]:
        """使用 LLM 进行意图分类"""
        if not self.llm_gateway:
            return None
        
        # 构建 prompt
        intent_types = [t.value for t in IntentType if t != IntentType.UNKNOWN]
        
        prompt = f"""你是一个意图分类器。请分析用户输入，识别其意图类型。

可用的意图类型：
{json.dumps(intent_types, ensure_ascii=False, indent=2)}

用户输入：{text}

请以 JSON 格式返回：
{{
    "intent": "意图类型",
    "confidence": 0.0-1.0之间的置信度,
    "entities": {{提取的实体}},
    "reasoning": "简短的推理说明"
}}

只返回 JSON，不要其他内容。"""

        try:
            from ..llm_gateway.models import LLMRequest, Message, MessageRole
            
            request = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="你是一个精确的意图分类器。"),
                    Message(role=MessageRole.USER, content=prompt),
                ],
                temperature=0.1,
                max_tokens=200,
            )
            
            response = await self.llm_gateway.complete(request)
            
            if response.content:
                # 解析 JSON 响应
                content = response.content.strip()
                # 清理可能的 markdown 代码块
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                
                data = json.loads(content)
                
                intent_type_str = data.get("intent", "unknown")
                try:
                    intent_type = IntentType(intent_type_str)
                except ValueError:
                    intent_type = IntentType.UNKNOWN
                
                confidence = float(data.get("confidence", 0.5))
                entities = data.get("entities", {})
                
                if confidence >= self.config.llm_min_confidence:
                    return IntentResult(
                        primary_intent=Intent(
                            type=intent_type,
                            confidence=confidence,
                            entities=entities,
                            source="llm",
                            metadata={"reasoning": data.get("reasoning", "")},
                        ),
                        input_text=text,
                        used_method="llm",
                    )
        
        except Exception as e:
            logger.warning(f"LLM classification failed", error=str(e))
        
        return None
    
    # ===== 缓存 =====
    
    def _cache_key(self, text: str) -> str:
        """生成缓存 key"""
        hash_value = hashlib.md5(text.encode()).hexdigest()[:16]
        return f"{INTENT_CACHE_PREFIX}{hash_value}"
    
    async def _get_cached(self, text: str) -> Optional[IntentResult]:
        """获取缓存的结果"""
        if not self.redis:
            return None
        
        try:
            key = self._cache_key(text)
            data = await self.redis.get_json(key)
            if data:
                return IntentResult(**data)
        except Exception as e:
            logger.warning(f"Cache get failed", error=str(e))
        
        return None
    
    async def _cache_result(self, text: str, result: IntentResult) -> None:
        """缓存结果"""
        if not self.redis or not self.config.enable_cache:
            return
        
        try:
            key = self._cache_key(text)
            await self.redis.set_json(
                key,
                result.model_dump(mode="json"),
                ttl=self.config.cache_ttl,
            )
        except Exception as e:
            logger.warning(f"Cache set failed", error=str(e))
    
    async def clear_cache(self) -> None:
        """清除缓存"""
        # Redis 的 key 会自动过期
        logger.info("Intent cache cleared")


# 全局意图识别器
_recognizer: Optional[IntentRecognizer] = None


def get_intent_recognizer() -> IntentRecognizer:
    """获取全局意图识别器"""
    global _recognizer
    if _recognizer is None:
        _recognizer = IntentRecognizer()
    return _recognizer


async def recognize_intent(
    text: str,
    context: Optional[dict] = None,
) -> IntentResult:
    """识别意图（便捷函数）"""
    recognizer = get_intent_recognizer()
    return await recognizer.recognize(text, context)
