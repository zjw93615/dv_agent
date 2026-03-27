#!/usr/bin/env python
"""
RAG Documents Migration Script
创建 RAG 文档相关表结构

运行方式:
    python scripts/migrate_rag_documents.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed. Run: pip install asyncpg")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


async def run_migration():
    """执行数据库迁移"""
    
    # 获取数据库连接信息
    host = os.getenv('RAG_POSTGRES_HOST', os.getenv('POSTGRES_HOST', 'localhost'))
    port = int(os.getenv('RAG_POSTGRES_PORT', os.getenv('POSTGRES_PORT', '5432')))
    database = os.getenv('RAG_POSTGRES_DATABASE', os.getenv('POSTGRES_DB', 'dv_agent'))
    user = os.getenv('RAG_POSTGRES_USER', os.getenv('POSTGRES_USER', 'postgres'))
    password = os.getenv('RAG_POSTGRES_PASSWORD', os.getenv('POSTGRES_PASSWORD', 'postgres123'))
    
    print(f"📦 Connecting to PostgreSQL: {host}:{port}/{database}")
    
    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    print("✅ Connected to PostgreSQL")
    
    try:
        # 检查 documents 表是否已存在
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'documents'
            )
        """)
        
        if exists:
            print("⚠️  documents table already exists")
            # 检查是否需要更新表结构
            columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'documents'
            """)
            column_names = [c['column_name'] for c in columns]
            
            if 'doc_id' not in column_names:
                print("⚠️  Table structure is different from expected")
                print("   Please manually migrate or drop the existing table")
                return
            else:
                print("✅ Table structure is correct")
        else:
            print("📝 Creating documents table...")
            
            # 创建 documents 表
            await conn.execute("""
                CREATE TABLE documents (
                    doc_id VARCHAR(64) PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    collection_id VARCHAR(64),
                    
                    filename VARCHAR(512) NOT NULL,
                    file_type VARCHAR(32) NOT NULL,
                    file_size BIGINT NOT NULL,
                    content_hash VARCHAR(64),
                    
                    title VARCHAR(512),
                    description TEXT,
                    
                    storage_path VARCHAR(1024) NOT NULL,
                    
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    
                    metadata JSONB DEFAULT '{}',
                    
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP WITH TIME ZONE,
                    
                    deleted_at TIMESTAMP WITH TIME ZONE
                )
            """)
            print("✅ documents table created")
        
        # 创建索引
        print("📝 Creating indexes...")
        indexes = [
            ("idx_documents_tenant_id", "CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id)"),
            ("idx_documents_collection_id", "CREATE INDEX IF NOT EXISTS idx_documents_collection_id ON documents(collection_id)"),
            ("idx_documents_status", "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"),
            ("idx_documents_file_type", "CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type)"),
            ("idx_documents_created_at", "CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC)"),
            ("idx_documents_content_hash", "CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash) WHERE content_hash IS NOT NULL"),
        ]
        
        for name, sql in indexes:
            await conn.execute(sql)
        print("✅ Indexes created")
        
        # 检查 document_chunks 表
        chunks_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'document_chunks'
            )
        """)
        
        if not chunks_exists:
            print("📝 Creating document_chunks table...")
            await conn.execute("""
                CREATE TABLE document_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    doc_id VARCHAR(64) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                    tenant_id VARCHAR(64) NOT NULL,
                    
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    
                    page_number INTEGER,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    
                    metadata JSONB DEFAULT '{}',
                    
                    dense_vector_id VARCHAR(64),
                    sparse_vector_id VARCHAR(64),
                    
                    content_tsv TSVECTOR,
                    
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ document_chunks table created")
            
            # 创建 chunks 索引
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id ON document_chunks(tenant_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON document_chunks(doc_id, chunk_index)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON document_chunks USING GIN(content_tsv)")
            print("✅ document_chunks indexes created")
        else:
            print("✅ document_chunks table already exists")
        
        # 创建触发器函数
        print("📝 Creating trigger functions...")
        
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_chunk_tsv()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.content_tsv := to_tsvector('simple', COALESCE(NEW.content, ''));
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_documents_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at := CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        
        # 创建触发器
        await conn.execute("DROP TRIGGER IF EXISTS trigger_chunk_tsv_update ON document_chunks")
        await conn.execute("""
            CREATE TRIGGER trigger_chunk_tsv_update
                BEFORE INSERT OR UPDATE OF content ON document_chunks
                FOR EACH ROW
                EXECUTE FUNCTION update_chunk_tsv()
        """)
        
        await conn.execute("DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents")
        await conn.execute("""
            CREATE TRIGGER trigger_documents_updated_at
                BEFORE UPDATE ON documents
                FOR EACH ROW
                EXECUTE FUNCTION update_documents_updated_at()
        """)
        print("✅ Triggers created")
        
        # 打印最终状态
        print("\n" + "=" * 50)
        print("🎉 Migration completed successfully!")
        print("=" * 50)
        
        # 显示表结构
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('collections', 'documents', 'document_chunks')
            ORDER BY table_name
        """)
        
        print("\n📋 RAG Tables:")
        for t in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {t['table_name']}")
            print(f"   ✅ {t['table_name']}: {count} rows")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await conn.close()
        print("\n✅ Database connection closed")


if __name__ == "__main__":
    print("=" * 50)
    print("  RAG Documents Migration Script")
    print("=" * 50)
    print()
    
    asyncio.run(run_migration())
