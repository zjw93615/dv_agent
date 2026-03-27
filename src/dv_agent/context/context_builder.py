"""上下文构建器 (GSSC 流水线)

实现 Gather-Select-Structure-Compress 四阶段上下文工程：
- Gather: 收集所有候选上下文片段
- Select: 基于相关性和新近性筛选与排序
- Structure: 按模板结构化组装
- Compress: 压缩规范化（截断、摘要）

Author: DV-Agent Team
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from .token_counter import TokenCounter, get_token_counter


class ContextType(str, Enum):
    """上下文片段类型"""
    SYSTEM_PROMPT = "system_prompt"      # 系统提示词
    TASK_INSTRUCTION = "task_instruction"  # 任务指令
    SUMMARY = "summary"                   # 历史摘要
    HISTORY = "history"                   # 历史消息
    RAG_RESULT = "rag_result"            # RAG 检索结果
    TOOL_OUTPUT = "tool_output"          # 工具输出
    ENTITY_MEMORY = "entity_memory"      # 实体记忆
    USER_CONTEXT = "user_context"        # 用户上下文
    CURRENT_STATE = "current_state"      # 当前状态


@dataclass
class ContextPacket:
    """上下文片段
    
    携带内容、类型、优先级和元数据的上下文单元
    """
    content: str                          # 片段内容
    type: ContextType                     # 片段类型
    priority: float = 0.5                 # 优先级 (0.0 - 1.0)
    relevance_score: float = 0.0          # 相关性分数
    recency_score: float = 0.0            # 新近性分数
    tokens: int = 0                       # Token 数量（延迟计算）
    timestamp: Optional[datetime] = None  # 时间戳
    metadata: dict = field(default_factory=dict)
    
    @property
    def composite_score(self) -> float:
        """复合评分: 0.7*相关性 + 0.3*新近性"""
        return 0.7 * self.relevance_score + 0.3 * self.recency_score


@dataclass
class StructuredContext:
    """结构化上下文结果"""
    messages: list[dict]                  # 格式化后的消息列表
    total_tokens: int                     # 总 Token 数
    packets_included: int                 # 包含的片段数
    packets_dropped: int                  # 丢弃的片段数
    metadata: dict = field(default_factory=dict)


class ContextBuilder:
    """上下文构建器
    
    GSSC (Gather-Select-Structure-Compress) 流水线:
    
    ```
    [历史消息] ──┐
    [RAG 结果] ──┼──► Gather ──► Select ──► Structure ──► Compress ──► [LLM 输入]
    [工具输出] ──┤        (收集)    (筛选)    (结构化)     (压缩)
    [实体记忆] ──┘
    ```
    
    Example:
        ```python
        builder = ContextBuilder(max_tokens=8000)
        
        # Gather 阶段
        builder.add_system_prompt("你是一个智能助手...")
        builder.add_history(history_messages)
        builder.add_rag_results(search_results)
        
        # Select + Structure + Compress
        context = builder.build(current_query="如何使用Python?")
        
        # 使用结果
        llm_request = LLMRequest(messages=context.messages)
        ```
    """
    
    # 类型优先级映射（用于强制排序）
    TYPE_PRIORITY = {
        ContextType.SYSTEM_PROMPT: 1.0,
        ContextType.TASK_INSTRUCTION: 0.95,
        ContextType.CURRENT_STATE: 0.9,
        ContextType.SUMMARY: 0.85,
        ContextType.ENTITY_MEMORY: 0.8,
        ContextType.RAG_RESULT: 0.7,
        ContextType.HISTORY: 0.6,
        ContextType.TOOL_OUTPUT: 0.5,
        ContextType.USER_CONTEXT: 0.4,
    }
    
    def __init__(
        self,
        max_tokens: int = 8000,
        model_name: str = "gpt-4",
        reserved_for_response: int = 1000,
    ):
        """
        Args:
            max_tokens: 最大上下文 Token 数
            model_name: 模型名称（用于 Token 计算）
            reserved_for_response: 预留给响应的 Token 数
        """
        self._max_tokens = max_tokens
        self._reserved = reserved_for_response
        self._effective_limit = max_tokens - reserved_for_response
        self._counter = get_token_counter(model_name)
        self._packets: list[ContextPacket] = []
        self._current_query: str = ""
        
    # ===== Gather 阶段 =====
    
    def add_packet(self, packet: ContextPacket) -> "ContextBuilder":
        """添加上下文片段"""
        # 计算 Token 数
        if packet.tokens == 0:
            packet.tokens = self._counter.count_text(packet.content)
        
        # 设置默认优先级
        if packet.priority == 0.5:
            packet.priority = self.TYPE_PRIORITY.get(packet.type, 0.5)
        
        self._packets.append(packet)
        return self
    
    def add_system_prompt(self, prompt: str) -> "ContextBuilder":
        """添加系统提示词（最高优先级，始终包含）"""
        return self.add_packet(ContextPacket(
            content=prompt,
            type=ContextType.SYSTEM_PROMPT,
            priority=1.0,
            relevance_score=1.0,
            recency_score=1.0,
        ))
    
    def add_task_instruction(self, instruction: str) -> "ContextBuilder":
        """添加任务指令"""
        return self.add_packet(ContextPacket(
            content=instruction,
            type=ContextType.TASK_INSTRUCTION,
            priority=0.95,
            relevance_score=1.0,
            recency_score=1.0,
        ))
    
    def add_summary(self, summary: str) -> "ContextBuilder":
        """添加历史摘要"""
        return self.add_packet(ContextPacket(
            content=summary,
            type=ContextType.SUMMARY,
            priority=0.85,
            relevance_score=0.8,
            recency_score=0.5,
        ))
    
    def add_history(
        self,
        messages: list,
        role_attr: str = "type",
        content_attr: str = "content",
    ) -> "ContextBuilder":
        """添加历史消息
        
        Args:
            messages: 消息列表
            role_attr: 角色属性名
            content_attr: 内容属性名
        """
        now = datetime.now(timezone.utc)
        total = len(messages)
        
        for i, msg in enumerate(messages):
            # 获取内容
            content = getattr(msg, content_attr, str(msg))
            
            # 计算新近性（指数衰减）
            # 越靠后的消息新近性越高
            position_ratio = (i + 1) / max(total, 1)
            recency = position_ratio ** 0.5  # 平方根衰减，更平滑
            
            # 获取时间戳
            timestamp = getattr(msg, "timestamp", None)
            if timestamp:
                # 基于时间的衰减（24小时内为1.0，之后指数衰减）
                age_hours = (now - timestamp).total_seconds() / 3600
                time_decay = max(0.1, 1.0 / (1 + age_hours / 24))
                recency = 0.5 * recency + 0.5 * time_decay
            
            # 获取角色
            role = getattr(msg, role_attr, "user")
            role_str = str(role).lower()
            if "user" in role_str:
                role_prefix = "[User] "
            elif "assistant" in role_str:
                role_prefix = "[Assistant] "
            elif "system" in role_str:
                role_prefix = "[System] "
            else:
                role_prefix = ""
            
            self.add_packet(ContextPacket(
                content=f"{role_prefix}{content}",
                type=ContextType.HISTORY,
                recency_score=recency,
                timestamp=timestamp,
                metadata={"role": role_str, "index": i},
            ))
        
        return self
    
    def add_rag_results(
        self,
        results: list[dict],
        score_key: str = "score",
        content_key: str = "content",
    ) -> "ContextBuilder":
        """添加 RAG 检索结果
        
        Args:
            results: 检索结果列表
            score_key: 分数字段名
            content_key: 内容字段名
        """
        for result in results:
            content = result.get(content_key, str(result))
            score = result.get(score_key, 0.5)
            
            self.add_packet(ContextPacket(
                content=f"[Reference] {content}",
                type=ContextType.RAG_RESULT,
                relevance_score=float(score),
                recency_score=0.5,
                metadata=result,
            ))
        
        return self
    
    def add_tool_output(
        self,
        tool_name: str,
        output: str,
        max_length: int = 2000,
    ) -> "ContextBuilder":
        """添加工具输出
        
        Args:
            tool_name: 工具名称
            output: 输出内容
            max_length: 最大长度（超出会截断）
        """
        # 截断过长的输出
        if len(output) > max_length:
            truncated = output[:max_length // 2] + "\n...[truncated]...\n" + output[-max_length // 2:]
            output = truncated
        
        return self.add_packet(ContextPacket(
            content=f"[Tool: {tool_name}]\n{output}",
            type=ContextType.TOOL_OUTPUT,
            relevance_score=0.8,
            recency_score=0.9,
        ))
    
    def add_entity_memory(self, entities: dict[str, Any]) -> "ContextBuilder":
        """添加实体记忆
        
        Args:
            entities: 实体字典 {实体名: 实体值}
        """
        if not entities:
            return self
        
        lines = ["[Known Information]"]
        for key, value in entities.items():
            lines.append(f"- {key}: {value}")
        
        return self.add_packet(ContextPacket(
            content="\n".join(lines),
            type=ContextType.ENTITY_MEMORY,
            relevance_score=0.7,
            recency_score=0.5,
        ))
    
    # ===== Select 阶段 =====
    
    def set_query(self, query: str) -> "ContextBuilder":
        """设置当前查询（用于相关性评分）"""
        self._current_query = query
        return self
    
    def _compute_relevance(self, packet: ContextPacket) -> float:
        """计算相关性分数
        
        基于关键词重叠的简单相关性评分
        """
        if not self._current_query or packet.type in (
            ContextType.SYSTEM_PROMPT,
            ContextType.TASK_INSTRUCTION,
        ):
            # 系统提示词始终相关
            return packet.relevance_score
        
        # 简单的关键词重叠
        query_words = set(self._current_query.lower().split())
        content_words = set(packet.content.lower().split())
        
        if not query_words:
            return packet.relevance_score
        
        overlap = len(query_words & content_words)
        overlap_ratio = overlap / len(query_words)
        
        # 混合原始分数和计算分数
        return 0.5 * packet.relevance_score + 0.5 * overlap_ratio
    
    def _select_packets(self) -> list[ContextPacket]:
        """筛选和排序上下文片段"""
        # 更新相关性分数
        for packet in self._packets:
            packet.relevance_score = self._compute_relevance(packet)
        
        # 按类型优先级分组
        must_include = []  # 系统提示词、任务指令（必须包含）
        optional = []      # 其他内容
        
        for packet in self._packets:
            if packet.type in (ContextType.SYSTEM_PROMPT, ContextType.TASK_INSTRUCTION):
                must_include.append(packet)
            else:
                optional.append(packet)
        
        # 必须包含的按优先级排序
        must_include.sort(key=lambda p: p.priority, reverse=True)
        
        # 可选的按复合分数排序
        optional.sort(key=lambda p: (p.priority, p.composite_score), reverse=True)
        
        return must_include + optional
    
    # ===== Structure 阶段 =====
    
    def _structure_messages(
        self,
        packets: list[ContextPacket],
    ) -> list[dict]:
        """将上下文片段结构化为消息列表
        
        遵循 OpenAI 消息格式:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
        """
        messages = []
        
        # 聚合系统消息
        system_parts = []
        
        for packet in packets:
            if packet.type == ContextType.SYSTEM_PROMPT:
                system_parts.append(packet.content)
            elif packet.type == ContextType.TASK_INSTRUCTION:
                system_parts.append(f"\n[Task]\n{packet.content}")
            elif packet.type == ContextType.SUMMARY:
                system_parts.append(f"\n[Previous Conversation Summary]\n{packet.content}")
            elif packet.type == ContextType.ENTITY_MEMORY:
                system_parts.append(f"\n{packet.content}")
            elif packet.type == ContextType.CURRENT_STATE:
                system_parts.append(f"\n[Current State]\n{packet.content}")
        
        # 添加聚合的系统消息
        if system_parts:
            messages.append({
                "role": "system",
                "content": "\n".join(system_parts),
            })
        
        # 添加历史消息
        history_packets = [p for p in packets if p.type == ContextType.HISTORY]
        # 按原始顺序排序
        history_packets.sort(key=lambda p: p.metadata.get("index", 0))
        
        for packet in history_packets:
            role = packet.metadata.get("role", "user")
            # 移除角色前缀
            content = packet.content
            for prefix in ["[User] ", "[Assistant] ", "[System] "]:
                if content.startswith(prefix):
                    content = content[len(prefix):]
                    break
            
            if "user" in role:
                messages.append({"role": "user", "content": content})
            elif "assistant" in role:
                messages.append({"role": "assistant", "content": content})
        
        # RAG 结果和工具输出作为 user 消息的补充
        rag_packets = [p for p in packets if p.type == ContextType.RAG_RESULT]
        tool_packets = [p for p in packets if p.type == ContextType.TOOL_OUTPUT]
        
        if rag_packets or tool_packets:
            supplement_parts = []
            
            if rag_packets:
                supplement_parts.append("[Retrieved Information]")
                for packet in rag_packets:
                    supplement_parts.append(packet.content.replace("[Reference] ", "- "))
            
            if tool_packets:
                supplement_parts.append("\n[Tool Outputs]")
                for packet in tool_packets:
                    supplement_parts.append(packet.content)
            
            # 插入到最后一个 user 消息之前
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]["role"] == "user":
                    messages.insert(i, {
                        "role": "user",
                        "content": "\n".join(supplement_parts),
                    })
                    break
            else:
                # 没有 user 消息，追加到末尾
                messages.append({
                    "role": "user",
                    "content": "\n".join(supplement_parts),
                })
        
        return messages
    
    # ===== Compress 阶段 =====
    
    def _compress_to_budget(
        self,
        packets: list[ContextPacket],
    ) -> tuple[list[ContextPacket], int, int]:
        """压缩到 Token 预算内
        
        Returns:
            (selected_packets, included_count, dropped_count)
        """
        selected = []
        total_tokens = 0
        dropped = 0
        
        for packet in packets:
            if total_tokens + packet.tokens <= self._effective_limit:
                selected.append(packet)
                total_tokens += packet.tokens
            else:
                # 超出预算
                if packet.type in (ContextType.SYSTEM_PROMPT, ContextType.TASK_INSTRUCTION):
                    # 必须包含的内容，强制加入
                    selected.append(packet)
                    total_tokens += packet.tokens
                else:
                    dropped += 1
        
        return selected, len(selected), dropped
    
    # ===== 主入口 =====
    
    def build(
        self,
        current_query: Optional[str] = None,
    ) -> StructuredContext:
        """构建结构化上下文
        
        执行完整的 GSSC 流水线：
        1. Gather - 已通过 add_* 方法完成
        2. Select - 基于相关性和优先级筛选排序
        3. Structure - 格式化为 LLM 消息格式
        4. Compress - 压缩到 Token 预算内
        
        Args:
            current_query: 当前用户查询（用于相关性计算）
            
        Returns:
            StructuredContext: 结构化上下文结果
        """
        if current_query:
            self.set_query(current_query)
        
        # Select: 筛选和排序
        sorted_packets = self._select_packets()
        
        # Compress: 压缩到预算
        selected, included, dropped = self._compress_to_budget(sorted_packets)
        
        # Structure: 结构化为消息
        messages = self._structure_messages(selected)
        
        # 计算实际 Token 数
        total_tokens = sum(p.tokens for p in selected)
        
        return StructuredContext(
            messages=messages,
            total_tokens=total_tokens,
            packets_included=included,
            packets_dropped=dropped,
            metadata={
                "max_tokens": self._max_tokens,
                "effective_limit": self._effective_limit,
                "reserved_for_response": self._reserved,
            },
        )
    
    def clear(self) -> "ContextBuilder":
        """清空所有上下文片段"""
        self._packets.clear()
        self._current_query = ""
        return self
    
    def get_stats(self) -> dict:
        """获取当前状态统计"""
        total_tokens = sum(p.tokens for p in self._packets)
        by_type = {}
        for packet in self._packets:
            type_name = packet.type.value
            if type_name not in by_type:
                by_type[type_name] = {"count": 0, "tokens": 0}
            by_type[type_name]["count"] += 1
            by_type[type_name]["tokens"] += packet.tokens
        
        return {
            "total_packets": len(self._packets),
            "total_tokens": total_tokens,
            "max_tokens": self._max_tokens,
            "effective_limit": self._effective_limit,
            "utilization": total_tokens / self._effective_limit if self._effective_limit > 0 else 0,
            "by_type": by_type,
        }
