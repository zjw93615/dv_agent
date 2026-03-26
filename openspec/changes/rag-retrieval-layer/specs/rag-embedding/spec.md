## ADDED Requirements

### Requirement: BGE-M3 dense and sparse embedding
系统 SHALL 使用 BGE-M3 模型生成文本的稠密向量和稀疏向量。

#### Scenario: Generate dense embedding
- **WHEN** 系统接收一段文本
- **THEN** 系统返回 1024 维的稠密向量（归一化）

#### Scenario: Generate sparse embedding
- **WHEN** 系统接收一段文本
- **THEN** 系统返回稀疏向量，格式为 {token_id: weight} 的字典

#### Scenario: Batch embedding
- **WHEN** 系统接收一批文本（最多32条）
- **THEN** 系统批量处理并返回所有文本的向量，提升吞吐量

### Requirement: Embedding caching
系统 SHALL 缓存已计算的向量，避免重复计算。

#### Scenario: Cache hit
- **WHEN** 系统请求一个已缓存文本的向量
- **THEN** 系统直接返回缓存结果，不调用模型推理

#### Scenario: Cache miss
- **WHEN** 系统请求一个未缓存文本的向量
- **THEN** 系统计算向量后写入缓存，缓存 TTL 为 7 天

#### Scenario: Cache key collision prevention
- **WHEN** 两段不同的文本具有相同的 hash 前缀
- **THEN** 系统使用完整文本 hash 作为缓存键，避免碰撞

### Requirement: Model lazy loading
系统 SHALL 延迟加载向量模型，避免启动时阻塞。

#### Scenario: First embedding request
- **WHEN** 系统收到第一个向量化请求
- **THEN** 系统加载模型（预期耗时 5-10 秒），后续请求使用已加载模型

#### Scenario: Model not initialized
- **WHEN** 代码尝试在模型加载前直接访问模型
- **THEN** 系统抛出明确的异常，提示需要先调用 initialize()

### Requirement: GPU/CPU inference support
系统 SHALL 支持 GPU 和 CPU 两种推理模式。

#### Scenario: GPU available
- **WHEN** 系统检测到可用的 CUDA GPU
- **THEN** 系统使用 GPU 推理，启用 FP16 半精度加速

#### Scenario: GPU unavailable
- **WHEN** 系统未检测到可用的 GPU
- **THEN** 系统回退到 CPU 推理，并记录警告日志

### Requirement: Embedding normalization
系统 SHALL 对稠密向量进行 L2 归一化处理。

#### Scenario: Normalize dense vector
- **WHEN** 系统生成一个稠密向量
- **THEN** 向量的 L2 范数等于 1.0

#### Scenario: Handle empty text
- **WHEN** 系统接收空文本或纯空白文本
- **THEN** 系统返回全零向量，维度与正常向量一致

### Requirement: Sparse vector filtering
系统 SHALL 对稀疏向量进行低权重过滤以减少存储开销。

#### Scenario: Filter low weight tokens
- **WHEN** 系统生成稀疏向量
- **THEN** 系统仅保留权重大于阈值（默认0.01）的 token

#### Scenario: Top-K sparse features
- **WHEN** 配置了最大稀疏特征数（如 Top-128）
- **THEN** 系统仅保留权重最高的 K 个特征
