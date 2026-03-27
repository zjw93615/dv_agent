"""
数据库迁移脚本
运行: python scripts/run_migration.py
"""

import asyncio
import os
from pathlib import Path


async def run_migration():
    """执行数据库迁移"""
    try:
        import asyncpg
    except ImportError:
        print("❌ asyncpg not installed. Run: pip install asyncpg")
        return
    
    # 从环境变量或默认值获取连接信息
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres123")
    db_name = os.getenv("POSTGRES_DB", "dv_agent")
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"🔗 Connecting to: {db_host}:{db_port}/{db_name}")
    
    try:
        conn = await asyncpg.connect(connection_string)
        print("✅ Connected to database")
        
        # 查找迁移文件
        migrations_dir = Path(__file__).parent.parent / "migrations"
        
        if not migrations_dir.exists():
            print(f"❌ Migrations directory not found: {migrations_dir}")
            return
        
        # 获取所有 SQL 文件并排序
        sql_files = sorted(migrations_dir.glob("*.sql"))
        
        if not sql_files:
            print("ℹ️ No migration files found")
            return
        
        print(f"📁 Found {len(sql_files)} migration file(s)")
        
        for sql_file in sql_files:
            print(f"\n📄 Running: {sql_file.name}")
            
            sql_content = sql_file.read_text(encoding="utf-8")
            
            try:
                await conn.execute(sql_content)
                print(f"   ✅ Success")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"   ⏭️ Skipped (already exists)")
                else:
                    print(f"   ❌ Error: {e}")
        
        await conn.close()
        print("\n🎉 Migration completed!")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Tips:")
        print("   - Make sure PostgreSQL is running")
        print("   - Check connection settings in .env file")
        print("   - For Docker: ensure port 5432 is exposed")


if __name__ == "__main__":
    asyncio.run(run_migration())
