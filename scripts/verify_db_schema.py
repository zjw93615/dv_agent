#!/usr/bin/env python3
"""
数据库架构验证脚本
验证PostgreSQL数据库中的表结构是否正确初始化

使用方法:
    python scripts/verify_db_schema.py
"""

import asyncio
import os
import sys
from typing import List, Dict

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


async def verify_schema():
    """验证数据库架构"""
    try:
        import asyncpg
    except ImportError:
        print("❌ asyncpg not installed. Run: pip install asyncpg")
        return False
    
    # 从环境变量读取配置
    pg_host = os.getenv("RAG_POSTGRES_HOST", "localhost")
    pg_port = int(os.getenv("RAG_POSTGRES_PORT", "5432"))
    pg_database = os.getenv("RAG_POSTGRES_DATABASE", "dv_agent")
    pg_user = os.getenv("RAG_POSTGRES_USER", "postgres")
    pg_password = os.getenv("RAG_POSTGRES_PASSWORD", "postgres123")
    
    connection_string = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
    
    print("=" * 60)
    print("🔍 数据库架构验证工具")
    print("=" * 60)
    print(f"📡 连接到: {pg_host}:{pg_port}/{pg_database}")
    print()
    
    try:
        conn = await asyncpg.connect(connection_string)
        print("✅ 数据库连接成功\n")
        
        # 定义需要检查的表
        required_tables = {
            # Memory System Tables
            "user_memories": "长期记忆存储表",
            "memory_relations": "记忆关系表",
            "user_memories_archive": "归档记忆表",
            "enterprise_knowledge": "企业知识库表",
            
            # RAG System Tables
            "collections": "文档集合表",
            "documents": "文档元数据表",
            "document_chunks": "文档分块表",
        }
        
        all_passed = True
        
        # 检查表是否存在
        print("📋 检查表结构:")
        print("-" * 60)
        
        for table_name, description in required_tables.items():
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = $1
                )
                """,
                table_name
            )
            
            if exists:
                # 获取列信息
                columns = await conn.fetch(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY ordinal_position
                    """,
                    table_name
                )
                
                print(f"✅ {table_name:25} - {description}")
                print(f"   列数: {len(columns)}")
                
                # 获取索引信息
                indexes = await conn.fetch(
                    """
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public' AND tablename = $1
                    """,
                    table_name
                )
                print(f"   索引数: {len(indexes)}")
            else:
                print(f"❌ {table_name:25} - {description} [缺失]")
                all_passed = False
            
            print()
        
        # 检查特定的约束和关系
        print("🔗 检查关键约束:")
        print("-" * 60)
        
        # 检查 collections 的 unique 约束
        unique_constraint = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints
                WHERE table_name = 'collections' 
                  AND constraint_type = 'UNIQUE'
                  AND constraint_name = 'unique_tenant_collection_name'
            )
            """
        )
        
        if unique_constraint:
            print("✅ collections.unique_tenant_collection_name 约束存在")
        else:
            print("⚠️  collections.unique_tenant_collection_name 约束缺失")
            all_passed = False
        
        # 检查 documents 的外键
        fk_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints
                WHERE table_name = 'document_chunks' 
                  AND constraint_type = 'FOREIGN KEY'
            )
            """
        )
        
        if fk_exists:
            print("✅ document_chunks 外键约束存在")
        else:
            print("⚠️  document_chunks 外键约束缺失")
        
        print()
        
        # 检查视图
        print("📊 检查视图:")
        print("-" * 60)
        
        view_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.views
                WHERE table_schema = 'public' AND table_name = 'tenant_storage_stats'
            )
            """
        )
        
        if view_exists:
            print("✅ tenant_storage_stats 视图存在")
        else:
            print("⚠️  tenant_storage_stats 视图缺失")
            all_passed = False
        
        print()
        
        # 检查函数
        print("⚙️  检查存储函数:")
        print("-" * 60)
        
        functions = await conn.fetch(
            """
            SELECT routine_name 
            FROM information_schema.routines
            WHERE routine_schema = 'public' AND routine_type = 'FUNCTION'
            """
        )
        
        function_names = {f['routine_name'] for f in functions}
        required_functions = [
            "update_updated_at_column",
            "archive_memory",
            "search_document_chunks",
            "update_chunk_tsv",
            "update_documents_updated_at",
        ]
        
        for func_name in required_functions:
            if func_name in function_names:
                print(f"✅ {func_name}")
            else:
                print(f"⚠️  {func_name} [缺失]")
        
        print()
        
        # 统计信息
        print("📈 数据统计:")
        print("-" * 60)
        
        if "collections" in [t for t, _ in required_tables.items()]:
            count = await conn.fetchval("SELECT COUNT(*) FROM collections")
            print(f"Collections: {count}")
        
        if "documents" in [t for t, _ in required_tables.items()]:
            count = await conn.fetchval("SELECT COUNT(*) FROM documents")
            print(f"Documents: {count}")
        
        if "document_chunks" in [t for t, _ in required_tables.items()]:
            count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
            print(f"Document Chunks: {count}")
        
        print()
        print("=" * 60)
        
        await conn.close()
        
        if all_passed:
            print("✅ 数据库架构验证通过！")
            return True
        else:
            print("⚠️  数据库架构存在问题，请检查初始化脚本")
            return False
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False


async def main():
    """主函数"""
    success = await verify_schema()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
