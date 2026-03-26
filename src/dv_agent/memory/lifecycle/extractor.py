"""
Memory Extractor
记忆提取器 - 从对话中提取长期记忆

使用 LLM 从对话内容中识别和提取值得长期保存的记忆，
包括用户偏好、事实信息、重要事件等。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from ..models import Memory, MemoryType

logger = logging.getLogger(__name__)


# 提取 Prompt 模板
EXTRACTION_PROMPT = """You are a memory extraction system. Analyze the following conversation and extract important information that should be remembered about the user for future interactions.

Focus on extracting:
1. **Facts** - Concrete information about the user (name, location, profession, etc.)
2. **Preferences** - User's likes, dislikes, preferences, habits
3. **Events** - Important events mentioned (birthdays, appointments, achievements)
4. **Relationships** - People mentioned and their relationship to the user

For each extracted memory:
- Be concise but complete
- Include relevant context
- Assign a confidence score (0.0-1.0) based on how certain the information is
- Assign an importance score (0.0-1.0) based on how useful this will be in future

**Conversation:**
{conversation}

**Output Format (JSON array):**
```json
[
  {
    "type": "fact|preference|event|relationship",
    "content": "The extracted memory content",
    "confidence": 0.9,
    "importance": 0.8,
    "tags": ["relevant", "tags"]
  }
]
```

If no significant memories to extract, return an empty array: []

**Important:**
- Only extract genuinely useful long-term information
- Avoid extracting trivial or temporary information
- Don't duplicate information already known
- Be accurate - don't infer beyond what's stated
"""


@dataclass
class ExtractionResult:
    """提取结果"""
    memories: list[Memory] = field(default_factory=list)
    raw_response: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    
    @property
    def count(self) -> int:
        return len(self.memories)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class MemoryExtractor:
    """
    记忆提取器
    
    使用 LLM 从对话中提取值得长期保存的信息。
    
    工作流程：
    1. 格式化对话内容
    2. 调用 LLM 进行提取
    3. 解析和验证结果
    4. 创建 Memory 对象
    """
    
    # 类型映射
    TYPE_MAPPING = {
        "fact": MemoryType.FACT,
        "preference": MemoryType.PREFERENCE,
        "event": MemoryType.EVENT,
        "relationship": MemoryType.RELATIONSHIP,
    }
    
    def __init__(
        self,
        llm_client,
        model: str = "gpt-4o-mini",
        max_tokens: int = 2048,
        temperature: float = 0.1,
        existing_memories: Optional[list[Memory]] = None,
    ):
        """
        初始化提取器
        
        Args:
            llm_client: LLM 客户端
            model: 使用的模型
            max_tokens: 最大输出 token 数
            temperature: 采样温度
            existing_memories: 已有记忆（用于去重）
        """
        self.llm = llm_client
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.existing_memories = existing_memories or []
    
    async def extract(
        self,
        conversation: list[dict[str, str]],
        user_id: str,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
    ) -> ExtractionResult:
        """
        从对话中提取记忆
        
        Args:
            conversation: 对话消息列表 [{"role": "user/assistant", "content": "..."}]
            user_id: 用户 ID
            session_id: 会话 ID
            turn_id: 轮次 ID
            
        Returns:
            提取结果
        """
        start_time = datetime.utcnow()
        result = ExtractionResult()
        
        try:
            # 格式化对话
            formatted = self._format_conversation(conversation)
            
            # 构建 prompt
            prompt = EXTRACTION_PROMPT.format(conversation=formatted)
            
            # 调用 LLM
            response = await self._call_llm(prompt)
            result.raw_response = response
            
            # 解析结果
            extracted = self._parse_response(response)
            
            # 验证并创建 Memory 对象
            for item in extracted:
                memory = self._create_memory(
                    item=item,
                    user_id=user_id,
                    session_id=session_id,
                    turn_id=turn_id,
                )
                if memory and not self._is_duplicate(memory):
                    result.memories.append(memory)
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}", exc_info=True)
            result.errors.append(str(e))
        
        result.latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.info(
            f"Extracted {result.count} memories from conversation "
            f"(errors={len(result.errors)}, latency={result.latency_ms:.1f}ms)"
        )
        
        return result
    
    def _format_conversation(self, conversation: list[dict[str, str]]) -> str:
        """
        格式化对话为字符串
        
        Args:
            conversation: 对话消息列表
            
        Returns:
            格式化后的字符串
        """
        lines = []
        for msg in conversation:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            lines.append(f"**{role}:** {content}")
        
        return "\n\n".join(lines)
    
    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM
        
        Args:
            prompt: 提示词
            
        Returns:
            LLM 响应
        """
        # 使用通用的 LLM 调用接口
        # 这里假设 llm_client 有 chat_completion 方法
        response = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        
        return response.get("content", "")
    
    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 原始响应
            
        Returns:
            解析后的记忆列表
        """
        # 尝试提取 JSON
        json_match = re.search(r'\[[\s\S]*\]', response)
        
        if not json_match:
            logger.warning("No JSON array found in response")
            return []
        
        try:
            data = json.loads(json_match.group())
            
            if not isinstance(data, list):
                logger.warning("Parsed data is not a list")
                return []
            
            return data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return []
    
    def _create_memory(
        self,
        item: dict[str, Any],
        user_id: str,
        session_id: Optional[str],
        turn_id: Optional[int],
    ) -> Optional[Memory]:
        """
        创建 Memory 对象
        
        Args:
            item: 提取的记忆项
            user_id: 用户 ID
            session_id: 会话 ID
            turn_id: 轮次 ID
            
        Returns:
            Memory 对象，验证失败返回 None
        """
        try:
            # 验证必需字段
            content = item.get("content", "").strip()
            if not content or len(content) < 5:
                return None
            
            # 解析类型
            type_str = item.get("type", "fact").lower()
            memory_type = self.TYPE_MAPPING.get(type_str, MemoryType.FACT)
            
            # 解析分数
            confidence = self._parse_score(item.get("confidence", 0.5))
            importance = self._parse_score(item.get("importance", 0.5))
            
            # 解析标签
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            
            # 创建 Memory
            now = datetime.utcnow()
            
            return Memory(
                id=uuid4(),
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                source_session=session_id,
                source_turn=turn_id,
                confidence=confidence,
                importance=importance,
                access_count=0,
                decay_rate=0.01,
                created_at=now,
                updated_at=now,
                last_accessed=now,
                metadata={"tags": tags, "extraction_version": "v1"},
            )
            
        except Exception as e:
            logger.warning(f"Failed to create memory from item: {e}")
            return None
    
    def _parse_score(self, value: Any) -> float:
        """
        解析分数值
        
        Args:
            value: 分数值
            
        Returns:
            标准化的分数 [0.0, 1.0]
        """
        try:
            score = float(value)
            return max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            return 0.5
    
    def _is_duplicate(self, memory: Memory) -> bool:
        """
        检查是否与已有记忆重复
        
        Args:
            memory: 待检查的记忆
            
        Returns:
            是否重复
        """
        if not self.existing_memories:
            return False
        
        # 简单的文本相似度检查
        new_content_lower = memory.content.lower()
        new_words = set(new_content_lower.split())
        
        for existing in self.existing_memories:
            existing_lower = existing.content.lower()
            
            # 完全匹配
            if new_content_lower == existing_lower:
                return True
            
            # Jaccard 相似度
            existing_words = set(existing_lower.split())
            intersection = len(new_words & existing_words)
            union = len(new_words | existing_words)
            
            if union > 0 and intersection / union > 0.8:
                return True
        
        return False
    
    async def extract_incremental(
        self,
        new_messages: list[dict[str, str]],
        user_id: str,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
        context_messages: Optional[list[dict[str, str]]] = None,
    ) -> ExtractionResult:
        """
        增量提取（只处理新消息，但提供上下文）
        
        Args:
            new_messages: 新增的消息
            user_id: 用户 ID
            session_id: 会话 ID
            turn_id: 轮次 ID
            context_messages: 上下文消息
            
        Returns:
            提取结果
        """
        # 合并上下文和新消息
        conversation = []
        
        if context_messages:
            # 只取最后几条上下文
            conversation.extend(context_messages[-4:])
        
        conversation.extend(new_messages)
        
        return await self.extract(
            conversation=conversation,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
        )
