"""
Metadata Extractor
元数据提取器

从文档中提取结构化元数据。
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """文档元数据"""
    
    # 基础信息
    doc_id: str = ""                       # 文档ID（唯一标识）
    filename: str = ""                     # 文件名
    file_path: Optional[str] = None        # 文件路径
    file_type: str = ""                    # 文件类型
    file_size: int = 0                     # 文件大小（字节）
    content_hash: str = ""                 # 内容哈希（用于去重）
    
    # 文档属性
    title: str = ""                        # 标题
    author: str = ""                       # 作者
    language: str = ""                     # 语言
    page_count: int = 0                    # 页数
    word_count: int = 0                    # 字数
    
    # 时间信息
    created_at: Optional[datetime] = None  # 创建时间
    modified_at: Optional[datetime] = None # 修改时间
    indexed_at: Optional[datetime] = None  # 索引时间
    
    # 来源和分类
    source: str = ""                       # 来源
    category: str = ""                     # 分类
    tags: list[str] = field(default_factory=list)  # 标签
    
    # 租户信息
    tenant_id: str = ""                    # 租户ID
    collection_id: str = ""                # 集合ID
    
    # 扩展字段
    extra: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "content_hash": self.content_hash,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "page_count": self.page_count,
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "source": self.source,
            "category": self.category,
            "tags": self.tags,
            "tenant_id": self.tenant_id,
            "collection_id": self.collection_id,
            "extra": self.extra,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentMetadata":
        """从字典创建"""
        # 处理时间字段
        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)
        
        return cls(
            doc_id=data.get("doc_id", ""),
            filename=data.get("filename", ""),
            file_path=data.get("file_path"),
            file_type=data.get("file_type", ""),
            file_size=data.get("file_size", 0),
            content_hash=data.get("content_hash", ""),
            title=data.get("title", ""),
            author=data.get("author", ""),
            language=data.get("language", ""),
            page_count=data.get("page_count", 0),
            word_count=data.get("word_count", 0),
            created_at=parse_datetime(data.get("created_at")),
            modified_at=parse_datetime(data.get("modified_at")),
            indexed_at=parse_datetime(data.get("indexed_at")),
            source=data.get("source", ""),
            category=data.get("category", ""),
            tags=data.get("tags", []),
            tenant_id=data.get("tenant_id", ""),
            collection_id=data.get("collection_id", ""),
            extra=data.get("extra", {}),
        )


class MetadataExtractor:
    """
    元数据提取器
    
    从文档文件和内容中提取元数据。
    """
    
    # 语言检测模式
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
    ENGLISH_PATTERN = re.compile(r'[a-zA-Z]')
    
    def __init__(self):
        """初始化提取器"""
        self._langdetect_available = self._check_langdetect()
    
    def _check_langdetect(self) -> bool:
        """检查语言检测库是否可用"""
        try:
            import langdetect
            return True
        except ImportError:
            logger.warning(
                "langdetect not installed. Language detection will use fallback. "
                "Run: pip install langdetect"
            )
            return False
    
    def extract(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
        text: Optional[str] = None,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        tenant_id: str = "",
        collection_id: str = "",
        extra_metadata: Optional[dict] = None,
    ) -> DocumentMetadata:
        """
        提取文档元数据
        
        Args:
            file_path: 文件路径
            content: 文件内容（字节）
            text: 提取的文本内容
            filename: 文件名
            file_type: 文件类型
            tenant_id: 租户ID
            collection_id: 集合ID
            extra_metadata: 额外元数据
            
        Returns:
            文档元数据
        """
        metadata = DocumentMetadata()
        
        # 基础信息
        if file_path:
            path = Path(file_path)
            metadata.filename = filename or path.name
            metadata.file_path = str(path.absolute())
            metadata.file_type = file_type or path.suffix.lstrip('.').lower()
            
            if path.exists():
                stat = path.stat()
                metadata.file_size = stat.st_size
                metadata.modified_at = datetime.fromtimestamp(stat.st_mtime)
                metadata.created_at = datetime.fromtimestamp(stat.st_ctime)
        elif filename:
            metadata.filename = filename
            metadata.file_type = file_type or Path(filename).suffix.lstrip('.').lower()
        
        # 内容哈希
        if content:
            metadata.content_hash = self._compute_hash(content)
            metadata.file_size = len(content)
        elif file_path and Path(file_path).exists():
            with open(file_path, "rb") as f:
                metadata.content_hash = self._compute_hash(f.read())
        
        # 从文本提取
        if text:
            metadata.word_count = self._count_words(text)
            metadata.language = self._detect_language(text)
            metadata.title = self._extract_title(text, metadata.filename)
        
        # 生成文档ID
        metadata.doc_id = self._generate_doc_id(
            metadata.content_hash,
            metadata.filename,
            tenant_id,
        )
        
        # 租户信息
        metadata.tenant_id = tenant_id
        metadata.collection_id = collection_id
        
        # 索引时间
        metadata.indexed_at = datetime.now()
        
        # 合并额外元数据
        if extra_metadata:
            self._merge_extra_metadata(metadata, extra_metadata)
        
        return metadata
    
    def extract_from_pdf(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """
        从 PDF 提取元数据
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            元数据字典
        """
        metadata = {}
        
        try:
            import fitz  # PyMuPDF
            
            if file_path:
                doc = fitz.open(file_path)
            elif content:
                doc = fitz.open(stream=content, filetype="pdf")
            else:
                return metadata
            
            # 提取PDF元数据
            pdf_meta = doc.metadata
            if pdf_meta:
                metadata["title"] = pdf_meta.get("title", "")
                metadata["author"] = pdf_meta.get("author", "")
                metadata["subject"] = pdf_meta.get("subject", "")
                metadata["keywords"] = pdf_meta.get("keywords", "")
                metadata["creator"] = pdf_meta.get("creator", "")
                metadata["producer"] = pdf_meta.get("producer", "")
                
                # 时间处理
                if pdf_meta.get("creationDate"):
                    metadata["created_at"] = self._parse_pdf_date(
                        pdf_meta["creationDate"]
                    )
                if pdf_meta.get("modDate"):
                    metadata["modified_at"] = self._parse_pdf_date(
                        pdf_meta["modDate"]
                    )
            
            metadata["page_count"] = len(doc)
            doc.close()
            
        except ImportError:
            logger.warning("PyMuPDF not installed for PDF metadata extraction")
        except Exception as e:
            logger.warning(f"Failed to extract PDF metadata: {e}")
        
        return metadata
    
    def extract_from_docx(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """
        从 Word 文档提取元数据
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            元数据字典
        """
        metadata = {}
        
        try:
            from docx import Document
            from io import BytesIO
            
            if file_path:
                doc = Document(file_path)
            elif content:
                doc = Document(BytesIO(content))
            else:
                return metadata
            
            # 提取核心属性
            core_props = doc.core_properties
            if core_props:
                metadata["title"] = core_props.title or ""
                metadata["author"] = core_props.author or ""
                metadata["subject"] = core_props.subject or ""
                metadata["keywords"] = core_props.keywords or ""
                metadata["category"] = core_props.category or ""
                metadata["created_at"] = core_props.created
                metadata["modified_at"] = core_props.modified
                metadata["last_modified_by"] = core_props.last_modified_by or ""
            
        except ImportError:
            logger.warning("python-docx not installed for DOCX metadata extraction")
        except Exception as e:
            logger.warning(f"Failed to extract DOCX metadata: {e}")
        
        return metadata
    
    def _compute_hash(self, content: bytes) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content).hexdigest()
    
    def _count_words(self, text: str) -> int:
        """统计字数"""
        # 中文按字计数，英文按词计数
        chinese_chars = len(self.CHINESE_PATTERN.findall(text))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        return chinese_chars + english_words
    
    def _detect_language(self, text: str) -> str:
        """检测语言"""
        if not text or len(text.strip()) < 10:
            return "unknown"
        
        # 使用 langdetect
        if self._langdetect_available:
            try:
                import langdetect
                lang = langdetect.detect(text[:1000])
                return lang
            except Exception:
                pass
        
        # 简单的启发式检测
        chinese_count = len(self.CHINESE_PATTERN.findall(text))
        english_count = len(self.ENGLISH_PATTERN.findall(text))
        
        if chinese_count > english_count:
            return "zh"
        elif english_count > chinese_count:
            return "en"
        else:
            return "unknown"
    
    def _extract_title(self, text: str, filename: str = "") -> str:
        """从文本提取标题"""
        if not text:
            return filename
        
        # 取第一行非空内容作为标题
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) <= 200:  # 标题不应太长
                # 移除常见的标题标记
                title = re.sub(r'^[#\-\*\d\.]+\s*', '', line)
                if title:
                    return title
        
        # 使用文件名作为后备
        if filename:
            return Path(filename).stem
        
        return ""
    
    def _generate_doc_id(
        self,
        content_hash: str,
        filename: str,
        tenant_id: str,
    ) -> str:
        """生成文档ID"""
        # 使用内容哈希、文件名和租户ID组合生成唯一ID
        combined = f"{tenant_id}:{filename}:{content_hash}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _parse_pdf_date(self, date_str: str) -> Optional[datetime]:
        """解析PDF日期格式"""
        try:
            # PDF 日期格式: D:YYYYMMDDHHmmSS
            if date_str.startswith("D:"):
                date_str = date_str[2:]
            
            # 提取年月日时分秒
            if len(date_str) >= 14:
                return datetime.strptime(date_str[:14], "%Y%m%d%H%M%S")
            elif len(date_str) >= 8:
                return datetime.strptime(date_str[:8], "%Y%m%d")
        except Exception:
            pass
        
        return None
    
    def _merge_extra_metadata(
        self,
        metadata: DocumentMetadata,
        extra: dict,
    ) -> None:
        """合并额外元数据"""
        # 标准字段
        if "title" in extra and not metadata.title:
            metadata.title = extra["title"]
        if "author" in extra and not metadata.author:
            metadata.author = extra["author"]
        if "language" in extra and not metadata.language:
            metadata.language = extra["language"]
        if "page_count" in extra and not metadata.page_count:
            metadata.page_count = extra["page_count"]
        if "source" in extra:
            metadata.source = extra["source"]
        if "category" in extra:
            metadata.category = extra["category"]
        if "tags" in extra:
            metadata.tags = extra["tags"]
        
        # 时间字段
        if "created_at" in extra and extra["created_at"]:
            if isinstance(extra["created_at"], datetime):
                metadata.created_at = extra["created_at"]
        if "modified_at" in extra and extra["modified_at"]:
            if isinstance(extra["modified_at"], datetime):
                metadata.modified_at = extra["modified_at"]
        
        # 其他字段放入 extra
        standard_fields = {
            "title", "author", "language", "page_count", 
            "source", "category", "tags", "created_at", "modified_at"
        }
        for key, value in extra.items():
            if key not in standard_fields:
                metadata.extra[key] = value
