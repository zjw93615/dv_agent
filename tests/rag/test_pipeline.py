"""
Document Pipeline Unit Tests
文档处理流水线单元测试
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import pipeline components
from dv_agent.rag.pipeline import (
    DocumentDetector,
    FileFormat,
    DocumentExtractor,
    ExtractedContent,
    ExtractedElement,
    TextChunker,
    Chunk,
    TextCleaner,
    CleanerConfig,
    MetadataExtractor,
    DocumentMetadata,
    DocumentPipeline,
    PipelineConfig,
    ProcessingResult,
    ProcessingStatus,
)


class TestDocumentDetector:
    """文档格式检测器测试"""
    
    def test_detect_by_extension_pdf(self):
        """测试 PDF 扩展名检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="test.pdf")
        assert result == FileFormat.PDF
    
    def test_detect_by_extension_docx(self):
        """测试 DOCX 扩展名检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="document.docx")
        assert result == FileFormat.DOCX
    
    def test_detect_by_extension_txt(self):
        """测试 TXT 扩展名检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="readme.txt")
        assert result == FileFormat.TXT
    
    def test_detect_by_extension_md(self):
        """测试 Markdown 扩展名检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="README.md")
        assert result == FileFormat.MD
    
    def test_detect_by_extension_html(self):
        """测试 HTML 扩展名检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="index.html")
        assert result == FileFormat.HTML
    
    def test_detect_by_content_pdf(self):
        """测试 PDF 内容检测"""
        detector = DocumentDetector()
        pdf_header = b"%PDF-1.4"
        result = detector.detect(content=pdf_header)
        assert result == FileFormat.PDF
    
    def test_detect_by_content_docx(self):
        """测试 DOCX 内容检测（ZIP 格式）"""
        detector = DocumentDetector()
        # DOCX/XLSX/PPTX 都是 ZIP 格式，需要文件名辅助判断
        zip_header = b"PK\x03\x04"
        result = detector.detect(content=zip_header, filename="test.docx")
        assert result == FileFormat.DOCX
    
    def test_detect_unknown_format(self):
        """测试未知格式检测"""
        detector = DocumentDetector()
        result = detector.detect(filename="unknown.xyz")
        assert result == FileFormat.UNKNOWN
    
    def test_file_format_is_supported(self):
        """测试格式支持判断"""
        assert FileFormat.PDF.is_supported
        assert FileFormat.DOCX.is_supported
        assert FileFormat.TXT.is_supported
        assert not FileFormat.UNKNOWN.is_supported
    
    def test_get_supported_formats(self):
        """测试获取支持的格式列表"""
        detector = DocumentDetector()
        formats = detector.get_supported_formats()
        assert "pdf" in formats
        assert "docx" in formats
        assert "txt" in formats


class TestTextChunker:
    """文本切分器测试"""
    
    def test_basic_chunking(self):
        """测试基本切分"""
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "这是一段测试文本。" * 20
        chunks = chunker.chunk(text)
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.content
    
    def test_chunk_with_overlap(self):
        """测试带重叠的切分"""
        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 100
        chunks = chunker.chunk(text)
        
        # 应该有多个块
        assert len(chunks) >= 2
    
    def test_short_text_single_chunk(self):
        """测试短文本单块"""
        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        text = "这是一段短文本。"
        chunks = chunker.chunk(text)
        
        assert len(chunks) == 1
        assert chunks[0].content == text.strip()
    
    def test_empty_text(self):
        """测试空文本"""
        chunker = TextChunker()
        chunks = chunker.chunk("")
        assert len(chunks) == 0
    
    def test_chunk_preserves_page_number(self):
        """测试页码保留"""
        chunker = TextChunker(chunk_size=100)
        chunks = chunker.chunk("测试内容", page_number=5)
        
        assert len(chunks) == 1
        assert chunks[0].page_number == 5
    
    def test_chunk_with_pages(self):
        """测试按页切分"""
        chunker = TextChunker(chunk_size=100)
        pages = [
            ("第一页的内容" * 10, 1),
            ("第二页的内容" * 10, 2),
        ]
        chunks = chunker.chunk_with_pages(pages)
        
        assert len(chunks) > 0
        # 验证页码信息保留
        page_numbers = set(c.page_number for c in chunks)
        assert 1 in page_numbers
        assert 2 in page_numbers
    
    def test_from_config(self):
        """测试从配置创建"""
        config = {
            "chunk_size": 200,
            "chunk_overlap": 30,
            "min_chunk_size": 10,
        }
        chunker = TextChunker.from_config(config)
        assert chunker.chunk_size == 200
        assert chunker.chunk_overlap == 30
        assert chunker.min_chunk_size == 10


class TestTextCleaner:
    """文本清洗器测试"""
    
    def test_remove_extra_whitespace(self):
        """测试去除多余空白"""
        cleaner = TextCleaner()
        text = "hello    world\n\n\n\ntest"
        result = cleaner.clean(text)
        
        assert "    " not in result
        assert "\n\n\n\n" not in result
    
    def test_normalize_unicode(self):
        """测试 Unicode 标准化"""
        cleaner = TextCleaner()
        text = "＆＋－"  # 全角字符
        result = cleaner.clean(text)
        
        # NFKC 标准化会转换这些字符
        assert result != text or "+" in result
    
    def test_fix_encoding(self):
        """测试编码修复"""
        cleaner = TextCleaner()
        text = "hello\ufeffworld\x00test\xa0space"
        result = cleaner.clean(text)
        
        assert "\ufeff" not in result
        assert "\x00" not in result
    
    def test_remove_urls(self):
        """测试移除 URL"""
        config = CleanerConfig(remove_urls=True)
        cleaner = TextCleaner(config)
        text = "访问 https://example.com 了解更多"
        result = cleaner.clean(text)
        
        assert "https://example.com" not in result
    
    def test_remove_emails(self):
        """测试移除邮箱"""
        config = CleanerConfig(remove_emails=True)
        cleaner = TextCleaner(config)
        text = "联系我们 contact@example.com"
        result = cleaner.clean(text)
        
        assert "contact@example.com" not in result
    
    def test_limit_repeat_chars(self):
        """测试限制重复字符"""
        cleaner = TextCleaner()
        text = "哈哈哈哈哈哈哈哈哈哈"  # 10个重复字符
        result = cleaner.clean(text)
        
        assert len(result) <= 5  # 默认最大5个
    
    def test_empty_text(self):
        """测试空文本"""
        cleaner = TextCleaner()
        assert cleaner.clean("") == ""
        assert cleaner.clean(None) == ""
    
    def test_from_config(self):
        """测试从配置创建"""
        config = {
            "remove_urls": True,
            "remove_emails": True,
            "max_repeat_chars": 3,
        }
        cleaner = TextCleaner.from_config(config)
        assert cleaner.config.remove_urls
        assert cleaner.config.remove_emails
        assert cleaner.config.max_repeat_chars == 3


class TestMetadataExtractor:
    """元数据提取器测试"""
    
    def test_basic_extraction(self):
        """测试基本元数据提取"""
        extractor = MetadataExtractor()
        metadata = extractor.extract(
            filename="test.pdf",
            text="这是测试内容",
            tenant_id="tenant1",
        )
        
        assert isinstance(metadata, DocumentMetadata)
        assert metadata.filename == "test.pdf"
        assert metadata.file_type == "pdf"
        assert metadata.tenant_id == "tenant1"
    
    def test_word_count(self):
        """测试字数统计"""
        extractor = MetadataExtractor()
        text = "Hello World 你好世界"
        metadata = extractor.extract(text=text)
        
        # 2 英文词 + 4 中文字
        assert metadata.word_count == 6
    
    def test_language_detection_chinese(self):
        """测试中文语言检测"""
        extractor = MetadataExtractor()
        text = "这是一段中文测试内容，用于测试语言检测功能。"
        metadata = extractor.extract(text=text)
        
        assert metadata.language in ["zh", "zh-cn", "zh-CN"]
    
    def test_language_detection_english(self):
        """测试英文语言检测"""
        extractor = MetadataExtractor()
        text = "This is an English test content for language detection."
        metadata = extractor.extract(text=text)
        
        assert metadata.language == "en"
    
    def test_title_extraction(self):
        """测试标题提取"""
        extractor = MetadataExtractor()
        text = "文档标题\n\n这是正文内容。"
        metadata = extractor.extract(text=text)
        
        assert metadata.title == "文档标题"
    
    def test_doc_id_generation(self):
        """测试文档ID生成"""
        extractor = MetadataExtractor()
        metadata = extractor.extract(
            content=b"test content",
            filename="test.pdf",
            tenant_id="tenant1",
        )
        
        assert metadata.doc_id
        assert len(metadata.doc_id) == 32  # MD5 hex
    
    def test_to_dict_and_from_dict(self):
        """测试字典序列化和反序列化"""
        extractor = MetadataExtractor()
        original = extractor.extract(
            filename="test.pdf",
            text="测试内容",
            tenant_id="tenant1",
        )
        
        # 序列化
        data = original.to_dict()
        assert isinstance(data, dict)
        
        # 反序列化
        restored = DocumentMetadata.from_dict(data)
        assert restored.filename == original.filename
        assert restored.tenant_id == original.tenant_id


class TestDocumentPipeline:
    """文档处理流水线测试"""
    
    def test_pipeline_config_from_dict(self):
        """测试从字典创建配置"""
        config = {
            "chunk_size": 300,
            "chunk_overlap": 30,
            "extraction_strategy": "fast",
        }
        pipeline_config = PipelineConfig.from_dict(config)
        
        assert pipeline_config.chunk_size == 300
        assert pipeline_config.chunk_overlap == 30
        assert pipeline_config.extraction_strategy == "fast"
    
    def test_pipeline_initialization(self):
        """测试流水线初始化"""
        pipeline = DocumentPipeline()
        
        assert pipeline.detector is not None
        assert pipeline.extractor is not None
        assert pipeline.cleaner is not None
        assert pipeline.chunker is not None
        assert pipeline.metadata_extractor is not None
    
    @patch.object(DocumentExtractor, 'extract')
    def test_process_text_file(self, mock_extract):
        """测试处理文本文件"""
        # Mock 提取结果
        mock_extract.return_value = ExtractedContent(
            elements=[
                ExtractedElement(
                    type="text",
                    content="这是一段测试文本内容，用于测试文档处理流水线。" * 5,
                )
            ]
        )
        
        pipeline = DocumentPipeline()
        result = pipeline.process(
            filename="test.txt",
            content=b"test content",
            tenant_id="tenant1",
        )
        
        assert result.success
        assert result.status == ProcessingStatus.COMPLETED
        assert result.file_format == FileFormat.TXT
        assert len(result.chunks) > 0
        assert result.metadata is not None
    
    def test_process_unsupported_format(self):
        """测试处理不支持的格式"""
        pipeline = DocumentPipeline()
        result = pipeline.process(filename="test.xyz")
        
        assert not result.success
        assert result.status == ProcessingStatus.FAILED
        assert len(result.errors) > 0
    
    def test_process_skip_cleaning(self):
        """测试跳过清洗步骤"""
        pipeline = DocumentPipeline()
        with patch.object(DocumentExtractor, 'extract') as mock_extract:
            mock_extract.return_value = ExtractedContent(
                elements=[
                    ExtractedElement(type="text", content="测试内容")
                ]
            )
            
            result = pipeline.process(
                filename="test.txt",
                content=b"test",
                skip_cleaning=True,
            )
            
            # 清洗后的文本应该与原文本相同
            assert result.cleaned_text == result.raw_text
    
    def test_process_skip_chunking(self):
        """测试跳过切分步骤"""
        pipeline = DocumentPipeline()
        with patch.object(DocumentExtractor, 'extract') as mock_extract:
            mock_extract.return_value = ExtractedContent(
                elements=[
                    ExtractedElement(type="text", content="测试内容")
                ]
            )
            
            result = pipeline.process(
                filename="test.txt",
                content=b"test",
                skip_chunking=True,
            )
            
            # 应该没有块
            assert len(result.chunks) == 0
    
    def test_processing_result_to_dict(self):
        """测试处理结果序列化"""
        result = ProcessingResult(
            status=ProcessingStatus.COMPLETED,
            chunks=[
                Chunk(index=0, content="chunk1", start_offset=0, end_offset=6),
                Chunk(index=1, content="chunk2", start_offset=6, end_offset=12),
            ],
            raw_text="test content",
            cleaned_text="test content",
            file_format=FileFormat.TXT,
        )
        
        data = result.to_dict()
        assert data["status"] == "completed"
        assert data["chunk_count"] == 2
        assert data["file_format"] == "txt"
    
    def test_from_config(self):
        """测试从配置创建流水线"""
        config = {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "use_hi_res": True,
        }
        pipeline = DocumentPipeline.from_config(config)
        
        assert pipeline.config.chunk_size == 200
        assert pipeline.config.chunk_overlap == 20
        assert pipeline.config.use_hi_res


class TestExtractedContent:
    """提取内容测试"""
    
    def test_text_property(self):
        """测试文本属性"""
        content = ExtractedContent(
            elements=[
                ExtractedElement(type="title", content="标题"),
                ExtractedElement(type="text", content="正文内容"),
                ExtractedElement(type="text", content="更多内容"),
            ]
        )
        
        text = content.text
        assert "标题" in text
        assert "正文内容" in text
        assert "更多内容" in text
    
    def test_page_count(self):
        """测试页数"""
        content = ExtractedContent(
            elements=[
                ExtractedElement(type="text", content="page1", page_number=1),
                ExtractedElement(type="text", content="page2", page_number=2),
                ExtractedElement(type="text", content="page3", page_number=3),
            ]
        )
        
        assert content.page_count == 3
    
    def test_has_errors(self):
        """测试错误检查"""
        content = ExtractedContent()
        assert not content.has_errors
        
        content.errors.append("An error occurred")
        assert content.has_errors


# pytest fixtures
@pytest.fixture
def sample_text():
    """示例文本"""
    return """
    文档标题
    
    这是第一段内容。它包含了一些测试文本。
    
    这是第二段内容。我们用它来测试切分功能。
    
    第三段包含一些特殊内容：
    - 列表项1
    - 列表项2
    - 列表项3
    """


@pytest.fixture
def pipeline():
    """测试流水线"""
    return DocumentPipeline(
        PipelineConfig(
            chunk_size=100,
            chunk_overlap=20,
        )
    )


def test_integration_text_processing(pipeline, sample_text):
    """集成测试：文本处理"""
    with patch.object(DocumentExtractor, 'extract') as mock_extract:
        mock_extract.return_value = ExtractedContent(
            elements=[
                ExtractedElement(type="text", content=sample_text)
            ]
        )
        
        result = pipeline.process(
            content=sample_text.encode(),
            filename="test.txt",
            tenant_id="test_tenant",
        )
        
        assert result.success
        assert result.chunk_count > 0
        assert result.metadata.tenant_id == "test_tenant"
