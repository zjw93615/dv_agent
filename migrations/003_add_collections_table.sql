-- RAG Collections Table Migration
-- Run this SQL to add collections table

CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT unique_tenant_collection_name UNIQUE (tenant_id, name)
);

-- Index for fast tenant-based lookups
CREATE INDEX IF NOT EXISTS idx_collections_tenant_id ON collections(tenant_id);

-- Update documents table to use UUID for collection_id if needed
-- ALTER TABLE documents ALTER COLUMN collection_id TYPE UUID USING collection_id::uuid;

-- Comment
COMMENT ON TABLE collections IS 'RAG document collections for organizing documents';
COMMENT ON COLUMN collections.tenant_id IS 'Tenant/User ID for multi-tenancy';
COMMENT ON COLUMN collections.name IS 'Collection display name';
COMMENT ON COLUMN collections.metadata IS 'Additional metadata as JSON';
