-- PostgreSQL Database Initialization Script
-- DV-Agent Memory System Schema

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text similarity

-- Memory Type Enum
CREATE TYPE memory_type AS ENUM ('fact', 'preference', 'event', 'entity');

-- Relation Type Enum
CREATE TYPE relation_type AS ENUM ('related', 'contradicts', 'supersedes');

-- ============================================
-- User Memories Table (Long-term Memory)
-- ============================================
CREATE TABLE IF NOT EXISTS user_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(64) NOT NULL,
    memory_type memory_type NOT NULL,
    content TEXT NOT NULL,
    
    -- Source tracking
    source_session VARCHAR(64),
    source_turn INTEGER,
    
    -- Scoring and lifecycle
    confidence FLOAT DEFAULT 1.0,
    importance FLOAT DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    decay_rate FLOAT DEFAULT 0.01,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE,
    expired_at TIMESTAMP WITH TIME ZONE,  -- Soft delete marker
    
    -- Extensible metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Full-text search vector
    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- Indexes for user_memories
CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX idx_user_memories_user_type ON user_memories(user_id, memory_type);
CREATE INDEX idx_user_memories_importance ON user_memories(importance DESC);
CREATE INDEX idx_user_memories_last_accessed ON user_memories(last_accessed DESC);
CREATE INDEX idx_user_memories_expired ON user_memories(expired_at) WHERE expired_at IS NOT NULL;
CREATE INDEX idx_user_memories_content_tsv ON user_memories USING GIN(content_tsv);
CREATE INDEX idx_user_memories_metadata ON user_memories USING GIN(metadata);

-- ============================================
-- Memory Relations Table
-- ============================================
CREATE TABLE IF NOT EXISTS memory_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
    relation_type relation_type NOT NULL,
    strength FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_relation UNIQUE (source_id, target_id, relation_type)
);

-- Indexes for memory_relations
CREATE INDEX idx_memory_relations_source ON memory_relations(source_id);
CREATE INDEX idx_memory_relations_target ON memory_relations(target_id);

-- ============================================
-- User Memories Archive Table
-- ============================================
CREATE TABLE IF NOT EXISTS user_memories_archive (
    id UUID PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    memory_type memory_type NOT NULL,
    content TEXT NOT NULL,
    
    -- Original metadata
    source_session VARCHAR(64),
    source_turn INTEGER,
    confidence FLOAT,
    importance FLOAT,
    access_count INTEGER,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    last_accessed TIMESTAMP WITH TIME ZONE,
    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Reason for archival
    archive_reason VARCHAR(64) DEFAULT 'low_importance',
    
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for archive
CREATE INDEX idx_user_memories_archive_user_id ON user_memories_archive(user_id);
CREATE INDEX idx_user_memories_archive_archived_at ON user_memories_archive(archived_at);

-- ============================================
-- Enterprise Knowledge Table (Shared)
-- ============================================
CREATE TABLE IF NOT EXISTS enterprise_knowledge (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(512) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(128),
    
    -- Access control
    dept_id VARCHAR(64),  -- NULL means accessible to all
    
    -- Versioning
    version INTEGER DEFAULT 1,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Full-text search
    content_tsv TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for enterprise_knowledge
CREATE INDEX idx_enterprise_knowledge_category ON enterprise_knowledge(category);
CREATE INDEX idx_enterprise_knowledge_dept ON enterprise_knowledge(dept_id);
CREATE INDEX idx_enterprise_knowledge_tsv ON enterprise_knowledge USING GIN(content_tsv);

-- ============================================
-- Helper Functions
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for user_memories
CREATE TRIGGER update_user_memories_updated_at
    BEFORE UPDATE ON user_memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for enterprise_knowledge
CREATE TRIGGER update_enterprise_knowledge_updated_at
    BEFORE UPDATE ON enterprise_knowledge
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to archive memory
CREATE OR REPLACE FUNCTION archive_memory(memory_id UUID, reason VARCHAR(64) DEFAULT 'low_importance')
RETURNS VOID AS $$
BEGIN
    -- Insert into archive
    INSERT INTO user_memories_archive (
        id, user_id, memory_type, content,
        source_session, source_turn, confidence, importance, access_count,
        created_at, updated_at, last_accessed, archive_reason, metadata
    )
    SELECT 
        id, user_id, memory_type, content,
        source_session, source_turn, confidence, importance, access_count,
        created_at, updated_at, last_accessed, reason, metadata
    FROM user_memories
    WHERE id = memory_id;
    
    -- Delete from active table
    DELETE FROM user_memories WHERE id = memory_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Comments
-- ============================================
COMMENT ON TABLE user_memories IS 'Long-term memory storage for user-specific knowledge';
COMMENT ON TABLE memory_relations IS 'Relationships between memories (related, contradicts, supersedes)';
COMMENT ON TABLE user_memories_archive IS 'Archived memories for compliance and potential recovery';
COMMENT ON TABLE enterprise_knowledge IS 'Shared enterprise knowledge base';
