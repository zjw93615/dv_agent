"""
Text Chunker
文本语义切分器

基于 RecursiveCharacterTextSplitter 的语义切分实现。
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """文本块"""
    
    index: int
    content: str
    start_offset: int
    end_offset: int
    page_number: Optional[int] = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def length(self) -> int:
        """块长度"""
        return len(self.content)
    
    def __str__(self) -> str:
        return self.content


class TextChunker:
    """
    文本语义切分器
    
    使用递归字符切分策略，在保留语义完整性的同时将长文本切分为适合向量检索的小块。
    
    特点：
    - 优先在自然边界（段落、句子）处切分
    - 支持配置块大小和重叠
    - 保留元数据（页码、位置偏移）
    """
    
    # 默认分隔符（按优先级排序）
    DEFAULT_SEPARATORS = [
        "\n\n",      # 段落边界
        "\n",        # 换行
        "。",        # 中文句号
        ".",         # 英文句号
        "！",        # 中文感叹号
        "!",         # 英文感叹号
        "？",        # 中文问号
        "?",         # 英文问号
        "；",        # 中文分号
        ";",         # 英文分号
        "，",        # 中文逗号
        ",",         # 英文逗号
        " ",         # 空格
        "",          # 字符级（最后手段）
    ]
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 20,
        separators: Optional[list[str]] = None,
        length_function: Optional[callable] = None,
    ):
        """
        初始化切分器
        
        Args:
            chunk_size: 目标块大小（字符数）
            chunk_overlap: 块之间的重叠大小
            min_chunk_size: 最小块大小（小于此大小的块将被丢弃）
            separators: 分隔符列表（按优先级排序）
            length_function: 自定义长度计算函数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.separators = separators or self.DEFAULT_SEPARATORS
        self.length_function = length_function or len
    
    def chunk(
        self,
        text: str,
        page_number: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        切分文本
        
        Args:
            text: 要切分的文本
            page_number: 页码（可选）
            metadata: 附加元数据
            
        Returns:
            切分后的块列表
        """
        if not text or not text.strip():
            return []
        
        # 使用递归切分
        raw_chunks = self._split_text(text, self.separators)
        
        # 合并相邻小块
        merged_chunks = self._merge_splits(raw_chunks)
        
        # 转换为 Chunk 对象
        chunks = []
        current_offset = 0
        
        for i, chunk_text in enumerate(merged_chunks):
            if self.length_function(chunk_text) < self.min_chunk_size:
                continue
            
            # 查找在原文中的位置
            start_offset = text.find(chunk_text, current_offset)
            if start_offset == -1:
                start_offset = current_offset
            
            end_offset = start_offset + len(chunk_text)
            
            chunk = Chunk(
                index=len(chunks),
                content=chunk_text.strip(),
                start_offset=start_offset,
                end_offset=end_offset,
                page_number=page_number,
                metadata=metadata or {},
            )
            chunks.append(chunk)
            
            # 更新偏移，考虑重叠
            current_offset = max(start_offset + 1, end_offset - self.chunk_overlap)
        
        return chunks
    
    def chunk_with_pages(
        self,
        pages: list[tuple[str, int]],
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        按页切分文本
        
        Args:
            pages: (文本, 页码) 元组列表
            metadata: 附加元数据
            
        Returns:
            切分后的块列表（保留页码信息）
        """
        all_chunks = []
        
        for page_text, page_number in pages:
            page_chunks = self.chunk(page_text, page_number, metadata)
            
            # 重新编号
            for chunk in page_chunks:
                chunk.index = len(all_chunks)
                all_chunks.append(chunk)
        
        return all_chunks
    
    def _split_text(
        self,
        text: str,
        separators: list[str],
    ) -> list[str]:
        """
        递归切分文本
        
        Args:
            text: 要切分的文本
            separators: 当前可用的分隔符列表
            
        Returns:
            切分后的文本片段列表
        """
        final_chunks = []
        
        # 找到可用的分隔符
        separator = separators[-1]  # 默认使用最后一个（字符级）
        new_separators = []
        
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break
        
        # 使用分隔符切分
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        
        # 处理每个片段
        good_splits = []
        
        for split in splits:
            if not split:
                continue
            
            if self.length_function(split) < self.chunk_size:
                good_splits.append(split)
            else:
                # 片段太大，需要继续切分
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                
                if new_separators:
                    # 递归使用更细粒度的分隔符
                    other_chunks = self._split_text(split, new_separators)
                    final_chunks.extend(other_chunks)
                else:
                    # 强制按大小切分
                    final_chunks.extend(self._force_split(split))
        
        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)
        
        return final_chunks
    
    def _merge_splits(
        self,
        splits: list[str],
        separator: str = "",
    ) -> list[str]:
        """
        合并小片段
        
        Args:
            splits: 文本片段列表
            separator: 用于连接的分隔符
            
        Returns:
            合并后的片段列表
        """
        merged = []
        current = []
        current_length = 0
        
        for split in splits:
            split_length = self.length_function(split)
            
            # 检查是否需要开始新块
            if current_length + split_length > self.chunk_size and current:
                merged.append(separator.join(current))
                
                # 保留重叠部分
                if self.chunk_overlap > 0:
                    overlap_splits = []
                    overlap_length = 0
                    for s in reversed(current):
                        s_len = self.length_function(s)
                        if overlap_length + s_len > self.chunk_overlap:
                            break
                        overlap_splits.insert(0, s)
                        overlap_length += s_len
                    current = overlap_splits
                    current_length = overlap_length
                else:
                    current = []
                    current_length = 0
            
            current.append(split)
            current_length += split_length + (len(separator) if current else 0)
        
        if current:
            merged.append(separator.join(current))
        
        return merged
    
    def _force_split(self, text: str) -> list[str]:
        """
        强制按大小切分（最后手段）
        
        Args:
            text: 要切分的文本
            
        Returns:
            切分后的片段列表
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - self.chunk_overlap if self.chunk_overlap > 0 else end
        
        return chunks
    
    @classmethod
    def from_config(cls, config: dict) -> "TextChunker":
        """
        从配置创建切分器
        
        Args:
            config: 配置字典
            
        Returns:
            TextChunker 实例
        """
        return cls(
            chunk_size=config.get("chunk_size", 500),
            chunk_overlap=config.get("chunk_overlap", 50),
            min_chunk_size=config.get("min_chunk_size", 20),
            separators=config.get("separators"),
        )
