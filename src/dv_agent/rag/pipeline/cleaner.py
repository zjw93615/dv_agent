"""
Text Cleaner
文本清洗器

去除文档噪声、标准化格式。
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CleanerConfig:
    """清洗器配置"""
    
    # 基础清理
    remove_extra_whitespace: bool = True  # 去除多余空白
    normalize_unicode: bool = True         # 标准化 Unicode
    fix_encoding: bool = True              # 修复编码问题
    
    # 内容过滤
    remove_urls: bool = False              # 移除 URL
    remove_emails: bool = False            # 移除邮箱
    remove_phone_numbers: bool = False     # 移除电话号码
    remove_special_chars: bool = False     # 移除特殊字符
    
    # 格式处理
    normalize_punctuation: bool = True     # 标准化标点
    remove_header_footer: bool = True      # 移除页眉页脚
    remove_page_numbers: bool = True       # 移除页码
    
    # 中文特殊处理
    convert_to_simplified: bool = False    # 繁体转简体
    fix_chinese_punctuation: bool = True   # 修复中文标点
    
    # 阈值设置
    min_line_length: int = 2               # 最小行长度（短于此的删除）
    max_repeat_chars: int = 5              # 最大重复字符数


class TextCleaner:
    """
    文本清洗器
    
    提供多种清洗策略，去除文档噪声并标准化格式。
    """
    
    # 常见模式
    URL_PATTERN = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+|'
        r'www\.[^\s<>"{}|\\^`\[\]]+'
    )
    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    )
    PHONE_PATTERN = re.compile(
        r'(?:\+?86)?[-\s]?1[3-9]\d{9}|'   # 中国手机
        r'\d{3,4}[-\s]?\d{7,8}|'           # 座机
        r'\(\d{3,4}\)[-\s]?\d{7,8}'        # 带括号座机
    )
    PAGE_NUMBER_PATTERN = re.compile(
        r'^[-—]?\s*(?:第?\s*\d+\s*页?|'
        r'Page\s*\d+|'
        r'\d+\s*/\s*\d+)\s*[-—]?$',
        re.IGNORECASE | re.MULTILINE
    )
    HEADER_FOOTER_PATTERN = re.compile(
        r'^.{1,50}(?:机密|保密|内部|版权|Copyright|Confidential|All Rights Reserved).*$|'
        r'^(?:文档编号|Document\s*ID|版本|Version)[:：].*$',
        re.IGNORECASE | re.MULTILINE
    )
    
    # 需要标准化的标点映射
    PUNCTUATION_MAP = {
        '，': ', ',
        '。': '. ',
        '；': '; ',
        '：': ': ',
        '！': '! ',
        '？': '? ',
        '"': '"',
        '"': '"',
        ''': "'",
        ''': "'",
        '【': '[',
        '】': ']',
        '（': '(',
        '）': ')',
        '《': '<',
        '》': '>',
        '—': '-',
        '…': '...',
    }
    
    def __init__(self, config: Optional[CleanerConfig] = None):
        """
        初始化清洗器
        
        Args:
            config: 清洗器配置
        """
        self.config = config or CleanerConfig()
        
        # 延迟加载简繁转换
        self._opencc = None
    
    def clean(self, text: str) -> str:
        """
        清洗文本
        
        Args:
            text: 要清洗的文本
            
        Returns:
            清洗后的文本
        """
        if not text:
            return ""
        
        # 基础清理
        if self.config.fix_encoding:
            text = self._fix_encoding(text)
        
        if self.config.normalize_unicode:
            text = self._normalize_unicode(text)
        
        # 内容过滤
        if self.config.remove_urls:
            text = self._remove_urls(text)
        
        if self.config.remove_emails:
            text = self._remove_emails(text)
        
        if self.config.remove_phone_numbers:
            text = self._remove_phone_numbers(text)
        
        # 格式处理
        if self.config.remove_header_footer:
            text = self._remove_header_footer(text)
        
        if self.config.remove_page_numbers:
            text = self._remove_page_numbers(text)
        
        if self.config.normalize_punctuation:
            text = self._normalize_punctuation(text)
        
        if self.config.fix_chinese_punctuation:
            text = self._fix_chinese_punctuation(text)
        
        if self.config.remove_special_chars:
            text = self._remove_special_chars(text)
        
        # 中文处理
        if self.config.convert_to_simplified:
            text = self._convert_to_simplified(text)
        
        # 空白处理
        if self.config.remove_extra_whitespace:
            text = self._remove_extra_whitespace(text)
        
        # 清理短行
        if self.config.min_line_length > 0:
            text = self._remove_short_lines(text)
        
        # 处理重复字符
        if self.config.max_repeat_chars > 0:
            text = self._limit_repeat_chars(text)
        
        return text.strip()
    
    def clean_lines(self, lines: list[str]) -> list[str]:
        """
        清洗多行文本
        
        Args:
            lines: 文本行列表
            
        Returns:
            清洗后的行列表
        """
        cleaned = []
        for line in lines:
            cleaned_line = self.clean(line)
            if cleaned_line:
                cleaned.append(cleaned_line)
        return cleaned
    
    def _fix_encoding(self, text: str) -> str:
        """修复编码问题"""
        # 处理常见的编码错误字符
        replacements = {
            '\ufeff': '',      # BOM
            '\x00': '',        # NULL
            '\xa0': ' ',       # NBSP
            '\u200b': '',      # Zero-width space
            '\u200c': '',      # Zero-width non-joiner
            '\u200d': '',      # Zero-width joiner
            '\u2028': '\n',    # Line separator
            '\u2029': '\n',    # Paragraph separator
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    def _normalize_unicode(self, text: str) -> str:
        """标准化 Unicode"""
        # 使用 NFKC 标准化（兼容性分解后再组合）
        return unicodedata.normalize('NFKC', text)
    
    def _remove_urls(self, text: str) -> str:
        """移除 URL"""
        return self.URL_PATTERN.sub(' ', text)
    
    def _remove_emails(self, text: str) -> str:
        """移除邮箱"""
        return self.EMAIL_PATTERN.sub(' ', text)
    
    def _remove_phone_numbers(self, text: str) -> str:
        """移除电话号码"""
        return self.PHONE_PATTERN.sub(' ', text)
    
    def _remove_header_footer(self, text: str) -> str:
        """移除页眉页脚"""
        return self.HEADER_FOOTER_PATTERN.sub('', text)
    
    def _remove_page_numbers(self, text: str) -> str:
        """移除页码"""
        return self.PAGE_NUMBER_PATTERN.sub('', text)
    
    def _normalize_punctuation(self, text: str) -> str:
        """标准化标点符号"""
        for old, new in self.PUNCTUATION_MAP.items():
            text = text.replace(old, new)
        return text
    
    def _fix_chinese_punctuation(self, text: str) -> str:
        """修复中文标点后缺少空格的问题"""
        # 中文标点后如果紧跟非空白字符，添加空格
        text = re.sub(r'([。！？；：])([^\s])', r'\1 \2', text)
        return text
    
    def _remove_special_chars(self, text: str) -> str:
        """移除特殊字符（保留基本标点和数字）"""
        # 保留中文、英文、数字、基本标点
        return re.sub(
            r'[^\w\s\u4e00-\u9fff.,!?;:\'"()\[\]{}<>@#$%&*+=/-]',
            ' ',
            text
        )
    
    def _convert_to_simplified(self, text: str) -> str:
        """繁体转简体"""
        try:
            if self._opencc is None:
                import opencc
                self._opencc = opencc.OpenCC('t2s')
            return self._opencc.convert(text)
        except ImportError:
            logger.warning(
                "opencc-python-reimplemented not installed. "
                "Run: pip install opencc-python-reimplemented"
            )
            return text
        except Exception as e:
            logger.warning(f"Failed to convert to simplified: {e}")
            return text
    
    def _remove_extra_whitespace(self, text: str) -> str:
        """去除多余空白"""
        # 将多个空格替换为单个
        text = re.sub(r'[ \t]+', ' ', text)
        # 将多个换行替换为双换行（保留段落分隔）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 去除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]
        return '\n'.join(lines)
    
    def _remove_short_lines(self, text: str) -> str:
        """移除短行"""
        lines = text.split('\n')
        filtered = [
            line for line in lines
            if len(line.strip()) >= self.config.min_line_length or not line.strip()
        ]
        return '\n'.join(filtered)
    
    def _limit_repeat_chars(self, text: str) -> str:
        """限制重复字符"""
        max_repeat = self.config.max_repeat_chars
        # 匹配连续重复的字符
        pattern = r'(.)\1{' + str(max_repeat) + r',}'
        return re.sub(pattern, r'\1' * max_repeat, text)
    
    @classmethod
    def from_config(cls, config: dict) -> "TextCleaner":
        """
        从配置字典创建清洗器
        
        Args:
            config: 配置字典
            
        Returns:
            TextCleaner 实例
        """
        cleaner_config = CleanerConfig(
            remove_extra_whitespace=config.get("remove_extra_whitespace", True),
            normalize_unicode=config.get("normalize_unicode", True),
            fix_encoding=config.get("fix_encoding", True),
            remove_urls=config.get("remove_urls", False),
            remove_emails=config.get("remove_emails", False),
            remove_phone_numbers=config.get("remove_phone_numbers", False),
            remove_special_chars=config.get("remove_special_chars", False),
            normalize_punctuation=config.get("normalize_punctuation", True),
            remove_header_footer=config.get("remove_header_footer", True),
            remove_page_numbers=config.get("remove_page_numbers", True),
            convert_to_simplified=config.get("convert_to_simplified", False),
            fix_chinese_punctuation=config.get("fix_chinese_punctuation", True),
            min_line_length=config.get("min_line_length", 2),
            max_repeat_chars=config.get("max_repeat_chars", 5),
        )
        return cls(cleaner_config)
