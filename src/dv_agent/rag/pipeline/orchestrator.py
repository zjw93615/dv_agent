"""
Document Pipeline Orchestrator
文档处理流水线编排器

整合文档处理的各个步骤，提供统一的处理接口。
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from .chunker import Chunk, TextChunker
from .cleaner import CleanerConfig, TextCleaner
from .detector import DocumentDetector, FileFormat
from .extractor import DocumentExtractor, ExtractedContent
from .metadata import DocumentMetadata, MetadataExtractor

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    """处理状态"""
    
    PENDING = "pending"
    DETECTING = "detecting"
    EXTRACTING = "extracting"
    CLEANING = "cleaning"
    CHUNKING = "chunking"
    METADATA = "metadata"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingResult:
    """处理结果"""
    
    status: ProcessingStatus = ProcessingStatus.PENDING
    metadata: Optional[DocumentMetadata] = None
    chunks: list[Chunk] = field(default_factory=list)
    raw_text: str = ""
    cleaned_text: str = ""
    file_format: Optional[FileFormat] = None
    errors: list[str] = field(default_factory=list)
    processing_time: float = 0.0
    
    @property
    def success(self) -> bool:
        """是否处理成功"""
        return self.status == ProcessingStatus.COMPLETED
    
    @property
    def chunk_count(self) -> int:
        """块数量"""
        return len(self.chunks)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "status": self.status.value,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "chunk_count": self.chunk_count,
            "raw_text_length": len(self.raw_text),
            "cleaned_text_length": len(self.cleaned_text),
            "file_format": self.file_format.value if self.file_format else None,
            "errors": self.errors,
            "processing_time": self.processing_time,
        }


@dataclass
class PipelineConfig:
    """流水线配置"""
    
    # 文档提取
    ocr_languages: list[str] = field(default_factory=lambda: ["chi_sim", "eng"])
    extraction_strategy: str = "auto"
    use_hi_res: bool = False
    
    # 文本切分
    chunk_size: int = 500
    chunk_overlap: int = 50
    min_chunk_size: int = 20
    
    # 文本清洗
    cleaner_config: Optional[CleanerConfig] = None
    
    # 元数据
    auto_extract_metadata: bool = True
    
    @classmethod
    def from_dict(cls, config: dict) -> "PipelineConfig":
        """从字典创建配置"""
        cleaner_cfg = None
        if "cleaner" in config:
            cleaner_cfg = CleanerConfig(**config["cleaner"])
        
        return cls(
            ocr_languages=config.get("ocr_languages", ["chi_sim", "eng"]),
            extraction_strategy=config.get("extraction_strategy", "auto"),
            use_hi_res=config.get("use_hi_res", False),
            chunk_size=config.get("chunk_size", 500),
            chunk_overlap=config.get("chunk_overlap", 50),
            min_chunk_size=config.get("min_chunk_size", 20),
            cleaner_config=cleaner_cfg,
            auto_extract_metadata=config.get("auto_extract_metadata", True),
        )


class DocumentPipeline:
    """
    文档处理流水线
    
    整合文档处理的各个步骤：
    1. 格式检测
    2. 内容提取
    3. 文本清洗
    4. 语义切分
    5. 元数据提取
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        初始化流水线
        
        Args:
            config: 流水线配置
        """
        self.config = config or PipelineConfig()
        
        # 初始化各组件
        self.detector = DocumentDetector()
        self.extractor = DocumentExtractor(
            ocr_languages=self.config.ocr_languages,
            strategy=self.config.extraction_strategy,
            use_hi_res=self.config.use_hi_res,
        )
        self.cleaner = TextCleaner(self.config.cleaner_config)
        self.chunker = TextChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            min_chunk_size=self.config.min_chunk_size,
        )
        self.metadata_extractor = MetadataExtractor()
    
    def process(
        self,
        file_path: Optional[Union[str, Path]] = None,
        content: Optional[bytes] = None,
        filename: Optional[str] = None,
        tenant_id: str = "",
        collection_id: str = "",
        extra_metadata: Optional[dict] = None,
        skip_cleaning: bool = False,
        skip_chunking: bool = False,
    ) -> ProcessingResult:
        """
        处理文档
        
        Args:
            file_path: 文件路径
            content: 文件内容（字节）
            filename: 文件名
            tenant_id: 租户ID
            collection_id: 集合ID
            extra_metadata: 额外元数据
            skip_cleaning: 跳过清洗步骤
            skip_chunking: 跳过切分步骤
            
        Returns:
            处理结果
        """
        import time
        start_time = time.time()
        
        result = ProcessingResult()
        
        try:
            # Step 1: 格式检测
            result.status = ProcessingStatus.DETECTING
            result.file_format = self.detector.detect(file_path, content, filename)
            
            if not result.file_format.is_supported:
                result.status = ProcessingStatus.FAILED
                result.errors.append(
                    f"Unsupported file format: {result.file_format.value}"
                )
                return result
            
            logger.info(f"Detected format: {result.file_format.value}")
            
            # Step 2: 内容提取
            result.status = ProcessingStatus.EXTRACTING
            extracted = self.extractor.extract(
                file_path=file_path,
                content=content,
                filename=filename,
                file_format=result.file_format,
            )
            
            if extracted.has_errors:
                result.errors.extend(extracted.errors)
            
            result.raw_text = extracted.text
            
            if not result.raw_text.strip():
                result.status = ProcessingStatus.FAILED
                result.errors.append("No text content extracted from document")
                return result
            
            logger.info(f"Extracted {len(result.raw_text)} characters")
            
            # Step 3: 文本清洗
            if not skip_cleaning:
                result.status = ProcessingStatus.CLEANING
                result.cleaned_text = self.cleaner.clean(result.raw_text)
                logger.info(f"Cleaned text: {len(result.cleaned_text)} characters")
            else:
                result.cleaned_text = result.raw_text
            
            # Step 4: 语义切分
            if not skip_chunking:
                result.status = ProcessingStatus.CHUNKING
                
                # 如果有页码信息，按页切分
                pages = self._extract_pages(extracted)
                if pages:
                    result.chunks = self.chunker.chunk_with_pages(pages)
                else:
                    result.chunks = self.chunker.chunk(result.cleaned_text)
                
                logger.info(f"Created {len(result.chunks)} chunks")
            
            # Step 5: 元数据提取
            if self.config.auto_extract_metadata:
                result.status = ProcessingStatus.METADATA
                
                # 获取文档特定元数据
                doc_metadata = {}
                if result.file_format == FileFormat.PDF:
                    doc_metadata = self.metadata_extractor.extract_from_pdf(
                        file_path, content
                    )
                elif result.file_format == FileFormat.DOCX:
                    doc_metadata = self.metadata_extractor.extract_from_docx(
                        file_path, content
                    )
                
                # 合并元数据
                combined_metadata = {**(extra_metadata or {}), **doc_metadata}
                
                result.metadata = self.metadata_extractor.extract(
                    file_path=file_path,
                    content=content,
                    text=result.cleaned_text,
                    filename=filename,
                    file_type=result.file_format.value,
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    extra_metadata=combined_metadata,
                )
                
                # 更新元数据中的页数
                if extracted.page_count:
                    result.metadata.page_count = extracted.page_count
            
            result.status = ProcessingStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            result.status = ProcessingStatus.FAILED
            result.errors.append(str(e))
        
        finally:
            result.processing_time = time.time() - start_time
        
        return result
    
    def process_batch(
        self,
        files: list[dict[str, Any]],
        tenant_id: str = "",
        collection_id: str = "",
        **kwargs,
    ) -> list[ProcessingResult]:
        """
        批量处理文档
        
        Args:
            files: 文件列表，每项包含 file_path 或 content/filename
            tenant_id: 租户ID
            collection_id: 集合ID
            **kwargs: 传递给 process 的其他参数
            
        Returns:
            处理结果列表
        """
        results = []
        
        for file_info in files:
            result = self.process(
                file_path=file_info.get("file_path"),
                content=file_info.get("content"),
                filename=file_info.get("filename"),
                tenant_id=tenant_id,
                collection_id=collection_id,
                extra_metadata=file_info.get("metadata"),
                **kwargs,
            )
            results.append(result)
        
        return results
    
    def _extract_pages(
        self,
        extracted: ExtractedContent,
    ) -> list[tuple[str, int]]:
        """
        从提取的内容中分离各页
        
        Args:
            extracted: 提取的内容
            
        Returns:
            (文本, 页码) 元组列表
        """
        pages: dict[int, list[str]] = {}
        
        for elem in extracted.elements:
            if elem.page_number is not None:
                if elem.page_number not in pages:
                    pages[elem.page_number] = []
                pages[elem.page_number].append(elem.content)
        
        if not pages:
            return []
        
        result = []
        for page_num in sorted(pages.keys()):
            page_text = "\n".join(pages[page_num])
            # 清洗每页文本
            cleaned_page = self.cleaner.clean(page_text)
            if cleaned_page.strip():
                result.append((cleaned_page, page_num))
        
        return result
    
    @classmethod
    def from_config(cls, config: dict) -> "DocumentPipeline":
        """
        从配置字典创建流水线
        
        Args:
            config: 配置字典
            
        Returns:
            DocumentPipeline 实例
        """
        pipeline_config = PipelineConfig.from_dict(config)
        return cls(pipeline_config)
