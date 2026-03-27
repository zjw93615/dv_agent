"""工具输出截断器

处理工具调用返回的长文本输出，支持多种截断策略：
- head: 保留头部
- tail: 保留尾部
- head_tail: 保留头尾
- smart: 智能截断（保留关键信息）

Author: DV-Agent Team
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TruncateStrategy(str, Enum):
    """截断策略"""
    HEAD = "head"           # 保留头部
    TAIL = "tail"           # 保留尾部
    HEAD_TAIL = "head_tail" # 保留头尾
    SMART = "smart"         # 智能截断


@dataclass
class TruncateResult:
    """截断结果"""
    content: str              # 截断后的内容
    original_length: int      # 原始长度
    truncated_length: int     # 截断后长度
    was_truncated: bool       # 是否被截断
    saved_path: Optional[str] = None  # 完整内容保存路径
    
    @property
    def compression_ratio(self) -> float:
        """压缩比率"""
        if self.original_length == 0:
            return 1.0
        return self.truncated_length / self.original_length


class ObservationTruncator:
    """工具输出截断器
    
    用于处理工具调用返回的长文本，确保不会超出 LLM 上下文限制。
    
    Features:
    - 多种截断策略
    - 自动保存完整输出到文件
    - 添加截断标记
    - 统计信息
    
    Example:
        ```python
        truncator = ObservationTruncator(
            max_length=2000,
            strategy=TruncateStrategy.HEAD_TAIL,
        )
        
        result = truncator.truncate(
            tool_name="search",
            output=very_long_text,
        )
        
        if result.was_truncated:
            print(f"Truncated from {result.original_length} to {result.truncated_length}")
            print(f"Full output saved to: {result.saved_path}")
        ```
    """
    
    # 截断标记模板
    TRUNCATE_MARKER = "\n\n... [Truncated: {original_len} → {truncated_len} chars, full output saved to {path}] ...\n\n"
    TRUNCATE_MARKER_NO_SAVE = "\n\n... [Truncated: {original_len} → {truncated_len} chars] ...\n\n"
    
    def __init__(
        self,
        max_length: int = 4000,
        strategy: TruncateStrategy = TruncateStrategy.HEAD_TAIL,
        head_ratio: float = 0.6,
        save_full_output: bool = True,
        output_dir: Optional[str] = None,
    ):
        """
        Args:
            max_length: 最大输出长度（字符数）
            strategy: 截断策略
            head_ratio: HEAD_TAIL 模式下头部占比
            save_full_output: 是否保存完整输出
            output_dir: 完整输出保存目录
        """
        self._max_length = max_length
        self._strategy = strategy
        self._head_ratio = head_ratio
        self._save_full_output = save_full_output
        
        # 设置输出目录
        if output_dir:
            self._output_dir = Path(output_dir)
        else:
            self._output_dir = Path.cwd() / ".dv_agent" / "tool_outputs"
        
        # 确保目录存在
        if self._save_full_output:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        
        # 统计信息
        self._stats = {
            "total_calls": 0,
            "truncated_calls": 0,
            "total_chars_saved": 0,
        }
    
    def truncate(
        self,
        output: str,
        tool_name: str = "unknown",
        strategy: Optional[TruncateStrategy] = None,
    ) -> TruncateResult:
        """截断工具输出
        
        Args:
            output: 工具输出内容
            tool_name: 工具名称（用于生成文件名）
            strategy: 截断策略（覆盖默认策略）
            
        Returns:
            TruncateResult: 截断结果
        """
        self._stats["total_calls"] += 1
        original_length = len(output)
        
        # 不需要截断
        if original_length <= self._max_length:
            return TruncateResult(
                content=output,
                original_length=original_length,
                truncated_length=original_length,
                was_truncated=False,
            )
        
        # 需要截断
        self._stats["truncated_calls"] += 1
        self._stats["total_chars_saved"] += original_length - self._max_length
        
        strategy = strategy or self._strategy
        saved_path = None
        
        # 保存完整输出
        if self._save_full_output:
            saved_path = self._save_output(output, tool_name)
        
        # 执行截断
        truncated = self._do_truncate(output, strategy)
        
        # 添加截断标记
        if saved_path:
            marker = self.TRUNCATE_MARKER.format(
                original_len=original_length,
                truncated_len=len(truncated),
                path=saved_path,
            )
        else:
            marker = self.TRUNCATE_MARKER_NO_SAVE.format(
                original_len=original_length,
                truncated_len=len(truncated),
            )
        
        # 插入标记
        if strategy == TruncateStrategy.HEAD:
            content = truncated + marker
        elif strategy == TruncateStrategy.TAIL:
            content = marker + truncated
        else:  # HEAD_TAIL or SMART
            # 在中间插入标记
            mid_point = len(truncated) // 2
            # 找到最近的换行符
            newline_pos = truncated.rfind('\n', 0, mid_point)
            if newline_pos == -1:
                newline_pos = mid_point
            content = truncated[:newline_pos] + marker + truncated[newline_pos:]
        
        return TruncateResult(
            content=content,
            original_length=original_length,
            truncated_length=len(content),
            was_truncated=True,
            saved_path=saved_path,
        )
    
    def _do_truncate(
        self,
        text: str,
        strategy: TruncateStrategy,
    ) -> str:
        """执行截断"""
        # 预留空间给标记
        effective_max = self._max_length - 100
        
        if strategy == TruncateStrategy.HEAD:
            return text[:effective_max]
        
        elif strategy == TruncateStrategy.TAIL:
            return text[-effective_max:]
        
        elif strategy == TruncateStrategy.HEAD_TAIL:
            head_len = int(effective_max * self._head_ratio)
            tail_len = effective_max - head_len
            return text[:head_len] + text[-tail_len:]
        
        elif strategy == TruncateStrategy.SMART:
            return self._smart_truncate(text, effective_max)
        
        else:
            return text[:effective_max]
    
    def _smart_truncate(self, text: str, max_length: int) -> str:
        """智能截断
        
        策略：
        1. 保留第一行（通常是标题或命令）
        2. 保留最后几行（通常是结果或总结）
        3. 中间部分采样
        """
        lines = text.split('\n')
        
        if len(lines) <= 10:
            # 行数不多，直接用 HEAD_TAIL
            head_len = int(max_length * 0.6)
            tail_len = max_length - head_len
            return text[:head_len] + text[-tail_len:]
        
        # 分配策略
        # - 前 3 行
        # - 最后 5 行
        # - 中间采样
        head_lines = lines[:3]
        tail_lines = lines[-5:]
        
        head_text = '\n'.join(head_lines)
        tail_text = '\n'.join(tail_lines)
        
        remaining = max_length - len(head_text) - len(tail_text) - 20
        
        if remaining > 0:
            # 中间采样
            middle_lines = lines[3:-5]
            if middle_lines:
                # 均匀采样
                step = max(1, len(middle_lines) // 5)
                sampled = middle_lines[::step][:5]
                middle_text = '\n'.join(sampled)
                
                if len(middle_text) > remaining:
                    middle_text = middle_text[:remaining]
                
                return head_text + '\n...\n' + middle_text + '\n...\n' + tail_text
        
        return head_text + '\n...\n' + tail_text
    
    def _save_output(self, output: str, tool_name: str) -> str:
        """保存完整输出到文件"""
        try:
            # 生成文件名
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            content_hash = hashlib.md5(output.encode()).hexdigest()[:8]
            filename = f"{tool_name}_{timestamp}_{content_hash}.txt"
            
            filepath = self._output_dir / filename
            filepath.write_text(output, encoding="utf-8")
            
            logger.debug(f"Saved full output to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.warning(f"Failed to save output: {e}")
            return None
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            "truncation_rate": (
                self._stats["truncated_calls"] / self._stats["total_calls"]
                if self._stats["total_calls"] > 0 else 0
            ),
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_calls": 0,
            "truncated_calls": 0,
            "total_chars_saved": 0,
        }


# ===== 便捷函数 =====

_default_truncator: Optional[ObservationTruncator] = None


def get_truncator() -> ObservationTruncator:
    """获取默认截断器"""
    global _default_truncator
    if _default_truncator is None:
        _default_truncator = ObservationTruncator()
    return _default_truncator


def truncate_output(
    output: str,
    tool_name: str = "unknown",
    max_length: int = 4000,
) -> str:
    """快捷截断函数
    
    Args:
        output: 工具输出
        tool_name: 工具名称
        max_length: 最大长度
        
    Returns:
        截断后的内容
    """
    truncator = ObservationTruncator(max_length=max_length)
    result = truncator.truncate(output, tool_name)
    return result.content
