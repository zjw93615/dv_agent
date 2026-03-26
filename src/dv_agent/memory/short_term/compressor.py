"""
Token Compressor
LLM 驱动的对话摘要生成器

使用 LLM 将超出窗口的历史消息压缩为摘要
"""

import json
import logging
from typing import Any, Optional, Protocol

from ..models import ShortTermMessage, WindowConfig

logger = logging.getLogger(__name__)


# 摘要生成 Prompt 模板
SUMMARY_PROMPT_TEMPLATE = """You are a conversation summarizer. Your task is to create a concise summary of the conversation history.

Focus on:
1. Key facts and information mentioned
2. User preferences and requirements
3. Important decisions or conclusions
4. Context that would be needed to continue the conversation

Keep the summary:
- Concise but comprehensive
- In the same language as the conversation
- Focused on information that would be useful for future turns

{existing_summary_section}

Conversation to summarize:
{messages}

Generate a summary in {max_tokens} tokens or less:"""


class LLMClient(Protocol):
    """LLM 客户端协议"""
    
    async def generate(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """生成响应"""
        ...


class TokenCompressor:
    """
    Token 压缩器
    
    使用 LLM 将历史消息压缩为摘要，减少 token 占用
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        config: Optional[WindowConfig] = None,
    ):
        """
        初始化压缩器
        
        Args:
            llm_client: LLM 客户端（需实现 generate 方法）
            config: 窗口配置
        """
        self.llm = llm_client
        self.config = config or WindowConfig()
    
    async def compress(
        self,
        messages: list[ShortTermMessage],
        existing_summary: Optional[str] = None,
    ) -> str:
        """
        压缩消息为摘要
        
        Args:
            messages: 待压缩的消息列表
            existing_summary: 现有摘要（增量压缩时使用）
            
        Returns:
            生成的摘要文本
        """
        if not messages:
            return existing_summary or ""
        
        # 构建消息文本
        messages_text = self._format_messages(messages)
        
        # 构建现有摘要部分
        existing_summary_section = ""
        if existing_summary:
            existing_summary_section = f"""
Previous summary (incorporate and update this):
{existing_summary}
"""
        
        # 构建 prompt
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            existing_summary_section=existing_summary_section,
            messages=messages_text,
            max_tokens=self.config.max_summary_tokens,
        )
        
        # 调用 LLM
        try:
            summary = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.compress_model,
                max_tokens=self.config.max_summary_tokens,
                temperature=0.3,  # 低温度保持一致性
            )
            
            logger.info(
                f"Compressed {len(messages)} messages to summary "
                f"({len(summary)} chars)"
            )
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Failed to compress messages: {e}")
            # 降级：返回简单的消息摘要
            return self._fallback_summary(messages, existing_summary)
    
    def _format_messages(self, messages: list[ShortTermMessage]) -> str:
        """
        格式化消息为文本
        
        Args:
            messages: 消息列表
            
        Returns:
            格式化的文本
        """
        lines = []
        for msg in messages:
            role = msg.role.upper()
            content = msg.content
            
            # 截断过长的内容
            if len(content) > 500:
                content = content[:500] + "..."
            
            lines.append(f"[{role}]: {content}")
        
        return "\n".join(lines)
    
    def _fallback_summary(
        self,
        messages: list[ShortTermMessage],
        existing_summary: Optional[str],
    ) -> str:
        """
        降级摘要生成（不使用 LLM）
        
        Args:
            messages: 消息列表
            existing_summary: 现有摘要
            
        Returns:
            简单的摘要文本
        """
        parts = []
        
        if existing_summary:
            parts.append(f"Previous context: {existing_summary}")
        
        # 提取用户消息作为关键点
        user_messages = [m for m in messages if m.role == "user"]
        if user_messages:
            topics = [m.content[:100] for m in user_messages[:3]]
            parts.append(f"Recent topics: {'; '.join(topics)}")
        
        return " | ".join(parts) if parts else ""
    
    async def incremental_compress(
        self,
        new_messages: list[ShortTermMessage],
        existing_summary: str,
        summary_tokens: int,
    ) -> str:
        """
        增量压缩：将新消息合并到现有摘要
        
        当摘要本身也接近 token 限制时使用
        
        Args:
            new_messages: 新消息
            existing_summary: 现有摘要
            summary_tokens: 现有摘要的 token 数
            
        Returns:
            更新后的摘要
        """
        # 如果摘要已经很长，需要先精简
        if summary_tokens > self.config.max_summary_tokens * 0.8:
            # 请求更精简的摘要
            condensed_config = WindowConfig(
                **self.config.model_dump(),
                max_summary_tokens=self.config.max_summary_tokens // 2,
            )
            temp_compressor = TokenCompressor(self.llm, condensed_config)
            existing_summary = await temp_compressor._condense_summary(
                existing_summary
            )
        
        return await self.compress(new_messages, existing_summary)
    
    async def _condense_summary(self, summary: str) -> str:
        """
        精简已有摘要
        
        Args:
            summary: 现有摘要
            
        Returns:
            精简后的摘要
        """
        prompt = f"""Condense the following conversation summary to half its length while keeping the most important information:

{summary}

Condensed summary:"""
        
        try:
            condensed = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.compress_model,
                max_tokens=self.config.max_summary_tokens // 2,
                temperature=0.3,
            )
            return condensed.strip()
        except Exception as e:
            logger.error(f"Failed to condense summary: {e}")
            # 降级：截断
            return summary[:len(summary) // 2] + "..."


class MockLLMClient:
    """
    模拟 LLM 客户端（用于测试）
    """
    
    async def generate(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """返回模拟摘要"""
        return "[Test Summary] This is a mock summary for testing purposes."
