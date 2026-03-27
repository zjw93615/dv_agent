"""HistoryManager - 历史消息管理器

职责：
- 消息追加（只追加，不编辑，缓存友好）
- 历史压缩（生成 summary + 保留最近轮次）
- 轮次边界检测
- Token 预算管理

参考: HelloAgents/context/history.py
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .token_counter import TokenCounter, get_token_counter

if TYPE_CHECKING:
    from ..session.models import ConversationMessage, MessageType

logger = logging.getLogger(__name__)


class HistoryManager:
    """历史管理器
    
    特性：
    - 只追加，不编辑（缓存友好）
    - 自动压缩历史（summary + 保留最近轮次）
    - 轮次边界检测
    - Token 预算管理
    
    用法示例：
    ```python
    manager = HistoryManager(
        min_retain_rounds=5,
        max_tokens=4000
    )
    
    # 添加消息
    manager.add_message(user_message)
    manager.add_message(assistant_message)
    
    # 获取用于 LLM 的消息（自动压缩）
    messages = await manager.get_context_messages(
        summarize_fn=my_summarize_function
    )
    
    # 手动压缩
    await manager.compress_if_needed(summarize_fn)
    ```
    """
    
    def __init__(
        self,
        messages: Optional[List["ConversationMessage"]] = None,
        min_retain_rounds: int = 5,
        max_tokens: int = 4000,
        compression_threshold: float = 0.8,
        token_counter: Optional[TokenCounter] = None,
    ):
        """初始化历史管理器
        
        Args:
            messages: 初始消息列表
            min_retain_rounds: 压缩时保留的最小完整轮次数
            max_tokens: 历史消息的最大 Token 预算
            compression_threshold: 压缩触发阈值（已用/最大）
            token_counter: Token 计数器（可选，默认使用全局单例）
        """
        self._messages: List["ConversationMessage"] = list(messages) if messages else []
        self._summary: Optional[str] = None  # 压缩后的历史摘要
        
        self.min_retain_rounds = min_retain_rounds
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self._counter = token_counter or get_token_counter()
        
        # 统计
        self._compression_count = 0
        self._total_compressed_messages = 0
    
    @property
    def messages(self) -> List["ConversationMessage"]:
        """获取消息列表（只读副本）"""
        return self._messages.copy()
    
    @property
    def summary(self) -> Optional[str]:
        """获取历史摘要"""
        return self._summary
    
    @property
    def message_count(self) -> int:
        """消息数量"""
        return len(self._messages)
    
    def add_message(self, message: "ConversationMessage") -> None:
        """追加消息（只追加，不编辑）
        
        Args:
            message: 要追加的消息
        """
        self._messages.append(message)
    
    def clear(self) -> None:
        """清空历史"""
        self._messages.clear()
        self._summary = None
    
    def estimate_rounds(self) -> int:
        """预估完整轮次数
        
        一轮定义：1 user 消息 + N 条 assistant/tool 消息
        
        Returns:
            完整轮次数
        """
        from ..session.models import MessageType
        
        rounds = 0
        i = 0
        while i < len(self._messages):
            if self._messages[i].type == MessageType.USER:
                rounds += 1
                # 跳过这一轮的后续消息
                i += 1
                while i < len(self._messages) and self._messages[i].type != MessageType.USER:
                    i += 1
            else:
                i += 1
        return rounds
    
    def find_round_boundaries(self) -> List[int]:
        """查找每轮的起始索引
        
        Returns:
            每轮起始索引列表，例如 [0, 3, 7, 10]
        """
        from ..session.models import MessageType
        
        boundaries = []
        for i, msg in enumerate(self._messages):
            if msg.type == MessageType.USER:
                boundaries.append(i)
        return boundaries
    
    def get_current_tokens(self) -> int:
        """获取当前消息的总 Token 数"""
        total = 0
        for msg in self._messages:
            total += self._counter.count_message(msg)
        if self._summary:
            total += self._counter.count_text(self._summary)
        return total
    
    def needs_compression(self) -> bool:
        """检查是否需要压缩
        
        Returns:
            True 如果已用 Token 超过阈值
        """
        current = self.get_current_tokens()
        threshold = int(self.max_tokens * self.compression_threshold)
        return current > threshold
    
    async def compress_if_needed(
        self,
        summarize_fn: Optional[Callable[[List["ConversationMessage"]], str]] = None,
    ) -> bool:
        """如果需要则压缩历史
        
        Args:
            summarize_fn: 摘要生成函数，接收消息列表返回摘要文本
                         如果为 None，使用简单的消息拼接
        
        Returns:
            True 如果执行了压缩
        """
        if not self.needs_compression():
            return False
        
        rounds = self.estimate_rounds()
        if rounds <= self.min_retain_rounds:
            logger.debug(f"Not enough rounds to compress: {rounds} <= {self.min_retain_rounds}")
            return False
        
        # 找到所有轮次边界
        boundaries = self.find_round_boundaries()
        
        # 计算要保留的起始位置（保留最近 min_retain_rounds 轮）
        if len(boundaries) <= self.min_retain_rounds:
            return False
        
        keep_from_index = boundaries[-self.min_retain_rounds]
        messages_to_compress = self._messages[:keep_from_index]
        messages_to_keep = self._messages[keep_from_index:]
        
        if not messages_to_compress:
            return False
        
        # 生成摘要
        if summarize_fn:
            try:
                new_summary = await summarize_fn(messages_to_compress)
            except Exception as e:
                logger.error(f"Summarization failed: {e}")
                new_summary = self._simple_summarize(messages_to_compress)
        else:
            new_summary = self._simple_summarize(messages_to_compress)
        
        # 合并旧摘要
        if self._summary:
            self._summary = f"{self._summary}\n\n---\n\n{new_summary}"
        else:
            self._summary = new_summary
        
        # 更新消息列表
        compressed_count = len(messages_to_compress)
        self._messages = messages_to_keep
        
        # 更新统计
        self._compression_count += 1
        self._total_compressed_messages += compressed_count
        
        logger.info(
            f"History compressed: {compressed_count} messages → summary, "
            f"kept {len(messages_to_keep)} messages ({self.estimate_rounds()} rounds)"
        )
        
        return True
    
    def _simple_summarize(self, messages: List["ConversationMessage"]) -> str:
        """简单摘要（降级方案）
        
        将消息转换为简洁的文本摘要
        """
        from ..session.models import MessageType
        
        lines = ["## 历史对话摘要"]
        
        for msg in messages:
            role = "用户" if msg.type == MessageType.USER else "助手"
            # 截取前 100 个字符
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            lines.append(f"- {role}: {content}")
        
        return "\n".join(lines)
    
    def get_context_messages(
        self,
        include_summary: bool = True,
    ) -> List["ConversationMessage"]:
        """获取用于 LLM 上下文的消息
        
        Args:
            include_summary: 是否包含历史摘要
        
        Returns:
            消息列表（如果有摘要，会作为第一条系统消息）
        """
        from ..session.models import ConversationMessage, MessageType
        
        result = []
        
        # 如果有摘要，作为第一条消息
        if include_summary and self._summary:
            summary_msg = ConversationMessage(
                type=MessageType.SYSTEM,
                content=self._summary,
                metadata={"is_summary": True},
            )
            result.append(summary_msg)
        
        # 添加保留的消息
        result.extend(self._messages)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "message_count": len(self._messages),
            "rounds": self.estimate_rounds(),
            "has_summary": self._summary is not None,
            "summary_tokens": self._counter.count_text(self._summary) if self._summary else 0,
            "current_tokens": self.get_current_tokens(),
            "max_tokens": self.max_tokens,
            "compression_count": self._compression_count,
            "total_compressed_messages": self._total_compressed_messages,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典
        
        Returns:
            包含历史和元数据的字典
        """
        return {
            "messages": [msg.model_dump() for msg in self._messages],
            "summary": self._summary,
            "stats": self.get_stats(),
            "created_at": datetime.now().isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryManager":
        """从字典反序列化
        
        Args:
            data: 序列化的历史数据
        
        Returns:
            HistoryManager 实例
        """
        from ..session.models import ConversationMessage
        
        messages = [
            ConversationMessage.model_validate(msg_data)
            for msg_data in data.get("messages", [])
        ]
        
        manager = cls(messages=messages)
        manager._summary = data.get("summary")
        
        return manager
