## ADDED Requirements

### Requirement: Document upload and storage
系统 SHALL 支持文档上传并持久化存储原始文件。

#### Scenario: Upload single document
- **WHEN** 用户上传一个文档文件
- **THEN** 系统将文件存储到 MinIO/S3，并返回唯一的 document_id

#### Scenario: Upload with metadata
- **WHEN** 用户上传文档并附带元数据（标题、标签、描述）
- **THEN** 系统将元数据与文档关联存储

#### Scenario: Duplicate detection
- **WHEN** 用户上传的文档内容与已存在文档完全相同（MD5匹配）
- **THEN** 系统提示文档已存在，返回现有 document_id

### Requirement: Document chunk indexing
系统 SHALL 存储文档切分后的 chunks 及其向量索引。

#### Scenario: Store chunk content
- **WHEN** 文档处理流水线生成 chunks
- **THEN** 系统将每个 chunk 的文本内容存储到 PostgreSQL

#### Scenario: Store chunk embeddings
- **WHEN** 系统生成 chunk 的向量
- **THEN** 系统将稠密向量存储到 Milvus doc_embeddings Collection

#### Scenario: Store sparse embeddings
- **WHEN** 系统生成 chunk 的稀疏向量
- **THEN** 系统将稀疏向量存储到 Milvus doc_sparse_embeddings Collection

### Requirement: Document metadata management
系统 SHALL 管理文档及 chunk 的元数据。

#### Scenario: Store document metadata
- **WHEN** 系统存储一个文档
- **THEN** 系统在 PostgreSQL documents 表存储：id、tenant_id、filename、file_type、file_size、page_count、status、created_at、updated_at

#### Scenario: Store chunk metadata
- **WHEN** 系统存储一个 chunk
- **THEN** 系统在 PostgreSQL document_chunks 表存储：id、document_id、chunk_index、content、page_number、created_at

#### Scenario: Full-text search index
- **WHEN** 系统存储 chunk 内容
- **THEN** 系统同时更新 PostgreSQL 的 TSVECTOR 全文索引

### Requirement: Document lifecycle management
系统 SHALL 支持文档的增删改查操作。

#### Scenario: Get document by ID
- **WHEN** 用户请求特定 document_id 的文档
- **THEN** 系统返回文档元数据和下载链接

#### Scenario: List documents
- **WHEN** 用户请求文档列表
- **THEN** 系统返回分页的文档列表，支持按创建时间、文件类型排序

#### Scenario: Delete document
- **WHEN** 用户删除一个文档
- **THEN** 系统删除原始文件、所有 chunks、向量索引和元数据

#### Scenario: Update document
- **WHEN** 用户重新上传同一 document_id 的新版本
- **THEN** 系统删除旧 chunks 和向量，重新处理并存储新版本

### Requirement: Tenant isolation
系统 SHALL 实现租户级别的数据隔离。

#### Scenario: Tenant data isolation
- **WHEN** 租户 A 上传文档
- **THEN** 该文档及其 chunks/向量仅对租户 A 可见

#### Scenario: Cross-tenant prevention
- **WHEN** 租户 A 尝试访问租户 B 的文档
- **THEN** 系统返回 403 Forbidden 错误

### Requirement: Storage quota management
系统 SHALL 支持存储配额管理。

#### Scenario: Check quota before upload
- **WHEN** 用户上传文档
- **THEN** 系统检查租户已用存储空间是否超过配额

#### Scenario: Reject over-quota upload
- **WHEN** 上传将导致超过存储配额
- **THEN** 系统拒绝上传并返回明确的错误信息

### Requirement: Async document processing
系统 SHALL 支持异步处理大型文档。

#### Scenario: Async processing mode
- **WHEN** 用户上传大型文档（>10MB 或 >50页）
- **THEN** 系统立即返回 document_id 和 status=processing，后台异步处理

#### Scenario: Processing status query
- **WHEN** 用户查询文档处理状态
- **THEN** 系统返回：pending、processing、completed、failed 之一

#### Scenario: Processing completion callback
- **WHEN** 文档处理完成
- **THEN** 系统更新状态为 completed，并可选触发 webhook 通知
