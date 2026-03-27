-- RAG Documents Migration Script
-- 创建/更新 RAG 文档相关表结构
-- 
-- 运行方式:
--   psql -h localhost -U postgres -d dv_agent -f scripts/migrate_rag_documents.sql
--
-- 或者使用 Python:
--   python scripts/migrate_rag_documents.py

-- ==================== Documents Table ====================
-- 存储文档元数据（与代码中的字段名匹配）

CREATE TABLE IF NOT EXISTS documents (
    doc_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    collection_id VARCHAR(64),  -- 关联到 collections 表
    
    -- File information
    filename VARCHAR(512) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size BIGINT NOT NULL,
    content_hash VARCHAR(64),  -- MD5 hash for deduplication
    
    -- Document metadata
    title VARCHAR(512),
    description TEXT,
    
    -- Storage reference
    storage_path VARCHAR(1024) NOT NULL,
    
    -- Processing status: pending, processing, completed, failed
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    
    -- Additional metadata as JSON
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Soft delete
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for documents table
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_collection_id ON documents(collection_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_deleted_at ON documents(deleted_at) WHERE deleted_at IS NULL;

COMMENT ON TABLE documents IS 'RAG document metadata storage';
COMMENT ON COLUMN documents.doc_id IS 'Unique document identifier';
COMMENT ON COLUMN documents.collection_id IS 'Reference to collections table';


-- ==================== Document Chunks Table ====================
-- 存储文档切分后的文本块

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id VARCHAR(64) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL,
    
    -- Chunk information
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    
    -- Position in original document
    page_number INTEGER,
    start_offset INTEGER,
    end_offset INTEGER,
    
    -- Additional metadata as JSON
    metadata JSONB DEFAULT '{}',
    
    -- Vector IDs for cross-reference with Milvus
    dense_vector_id VARCHAR(64),
    sparse_vector_id VARCHAR(64),
    
    -- Full-text search vector
    content_tsv TSVECTOR,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for document_chunks table
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id ON document_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON document_chunks(doc_id, chunk_index);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON document_chunks USING GIN(content_tsv);

COMMENT ON TABLE document_chunks IS 'Document chunks for RAG retrieval';


-- ==================== Trigger for TSVECTOR Update ====================
-- 自动更新 content_tsv 字段

CREATE OR REPLACE FUNCTION update_chunk_tsv()
RETURNS TRIGGER AS $$
BEGIN
    -- 使用简单分词配置
    NEW.content_tsv := to_tsvector('simple', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_chunk_tsv_update ON document_chunks;
CREATE TRIGGER trigger_chunk_tsv_update
    BEFORE INSERT OR UPDATE OF content ON document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_chunk_tsv();


-- ==================== Trigger for Updated At ====================
-- 自动更新 documents.updated_at 字段

CREATE OR REPLACE FUNCTION update_documents_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents;
CREATE TRIGGER trigger_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_documents_updated_at();


-- ==================== Tenant Storage Stats View ====================
-- 租户存储统计视图

CREATE OR REPLACE VIEW tenant_storage_stats AS
SELECT 
    tenant_id,
    COUNT(*) AS document_count,
    COALESCE(SUM(file_size), 0) AS total_size_bytes,
    COALESCE(SUM(file_size), 0) / 1024 / 1024 AS total_size_mb,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
    COUNT(*) FILTER (WHERE status = 'processing') AS processing_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_count
FROM documents
WHERE deleted_at IS NULL
GROUP BY tenant_id;


-- ==================== Full-Text Search Function ====================
-- 全文搜索函数

CREATE OR REPLACE FUNCTION search_document_chunks(
    p_tenant_id VARCHAR(64),
    p_query TEXT,
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    chunk_id UUID,
    document_id VARCHAR(64),
    content TEXT,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id AS chunk_id,
        dc.doc_id AS document_id,
        dc.content,
        ts_rank(dc.content_tsv, plainto_tsquery('simple', p_query)) AS rank
    FROM document_chunks dc
    JOIN documents d ON dc.doc_id = d.doc_id
    WHERE dc.tenant_id = p_tenant_id
      AND d.deleted_at IS NULL
      AND dc.content_tsv @@ plainto_tsquery('simple', p_query)
    ORDER BY rank DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;


-- ==================== Print Success Message ====================
DO $$
BEGIN
    RAISE NOTICE '✅ RAG documents migration completed successfully!';
    RAISE NOTICE 'Tables created/updated: documents, document_chunks';
    RAISE NOTICE 'Views created: tenant_storage_stats';
    RAISE NOTICE 'Functions created: search_document_chunks, update_chunk_tsv, update_documents_updated_at';
END $$;
