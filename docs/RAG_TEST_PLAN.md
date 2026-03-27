# DV-Agent RAG 模块测试方案

> 版本: 1.0
> 创建时间: 2026-03-26
> 状态: 待执行

---

## 1. 测试环境准备

### 1.1 基础设施检查

```bash
# 检查 Docker 容器状态
docker compose -f docker-compose.rag.yml ps

# 应该看到以下服务运行中:
# - milvus-standalone (向量数据库)
# - minio (对象存储)
# - etcd (Milvus 配置存储)
# - postgres (已有, 元数据存储)
# - redis (已有, 缓存)
```

### 1.2 服务连接测试

```bash
# 测试 Milvus 连接 (默认端口 19530)
curl -s http://localhost:9091/healthz  # Milvus health check

# 测试 MinIO 连接 (默认端口 9000)
curl -s http://localhost:9000/minio/health/live

# 测试 PostgreSQL 连接
psql -h localhost -U postgres -d dv_agent -c "SELECT 1;"
```

### 1.3 环境变量配置

确保 `.env` 文件包含以下配置：

```env
# Milvus
RAG_MILVUS_HOST=localhost
RAG_MILVUS_PORT=19530

# MinIO
RAG_MINIO_ENDPOINT=localhost:9000
RAG_MINIO_ACCESS_KEY=minioadmin
RAG_MINIO_SECRET_KEY=minioadmin
RAG_MINIO_SECURE=false

# PostgreSQL (与主数据库共用)
RAG_POSTGRES_HOST=localhost
RAG_POSTGRES_PORT=5432
RAG_POSTGRES_DATABASE=dv_agent
RAG_POSTGRES_USER=postgres
RAG_POSTGRES_PASSWORD=postgres123

# Embedding 模型
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_DEVICE=cuda  # 或 cpu
```

---

## 2. 功能测试

### 2.1 文档上传测试

#### 测试用例 1: 上传 TXT 文件

```bash
# 创建测试文件
echo "这是一个测试文档。内容包含机器学习和深度学习的基础知识。
神经网络是深度学习的核心组件，由多层节点组成。
监督学习需要标注数据，无监督学习不需要标注。" > test_doc.txt

# 上传文档
curl -X POST "http://localhost:9080/rag/documents/upload" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -F "file=@test_doc.txt" \
  -F "tenant_id=test_tenant" \
  -F 'metadata={"source": "test", "author": "tester"}'
```

**预期结果**:
```json
{
  "document_id": "uuid-xxx",
  "filename": "test_doc.txt",
  "file_type": "txt",
  "file_size": 245,
  "chunk_count": 3,
  "status": "completed",
  "created_at": "2026-03-26T..."
}
```

#### 测试用例 2: 上传 PDF 文件

```bash
curl -X POST "http://localhost:9080/rag/documents/upload" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -F "file=@sample.pdf" \
  -F "tenant_id=test_tenant" \
  -F "collection_id=knowledge_base"
```

#### 测试用例 3: 上传 Markdown 文件

```bash
curl -X POST "http://localhost:9080/rag/documents/upload" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -F "file=@README.md" \
  -F "tenant_id=test_tenant"
```

#### 边界测试

| 场景 | 输入 | 预期结果 |
|------|------|----------|
| 空文件 | 0 字节文件 | 400 Bad Request |
| 超大文件 | >50MB | 413 File Too Large |
| 不支持的类型 | .exe 文件 | 415 Unsupported Type |
| 无 tenant_id | 缺少参数 | 422 Validation Error |

---

### 2.2 文档检索测试

#### 测试用例 1: 简单检索

```bash
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什么是神经网络",
    "top_k": 5
  }'
```

**预期结果**:
```json
{
  "query": "什么是神经网络",
  "results": [
    {
      "chunk_id": "xxx",
      "document_id": "xxx",
      "content": "神经网络是深度学习的核心组件...",
      "score": 0.85,
      "dense_score": 0.82,
      "sparse_score": 0.78,
      "rerank_score": 0.88
    }
  ],
  "total": 1,
  "latency_ms": 125.5,
  "from_cache": false
}
```

#### 测试用例 2: 混合检索模式

```bash
# Dense Only
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "机器学习算法", "mode": "dense"}'

# Sparse Only
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "机器学习算法", "mode": "sparse"}'

# BM25 Only
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "机器学习算法", "mode": "bm25"}'

# Hybrid (默认)
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "机器学习算法", "mode": "hybrid"}'
```

#### 测试用例 3: 带过滤器检索

```bash
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "深度学习",
    "collection_ids": ["knowledge_base"],
    "filters": {"source": "test"},
    "top_k": 10
  }'
```

#### 测试用例 4: 禁用重排序

```bash
curl -X POST "http://localhost:9080/rag/search?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "监督学习和无监督学习",
    "use_reranking": false,
    "use_query_expansion": false
  }'
```

---

### 2.3 文档管理测试

#### 测试用例 1: 获取文档详情

```bash
curl -X GET "http://localhost:9080/rag/documents/{document_id}?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

#### 测试用例 2: 列出文档

```bash
curl -X GET "http://localhost:9080/rag/documents?tenant_id=test_tenant&page=1&page_size=10" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

#### 测试用例 3: 删除文档

```bash
curl -X DELETE "http://localhost:9080/rag/documents/{document_id}?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

**验证**: 删除后再次搜索，不应返回该文档的内容

---

### 2.4 集合管理测试

#### 测试用例 1: 创建集合

```bash
curl -X POST "http://localhost:9080/rag/collections?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "技术文档",
    "description": "技术相关的文档集合"
  }'
```

#### 测试用例 2: 列出集合

```bash
curl -X GET "http://localhost:9080/rag/collections?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

#### 测试用例 3: 删除集合

```bash
curl -X DELETE "http://localhost:9080/rag/collections/{collection_id}?tenant_id=test_tenant" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

---

## 3. 集成测试

### 3.1 端到端测试流程

```python
# tests/test_rag_e2e.py

import pytest
import httpx
import asyncio

BASE_URL = "http://localhost:9080"
TENANT_ID = "test_tenant_e2e"

@pytest.fixture
async def auth_headers():
    """获取认证 header"""
    async with httpx.AsyncClient() as client:
        # 登录获取 token
        resp = await client.post(f"{BASE_URL}/auth/login", json={
            "username": "test_user",
            "password": "test_pass"
        })
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_full_rag_workflow(auth_headers):
    """完整 RAG 工作流测试"""
    async with httpx.AsyncClient() as client:
        # 1. 创建集合
        resp = await client.post(
            f"{BASE_URL}/rag/collections?tenant_id={TENANT_ID}",
            headers=auth_headers,
            json={"name": "E2E Test Collection"}
        )
        assert resp.status_code == 200
        collection_id = resp.json()["collection_id"]
        
        # 2. 上传文档
        files = {"file": ("test.txt", b"Python is a programming language.")}
        data = {"tenant_id": TENANT_ID, "collection_id": collection_id}
        resp = await client.post(
            f"{BASE_URL}/rag/documents/upload",
            headers=auth_headers,
            files=files,
            data=data
        )
        assert resp.status_code == 200
        document_id = resp.json()["document_id"]
        
        # 3. 等待处理完成
        await asyncio.sleep(2)
        
        # 4. 检索文档
        resp = await client.post(
            f"{BASE_URL}/rag/search?tenant_id={TENANT_ID}",
            headers=auth_headers,
            json={"query": "What is Python?", "top_k": 5}
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) > 0
        assert "Python" in results[0]["content"]
        
        # 5. 删除文档
        resp = await client.delete(
            f"{BASE_URL}/rag/documents/{document_id}?tenant_id={TENANT_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # 6. 删除集合
        resp = await client.delete(
            f"{BASE_URL}/rag/collections/{collection_id}?tenant_id={TENANT_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_performance(auth_headers):
    """检索性能测试"""
    async with httpx.AsyncClient() as client:
        # 执行多次检索，检查延迟
        latencies = []
        for i in range(10):
            resp = await client.post(
                f"{BASE_URL}/rag/search?tenant_id={TENANT_ID}",
                headers=auth_headers,
                json={"query": f"测试查询 {i}", "top_k": 10}
            )
            latencies.append(resp.json()["latency_ms"])
        
        avg_latency = sum(latencies) / len(latencies)
        print(f"Average latency: {avg_latency:.2f}ms")
        
        # P95 应该小于 500ms
        assert sorted(latencies)[8] < 500
```

### 3.2 与聊天集成测试

```bash
# 上传一个知识文档
curl -X POST "http://localhost:9080/rag/documents/upload" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@python_guide.md" \
  -F "tenant_id=user_xxx"

# 在聊天中提问相关问题
# 应该能够利用 RAG 检索到相关内容
```

---

## 4. 性能测试

### 4.1 批量上传测试

```python
# 批量上传 100 个文档
for i in range(100):
    with open(f"docs/doc_{i}.txt", "rb") as f:
        files = {"file": (f"doc_{i}.txt", f)}
        requests.post(
            f"{BASE_URL}/rag/documents/upload",
            headers=auth_headers,
            files=files,
            data={"tenant_id": TENANT_ID}
        )
```

**指标**:
- 每个文档平均处理时间 < 5s
- CPU 使用率 < 80%
- 内存使用稳定

### 4.2 并发检索测试

```python
import asyncio
import aiohttp

async def concurrent_search(n_requests=50):
    async with aiohttp.ClientSession() as session:
        tasks = [
            session.post(
                f"{BASE_URL}/rag/search?tenant_id={TENANT_ID}",
                json={"query": f"查询 {i}", "top_k": 10}
            )
            for i in range(n_requests)
        ]
        responses = await asyncio.gather(*tasks)
        
    # 统计结果
    latencies = [r.json()["latency_ms"] for r in responses]
    print(f"并发 {n_requests} 请求:")
    print(f"  平均延迟: {sum(latencies)/len(latencies):.2f}ms")
    print(f"  最大延迟: {max(latencies):.2f}ms")
    print(f"  P95 延迟: {sorted(latencies)[int(n_requests*0.95)]:.2f}ms")
```

**目标指标**:
- 50 并发 QPS > 20
- P95 延迟 < 500ms
- 错误率 < 1%

### 4.3 缓存效果测试

```bash
# 首次查询
curl -X POST "http://localhost:9080/rag/search?tenant_id=test" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"query": "机器学习"}'
# 记录 latency_ms 和 from_cache: false

# 相同查询第二次
curl -X POST "http://localhost:9080/rag/search?tenant_id=test" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"query": "机器学习"}'
# 预期 from_cache: true, latency_ms 显著降低
```

---

## 5. 错误处理测试

### 5.1 服务不可用

```bash
# 停止 Milvus
docker stop milvus-standalone

# 尝试检索
curl -X POST "http://localhost:9080/rag/search?tenant_id=test" \
  -d '{"query": "test"}'
# 预期: 503 Service Unavailable

# 恢复 Milvus
docker start milvus-standalone
```

### 5.2 无效输入

```bash
# 空查询
curl -X POST "http://localhost:9080/rag/search?tenant_id=test" \
  -d '{"query": ""}'
# 预期: 422 Validation Error

# 无效 tenant_id
curl -X POST "http://localhost:9080/rag/search" \
  -d '{"query": "test"}'
# 预期: 422 Validation Error (缺少 tenant_id)
```

---

## 6. 多租户隔离测试

```bash
# 租户 A 上传文档
curl -X POST "http://localhost:9080/rag/documents/upload" \
  -F "tenant_id=tenant_a" \
  -F "file=@secret_a.txt"

# 租户 B 搜索
curl -X POST "http://localhost:9080/rag/search?tenant_id=tenant_b" \
  -d '{"query": "secret"}'
# 预期: 不返回租户 A 的文档

# 租户 A 搜索
curl -X POST "http://localhost:9080/rag/search?tenant_id=tenant_a" \
  -d '{"query": "secret"}'
# 预期: 返回租户 A 的文档
```

---

## 7. 测试清单

### 前置检查 ✅

- [ ] Docker 服务启动 (Milvus, MinIO, etcd)
- [ ] PostgreSQL 数据库已创建 RAG 相关表
- [ ] 环境变量配置正确
- [ ] 后端服务正常启动 (`/health` 返回 200)

### 功能测试

- [ ] 文档上传 (TXT)
- [ ] 文档上传 (PDF)
- [ ] 文档上传 (Markdown)
- [ ] 文档上传 (边界情况)
- [ ] 简单检索
- [ ] 混合检索 (dense/sparse/bm25/hybrid)
- [ ] 带过滤器检索
- [ ] 文档详情获取
- [ ] 文档列表
- [ ] 文档删除
- [ ] 集合创建
- [ ] 集合列表
- [ ] 集合删除

### 集成测试

- [ ] 完整 RAG 工作流
- [ ] 与聊天模块集成

### 性能测试

- [ ] 批量上传
- [ ] 并发检索
- [ ] 缓存效果

### 错误处理

- [ ] 服务不可用
- [ ] 无效输入
- [ ] 多租户隔离

---

## 8. 执行命令汇总

```bash
# 1. 启动 RAG 依赖服务
docker compose -f docker-compose.rag.yml up -d

# 2. 启动后端服务
uvicorn dv_agent.server:app --host 0.0.0.0 --port 9080 --reload --reload-dir src

# 3. 运行集成测试
pytest tests/test_rag_e2e.py -v

# 4. 运行性能测试
pytest tests/test_rag_performance.py -v

# 5. 查看日志
docker compose -f docker-compose.rag.yml logs -f
```
