"""
Document Format Detector
文档格式检测器

基于文件扩展名和 magic number 检测文档格式。
"""

import logging
import mimetypes
from enum import Enum
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


class FileFormat(str, Enum):
    """支持的文件格式"""
    
    # Documents
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    XLSX = "xlsx"
    XLS = "xls"
    PPTX = "pptx"
    PPT = "ppt"
    
    # Text formats
    TXT = "txt"
    MD = "md"
    HTML = "html"
    HTM = "htm"
    XML = "xml"
    JSON = "json"
    CSV = "csv"
    
    # Other
    UNKNOWN = "unknown"
    
    @classmethod
    def from_extension(cls, ext: str) -> "FileFormat":
        """根据扩展名获取格式"""
        ext = ext.lower().lstrip(".")
        try:
            return cls(ext)
        except ValueError:
            return cls.UNKNOWN
    
    @property
    def is_supported(self) -> bool:
        """是否是支持的格式"""
        return self in SUPPORTED_FORMATS
    
    @property
    def is_office(self) -> bool:
        """是否是 Office 文档"""
        return self in {
            FileFormat.DOCX, FileFormat.DOC,
            FileFormat.XLSX, FileFormat.XLS,
            FileFormat.PPTX, FileFormat.PPT,
        }
    
    @property
    def is_text(self) -> bool:
        """是否是纯文本格式"""
        return self in {
            FileFormat.TXT, FileFormat.MD,
            FileFormat.HTML, FileFormat.HTM,
            FileFormat.XML, FileFormat.JSON,
            FileFormat.CSV,
        }


# 支持的文件格式
SUPPORTED_FORMATS = {
    FileFormat.PDF,
    FileFormat.DOCX,
    FileFormat.XLSX,
    FileFormat.PPTX,
    FileFormat.TXT,
    FileFormat.MD,
    FileFormat.HTML,
    FileFormat.HTM,
}

# MIME 类型映射
MIME_TO_FORMAT = {
    "application/pdf": FileFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileFormat.DOCX,
    "application/msword": FileFormat.DOC,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileFormat.XLSX,
    "application/vnd.ms-excel": FileFormat.XLS,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileFormat.PPTX,
    "application/vnd.ms-powerpoint": FileFormat.PPT,
    "text/plain": FileFormat.TXT,
    "text/markdown": FileFormat.MD,
    "text/html": FileFormat.HTML,
    "text/xml": FileFormat.XML,
    "application/json": FileFormat.JSON,
    "text/csv": FileFormat.CSV,
}

# Magic numbers (文件头字节)
MAGIC_NUMBERS = {
    b"%PDF": FileFormat.PDF,
    b"PK\x03\x04": None,  # ZIP-based formats (docx, xlsx, pptx) - need further check
    b"\xd0\xcf\x11\xe0": None,  # OLE compound - old Office formats
}


class DocumentDetector:
    """
    文档格式检测器
    
    使用多种策略检测文档格式：
    1. 文件扩展名
    2. MIME 类型
    3. Magic number (文件头)
    """
    
    def __init__(self, use_magic: bool = True):
        """
        初始化检测器
        
        Args:
            use_magic: 是否使用 python-magic 库进行深度检测
        """
        self.use_magic = use_magic
        self._magic = None
        
        if use_magic:
            try:
                import magic
                self._magic = magic.Magic(mime=True)
            except ImportError:
                logger.warning(
                    "python-magic not installed. "
                    "Run: pip install python-magic"
                )
                self.use_magic = False
            except Exception as e:
                logger.warning(f"Failed to initialize magic: {e}")
                self.use_magic = False
    
    def detect(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> FileFormat:
        """
        检测文档格式
        
        Args:
            file_path: 文件路径
            content: 文件内容（字节）
            filename: 文件名（用于扩展名检测）
            
        Returns:
            检测到的文件格式
        """
        # Strategy 1: 从文件路径获取扩展名
        if file_path:
            path = Path(file_path)
            if path.suffix:
                fmt = FileFormat.from_extension(path.suffix)
                if fmt.is_supported:
                    return fmt
            
            # 读取文件内容用于后续检测
            if content is None and path.exists():
                with open(path, "rb") as f:
                    content = f.read(1024)  # 只读取前 1KB
        
        # Strategy 2: 从文件名获取扩展名
        if filename:
            ext = Path(filename).suffix
            if ext:
                fmt = FileFormat.from_extension(ext)
                if fmt.is_supported:
                    return fmt
        
        # Strategy 3: 使用 python-magic 检测 MIME 类型
        if content and self.use_magic and self._magic:
            try:
                mime_type = self._magic.from_buffer(content)
                if mime_type in MIME_TO_FORMAT:
                    fmt = MIME_TO_FORMAT[mime_type]
                    if fmt and fmt.is_supported:
                        return fmt
            except Exception as e:
                logger.debug(f"Magic detection failed: {e}")
        
        # Strategy 4: 检查 magic number
        if content:
            fmt = self._detect_by_magic_number(content)
            if fmt and fmt.is_supported:
                return fmt
        
        return FileFormat.UNKNOWN
    
    def _detect_by_magic_number(self, content: bytes) -> Optional[FileFormat]:
        """
        根据 magic number 检测格式
        
        Args:
            content: 文件内容
            
        Returns:
            检测到的格式，未知返回 None
        """
        # Check PDF
        if content.startswith(b"%PDF"):
            return FileFormat.PDF
        
        # Check ZIP-based formats (Office 2007+)
        if content.startswith(b"PK\x03\x04"):
            # Need to check internal structure for Office documents
            # For now, rely on extension
            return None
        
        # Check HTML
        lower_content = content[:100].lower()
        if b"<!doctype html" in lower_content or b"<html" in lower_content:
            return FileFormat.HTML
        
        # Check XML
        if content.startswith(b"<?xml"):
            return FileFormat.XML
        
        # Check JSON
        stripped = content.lstrip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            try:
                import json
                json.loads(content)
                return FileFormat.JSON
            except Exception:
                pass
        
        return None
    
    def detect_mime_type(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        获取文件的 MIME 类型
        
        Args:
            file_path: 文件路径
            content: 文件内容
            filename: 文件名
            
        Returns:
            MIME 类型字符串
        """
        # Try python-magic first
        if content and self.use_magic and self._magic:
            try:
                return self._magic.from_buffer(content)
            except Exception:
                pass
        
        # Fall back to mimetypes module
        name = filename or (str(file_path) if file_path else None)
        if name:
            mime_type, _ = mimetypes.guess_type(name)
            if mime_type:
                return mime_type
        
        return "application/octet-stream"
    
    def is_supported(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> bool:
        """
        检查文件是否是支持的格式
        
        Args:
            file_path: 文件路径
            content: 文件内容
            filename: 文件名
            
        Returns:
            是否支持
        """
        fmt = self.detect(file_path, content, filename)
        return fmt.is_supported
    
    @staticmethod
    def get_supported_formats() -> list[str]:
        """获取支持的文件格式列表"""
        return [fmt.value for fmt in SUPPORTED_FORMATS]
    
    @staticmethod
    def get_supported_extensions() -> list[str]:
        """获取支持的文件扩展名列表"""
        return [f".{fmt.value}" for fmt in SUPPORTED_FORMATS]
