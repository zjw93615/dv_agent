"""TokenCounter - Token 计数器

职责：
- 本地预估 Token 数（使用 tiktoken，无需 API 调用）
- 缓存机制（避免重复计算）
- 增量计算（只计算新增消息）
- 降级方案（tiktoken 不可用时使用字符估算）

参考: HelloAgents/context/token_counter.py
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..session.models import ConversationMessage

logger = logging.getLogger(__name__)

# 尝试导入 tiktoken
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed, falling back to character-based estimation")


class TokenCounter:
    """Token 计数器
    
    特性：
    - 本地精确计算（使用 tiktoken）
    - 缓存机制（避免重复计算）
    - 增量计算支持
    - 降级方案（tiktoken 不可用时使用字符估算）
    
    用法示例：
    ```python
    counter = TokenCounter(model="gpt-4")
    
    # 计算单条消息
    tokens = counter.count_message(message)
    
    # 计算消息列表
    total = counter.count_messages(messages)
    
    # 计算文本
    tokens = counter.count_text("Hello, world!")
    
    # 获取缓存统计
    stats = counter.get_cache_stats()
    ```
    """
    
    # 角色标记开销（OpenAI 格式约 4 tokens）
    ROLE_OVERHEAD = 4
    
    # 字符到 Token 的粗略比例（降级用）
    # 英文约 4 字符/token，中文约 2 字符/token，取折中值
    CHAR_PER_TOKEN_FALLBACK = 3
    
    def __init__(self, model: str = "gpt-4"):
        """初始化 Token 计数器
        
        Args:
            model: 模型名称（用于选择 tiktoken 编码器）
        """
        self.model = model
        self._encoding = self._get_encoding()
        self._cache: Dict[str, int] = {}  # 内容哈希 -> Token 数
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _get_encoding(self):
        """获取 tiktoken 编码器
        
        Returns:
            tiktoken 编码器实例，失败时返回 None
        """
        if not TIKTOKEN_AVAILABLE:
            return None
            
        try:
            # 尝试根据模型名称获取编码器
            return tiktoken.encoding_for_model(self.model)
        except KeyError:
            # 降级到通用编码器 cl100k_base（GPT-4/3.5-turbo 使用）
            try:
                logger.debug(f"Model {self.model} not found, using cl100k_base encoding")
                return tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"Failed to get tiktoken encoding: {e}")
                return None
        except Exception as e:
            logger.warning(f"tiktoken initialization failed: {e}")
            return None
    
    def count_text(self, text: str, use_cache: bool = True) -> int:
        """计算文本的 Token 数
        
        Args:
            text: 文本内容
            use_cache: 是否使用缓存
        
        Returns:
            Token 数
        """
        if not text:
            return 0
        
        # 检查缓存
        if use_cache:
            cache_key = hash(text)
            if cache_key in self._cache:
                self._cache_hits += 1
                return self._cache[cache_key]
            self._cache_misses += 1
        
        # 计算 Token 数
        tokens = self._count_text_impl(text)
        
        # 缓存结果
        if use_cache:
            self._cache[hash(text)] = tokens
        
        return tokens
    
    def _count_text_impl(self, text: str) -> int:
        """内部 Token 计算实现
        
        Args:
            text: 文本内容
        
        Returns:
            Token 数
        """
        if self._encoding:
            # 使用 tiktoken 精确计算
            try:
                return len(self._encoding.encode(text))
            except Exception as e:
                logger.debug(f"tiktoken encoding failed: {e}, falling back to estimation")
                return self._estimate_tokens(text)
        else:
            # 降级方案：字符估算
            return self._estimate_tokens(text)
    
    def _estimate_tokens(self, text: str) -> int:
        """字符估算 Token 数（降级方案）
        
        Args:
            text: 文本内容
        
        Returns:
            估算的 Token 数
        """
        # 简单启发式：中文字符权重更高
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # 中文约 1.5 字符/token，英文约 4 字符/token
        estimated = chinese_chars / 1.5 + other_chars / 4
        return max(1, int(estimated))
    
    def count_message(self, message: "ConversationMessage") -> int:
        """计算单条消息的 Token 数
        
        Args:
            message: ConversationMessage 对象
        
        Returns:
            Token 数（包含角色开销）
        """
        content_tokens = self.count_text(message.content)
        return content_tokens + self.ROLE_OVERHEAD
    
    def count_messages(self, messages: List["ConversationMessage"]) -> int:
        """计算消息列表的总 Token 数
        
        Args:
            messages: 消息列表
        
        Returns:
            总 Token 数
        """
        total = 0
        for msg in messages:
            total += self.count_message(msg)
        return total
    
    def count_messages_with_detail(
        self, 
        messages: List["ConversationMessage"]
    ) -> Dict[str, int]:
        """计算消息列表的 Token 数（详细版）
        
        Args:
            messages: 消息列表
        
        Returns:
            包含详细信息的字典
        """
        total = 0
        by_role = {"user": 0, "assistant": 0, "system": 0, "other": 0}
        
        for msg in messages:
            tokens = self.count_message(msg)
            total += tokens
            
            role = msg.type.value if hasattr(msg.type, 'value') else str(msg.type)
            if role in by_role:
                by_role[role] += tokens
            else:
                by_role["other"] += tokens
        
        return {
            "total": total,
            "by_role": by_role,
            "message_count": len(messages),
            "avg_per_message": total // len(messages) if messages else 0,
        }
    
    def estimate_remaining(self, current_tokens: int, max_tokens: int) -> int:
        """估算剩余可用 Token 数
        
        Args:
            current_tokens: 当前已用 Token 数
            max_tokens: 最大 Token 数
        
        Returns:
            剩余可用 Token 数
        """
        return max(0, max_tokens - current_tokens)
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.debug("Token cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0
        
        return {
            "cached_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 3),
            "total_cached_tokens": sum(self._cache.values()),
        }
    
    @property
    def is_precise(self) -> bool:
        """是否使用精确计算（tiktoken）"""
        return self._encoding is not None


# 全局单例（可选使用）
_default_counter: Optional[TokenCounter] = None


def get_token_counter(model: str = "gpt-4") -> TokenCounter:
    """获取全局 Token 计数器（单例模式）
    
    Args:
        model: 模型名称
    
    Returns:
        TokenCounter 实例
    """
    global _default_counter
    if _default_counter is None or _default_counter.model != model:
        _default_counter = TokenCounter(model=model)
    return _default_counter


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """便捷函数：计算文本 Token 数
    
    Args:
        text: 文本内容
        model: 模型名称
    
    Returns:
        Token 数
    """
    return get_token_counter(model).count_text(text)
