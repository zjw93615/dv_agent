# Docker & WSL 数据库初始化指南

## 📋 问题说明

之前的Docker配置中，PostgreSQL初始化脚本只包含了Memory System的表结构，缺少RAG系统所需的`collections`, `documents`, `document_chunks`表。

现已修复，Docker Compose会自动挂载两个初始化脚本：
1. `01_init_memory.sql` - Memory System 表
2. `02_init_rag.sql` - RAG System 表

---

## 🔧 WSL 环境下的操作步骤

### 方法一：完全重建（推荐）

如果数据可以清空，这是最简单的方法：

```bash
# 1. 停止并删除所有容器和卷
cd /mnt/f/python/dv-agent
docker-compose -f docker-compose.rag.yml down -v

# 2. 重新启动（会自动执行初始化脚本）
docker-compose -f docker-compose.rag.yml up -d

# 3. 查看初始化日志
docker logs dv-agent-postgres

# 4. 验证数据库架构
python scripts/verify_db_schema.py
```

### 方法二：手动执行SQL（保留现有数据）

如果需要保留现有数据：

```bash
# 1. 进入 WSL
cd /mnt/f/python/dv-agent

# 2. 进入PostgreSQL容器
docker exec -it dv-agent-postgres psql -U postgres -d dv_agent

# 3. 在psql中执行（注意：在psql命令行中执行）
\i /docker-entrypoint-initdb.d/02_init_rag.sql

# 或者从宿主机直接执行
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < scripts/init_rag_postgres.sql

# 4. 验证表是否创建成功
docker exec -it dv-agent-postgres psql -U postgres -d dv_agent -c "\dt"
```

### 方法三：使用Docker卷备份恢复

如果需要先备份数据：

```bash
# 1. 备份现有数据
docker exec dv-agent-postgres pg_dump -U postgres -d dv_agent > backup_$(date +%Y%m%d).sql

# 2. 停止并删除卷
docker-compose -f docker-compose.rag.yml down -v

# 3. 重新启动
docker-compose -f docker-compose.rag.yml up -d

# 4. 等待初始化完成后恢复数据
docker exec -i dv-agent-postgres psql -U postgres -d dv_agent < backup_20250327.sql
```

---

## 🔍 验证数据库架构

运行验证脚本检查所有表是否正确创建：

```bash
# 确保环境变量已配置
export RAG_POSTGRES_HOST=localhost
export RAG_POSTGRES_PORT=5432
export RAG_POSTGRES_DATABASE=dv_agent
export RAG_POSTGRES_USER=postgres
export RAG_POSTGRES_PASSWORD=postgres123

# 运行验证脚本
python scripts/verify_db_schema.py
```

预期输出：
```
============================================================
🔍 数据库架构验证工具
============================================================
📡 连接到: localhost:5432/dv_agent

✅ 数据库连接成功

📋 检查表结构:
------------------------------------------------------------
✅ user_memories              - 长期记忆存储表
   列数: 14
   索引数: 7

✅ memory_relations           - 记忆关系表
   列数: 6
   索引数: 3

✅ collections                - 文档集合表
   列数: 7
   索引数: 2

✅ documents                  - 文档元数据表
   列数: 16
   索引数: 7

✅ document_chunks            - 文档分块表
   列数: 12
   索引数: 4

...

✅ 数据库架构验证通过！
```

---

## 🗂️ 表结构清单

### Memory System Tables
| 表名 | 描述 |
|------|------|
| `user_memories` | 用户长期记忆存储 |
| `memory_relations` | 记忆之间的关系（相关/矛盾/替代） |
| `user_memories_archive` | 归档的记忆（低重要性） |
| `enterprise_knowledge` | 企业级共享知识库 |

### RAG System Tables
| 表名 | 描述 |
|------|------|
| `collections` | 文档集合（用于组织文档） |
| `documents` | 文档元数据（文件名、类型、状态等） |
| `document_chunks` | 文档分块（用于向量检索） |

### Views & Functions
- **View**: `tenant_storage_stats` - 租户存储统计
- **Function**: `search_document_chunks()` - 全文搜索
- **Function**: `archive_memory()` - 归档记忆
- **Trigger**: 自动更新 `updated_at` 时间戳

---

## 🐛 常见问题

### Q1: 容器启动失败，提示"数据库已存在"

**A**: PostgreSQL的`/docker-entrypoint-initdb.d/`只在**首次创建数据卷**时执行。如果卷已存在，需要删除卷后重新创建：

```bash
docker volume rm dv-agent-postgres-data
docker-compose -f docker-compose.rag.yml up -d postgres
```

### Q2: 表已存在但结构不对

**A**: 使用 `DROP TABLE` 后重新执行初始化脚本：

```bash
docker exec -it dv-agent-postgres psql -U postgres -d dv_agent
# 在psql中执行
DROP TABLE IF EXISTS document_chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS collections CASCADE;
\i /docker-entrypoint-initdb.d/02_init_rag.sql
```

### Q3: 在WSL中找不到`/mnt/f/`路径

**A**: 确保Windows磁盘已正确挂载到WSL：

```bash
# 检查挂载点
ls /mnt/

# 如果没有f盘，可以手动挂载
sudo mkdir -p /mnt/f
sudo mount -t drvfs F: /mnt/f
```

### Q4: 验证脚本连接超时

**A**: 检查PostgreSQL容器是否在运行，端口是否映射：

```bash
# 检查容器状态
docker ps | grep postgres

# 检查端口
docker port dv-agent-postgres

# 测试连接
docker exec dv-agent-postgres pg_isready -U postgres
```

---

## 📝 修改内容总结

### 1. `docker-compose.rag.yml` 修改

**Before:**
```yaml
volumes:
  - ./scripts/init_postgres.sql:/docker-entrypoint-initdb.d/init.sql:ro
```

**After:**
```yaml
volumes:
  - ./scripts/init_postgres.sql:/docker-entrypoint-initdb.d/01_init_memory.sql:ro
  - ./scripts/init_rag_postgres.sql:/docker-entrypoint-initdb.d/02_init_rag.sql:ro
```

### 2. `docker-compose.yml` 修改

同样更新了主配置文件，确保生产环境也有完整的表结构。

### 3. 新增文件

- **`scripts/verify_db_schema.py`**: 自动化验证脚本
- **`docs/DATABASE_INIT_GUIDE.md`**: 本文档

---

## 🚀 快速开始

```bash
# 1. 克隆或进入项目目录
cd /mnt/f/python/dv-agent

# 2. 完全重建数据库
docker-compose -f docker-compose.rag.yml down -v
docker-compose -f docker-compose.rag.yml up -d

# 3. 等待初始化完成（约30秒）
docker logs -f dv-agent-postgres

# 4. 验证
python scripts/verify_db_schema.py

# 5. 如果验证通过，启动应用
# (根据你的具体运行方式)
```

---

## 📞 需要帮助？

如果遇到问题：
1. 查看PostgreSQL日志: `docker logs dv-agent-postgres`
2. 进入容器检查: `docker exec -it dv-agent-postgres bash`
3. 运行验证脚本: `python scripts/verify_db_schema.py`
4. 检查`.env`配置是否正确

---

**最后更新**: 2025-03-27  
**适用版本**: dv-agent v0.1.0+
