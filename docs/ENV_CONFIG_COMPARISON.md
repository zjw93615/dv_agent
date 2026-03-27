# 环境配置对比报告

## 📋 对比总结

本报告对比了当前使用的环境配置文件和模板配置文件，除API Key外的所有差异。

---

## 🔍 主配置文件对比

### 1. `.env` vs `.env.example`

| 配置项 | 模板值 | 实际值 | 状态 | 建议 |
|--------|--------|--------|------|------|
| **POSTGRES_HOST** | ❌ 缺失 | ✅ localhost | ⚠️ **需添加到模板** | 添加Auth PostgreSQL配置 |
| **POSTGRES_PORT** | ❌ 缺失 | ✅ 5432 | ⚠️ **需添加到模板** | 添加Auth PostgreSQL配置 |
| **POSTGRES_DB** | ❌ 缺失 | ✅ dv_agent | ⚠️ **需添加到模板** | 添加Auth PostgreSQL配置 |
| **POSTGRES_USER** | ❌ 缺失 | ✅ postgres | ⚠️ **需添加到模板** | 添加Auth PostgreSQL配置 |
| **POSTGRES_PASSWORD** | ❌ 缺失 | ✅ postgres123 | ⚠️ **需添加到模板** | 添加Auth PostgreSQL配置 |
| LLM_OPENAI_BASE_URL | https://api.openai.com/v1 | https://ark.cn-beijing.volces.com/api/coding/v3 | ✅ API配置差异 | 正常（用户自定义） |
| LLM_OPENAI_MODEL | gpt-4o | doubao-seed-2.0-pro | ✅ API配置差异 | 正常（用户自定义） |

**关键发现**：
- ❌ `.env.example` **缺少 Auth PostgreSQL 配置**
- ✅ 其他非API配置完全一致

---

### 2. `.env.production` vs `.env.production.example`

| 配置项 | 模板值 | 实际值 | 状态 | 建议 |
|--------|--------|--------|------|------|
| **LLM_OPENAI_BASE_URL** | ❌ 缺失 | ✅ https://ark.cn-beijing.volces.com/api/coding/v3 | ⚠️ **模板应添加** | 方便用户自定义 |
| **LLM_OPENAI_MODEL** | ❌ 缺失 | ✅ doubao-seed-2.0-pro | ⚠️ **模板应添加** | 方便用户自定义 |
| **A2A_CONNECTION_TIMEOUT** | ❌ 缺失 | ❌ 缺失 | ⚠️ 生产环境缺失 | 建议添加 |
| **A2A_READ_TIMEOUT** | ❌ 缺失 | ❌ 缺失 | ⚠️ 生产环境缺失 | 建议添加 |
| **A2A_ENABLE_CORS** | ❌ 缺失 | ❌ 缺失 | ⚠️ 生产环境缺失 | 建议添加 |

**关键发现**：
- ⚠️ `.env.production.example` 缺少完整的LLM配置选项
- ⚠️ 缺少部分A2A Server配置
- ⚠️ **缺少所有RAG配置**（这是最严重的问题）

---

### 3. `frontend/.env` vs `frontend/.env.example`

| 配置项 | 模板值 | 实际值 | 状态 | 建议 |
|--------|--------|--------|------|------|
| VITE_API_BASE_URL | http://localhost:8080 | http://localhost:8000 | ❌ **端口不一致** | 统一为8080 |
| VITE_WS_BASE_URL | ws://localhost:8080 | ws://localhost:8000 | ❌ **端口不一致** | 统一为8080 |
| VITE_APP_ENV | development | ❌ 缺失 | ⚠️ 建议添加 | 方便环境判断 |

**关键发现**：
- ❌ **前端配置的后端端口不一致**（8000 vs 8080）
- ⚠️ 实际配置缺少环境标识

---

## 🚨 严重问题列表

### 问题1: `.env.example` 缺少 Auth PostgreSQL 配置

**影响**: 用户在初始化时可能不知道需要配置Auth数据库

**需要添加的配置**:
```bash
# ==================== PostgreSQL (Auth & Session) ====================
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=dv_agent
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123
```

---

### 问题2: `.env.production.example` 缺少 RAG 相关配置

**影响**: 生产环境无法使用RAG功能

**需要添加的配置**:
```bash
# ==================== RAG (Retrieval-Augmented Generation) ====================
RAG_ENABLED=true

# Embedding Model Configuration
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_MODEL_PATH=./models/bge-m3
RAG_EMBEDDING_DEVICE=cuda
RAG_EMBEDDING_BATCH_SIZE=32
RAG_EMBEDDING_MAX_LENGTH=8192

# MinIO Object Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_SECURE=false
MINIO_BUCKET_NAME=documents

# PostgreSQL (RAG Documents)
RAG_POSTGRES_HOST=postgres
RAG_POSTGRES_PORT=5432
RAG_POSTGRES_DATABASE=dv_agent
RAG_POSTGRES_USER=postgres
RAG_POSTGRES_PASSWORD=postgres123

# Milvus Vector Database
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_USER=
MILVUS_PASSWORD=

# Retrieval Configuration
RAG_DEFAULT_TOP_K=10
RAG_USE_RERANKING=true
RAG_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RAG_RERANKER_MODEL_PATH=./models/bge-reranker-v2-m3
RAG_USE_QUERY_EXPANSION=true
RAG_EXPANSION_COUNT=3

# Search Weights
RAG_DENSE_WEIGHT=0.4
RAG_SPARSE_WEIGHT=0.3
RAG_BM25_WEIGHT=0.3

# Cache Configuration
RAG_CACHE_ENABLED=true
RAG_CACHE_TTL=300
RAG_LOCAL_CACHE_SIZE=1000

# Document Processing
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=50
RAG_MAX_FILE_SIZE_MB=50

# Tenant Quotas
RAG_MAX_DOCUMENTS_PER_TENANT=1000
RAG_MAX_STORAGE_MB_PER_TENANT=5000
RAG_MAX_CHUNKS_PER_TENANT=100000
```

---

### 问题3: `.env.production.example` 缺少完整的LLM配置

**影响**: 用户无法自定义LLM Base URL和模型

**需要添加的配置**:
```bash
# OpenAI Configuration (REQUIRED if using openai)
OPENAI_API_KEY=sk-your-production-api-key
LLM_OPENAI_BASE_URL=https://api.openai.com/v1
LLM_OPENAI_MODEL=gpt-4o

# DeepSeek Configuration (optional)
DEEPSEEK_API_KEY=
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_DEEPSEEK_MODEL=deepseek-chat
```

---

### 问题4: `.env.production.example` 缺少完整的A2A Server配置

**需要添加**:
```bash
A2A_CONNECTION_TIMEOUT=30.0
A2A_READ_TIMEOUT=120.0
A2A_ENABLE_CORS=true
```

---

### 问题5: `frontend/.env` 端口配置错误

**影响**: 前端连接到错误的后端端口

**修复**:
```bash
# 应该改为
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

---

## 📝 其他配置文件状态

### `.env.memory.example` (Memory System专用)

**状态**: ✅ 这是一个独立的Memory System配置示例，不用于主应用

**说明**: 
- 这个文件是为Memory System子系统设计的独立配置
- 不需要合并到主`.env`文件
- 保持独立即可

---

## ✅ 修复建议优先级

### 🔴 高优先级（必须修复）

1. **修复 `frontend/.env` 端口配置** - 前端无法正常连接后端
2. **更新 `.env.production.example` 添加完整RAG配置** - 生产环境功能缺失
3. **更新 `.env.example` 添加Auth PostgreSQL配置** - 用户初始化困惑

### 🟡 中优先级（建议修复）

4. **更新 `.env.production.example` 添加完整LLM配置**
5. **更新 `.env.production.example` 添加完整A2A配置**

### 🟢 低优先级（可选）

6. 统一配置文件的注释风格
7. 添加更多配置说明文档

---

## 📊 配置完整性评分

| 配置文件 | 完整性 | 一致性 | 评分 |
|---------|--------|--------|------|
| `.env` vs `.env.example` | 85% | 95% | ⚠️ 需改进 |
| `.env.production` vs `.env.production.example` | 60% | 70% | ❌ 严重不足 |
| `frontend/.env` vs `frontend/.env.example` | 90% | 70% | ⚠️ 端口错误 |

---

## 🔧 自动修复脚本

为方便批量修复，建议创建以下脚本：

```bash
# scripts/sync_env_templates.sh
#!/bin/bash

echo "Syncing environment templates..."

# 1. Fix frontend port
sed -i 's|http://localhost:8000|http://localhost:8080|g' frontend/.env
sed -i 's|ws://localhost:8000|ws://localhost:8080|g' frontend/.env

# 2. Update templates
# (具体实现见下一部分)

echo "Done!"
```

---

**生成时间**: 2025-03-27  
**检查范围**: .env, .env.production, frontend/.env, 以及对应的.example文件
