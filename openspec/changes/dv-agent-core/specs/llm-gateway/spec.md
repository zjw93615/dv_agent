# Spec: llm-gateway

LLM统一适配层，支持多Provider接入、自动重试、降级路由、流式响应。

## ADDED Requirements

### Requirement: LLM Provider统一接口

系统SHALL提供统一的LLM调用接口，屏蔽不同Provider的API差异。

#### Scenario: OpenAI同步调用成功
- **WHEN** 调用`invoke()`方法并指定OpenAI provider
- **THEN** 系统返回标准化的`LLMResponse`对象，包含content、tool_calls、usage信息

#### Scenario: Ollama本地模型调用
- **WHEN** 调用`invoke()`方法并指定Ollama provider
- **THEN** 系统通过本地HTTP接口调用Ollama，返回标准化响应

#### Scenario: DeepSeek流式调用
- **WHEN** 调用`stream()`方法并指定DeepSeek provider
- **THEN** 系统返回`AsyncIterator[StreamChunk]`，支持逐token输出

---

### Requirement: 多Provider降级路由

系统SHALL支持Provider降级路由，当主Provider失败时自动切换到备用Provider。

#### Scenario: 主Provider失败自动降级
- **WHEN** OpenAI API调用失败（网络错误或超时）
- **THEN** 系统自动尝试DeepSeek provider
- **AND** 如果DeepSeek也失败，尝试Ollama本地模型
- **AND** 所有的降级行为被记录到日志

#### Scenario: 所有Provider失败
- **WHEN** 所有配置的Provider都调用失败
- **THEN** 系统抛出`AllProvidersFailedError`
- **AND** 错误信息包含各Provider的失败原因

---

### Requirement: 自动重试机制

系统SHALL对可重试错误实现指数退避重试策略。

#### Scenario: Rate Limit自动重试
- **WHEN** Provider返回429 Rate Limit错误
- **THEN** 系统等待exponential_base^retry_count秒后重试
- **AND** 最大重试次数不超过配置的max_retries（默认3次）
- **AND** 加入jitter随机抖动防止惊群效应

#### Scenario: 非可重试错误立即返回
- **WHEN** Provider返回400 Bad Request或401 Authentication Error
- **THEN** 系统立即抛出错误，不进行重试

---

### Requirement: Provider配置管理

系统SHALL支持 YAML 配置文件管理多个Provider。

#### Scenario: 加载Provider配置
- **WHEN** 系统启动时
- **THEN** 从`config/llm.yaml`加载Provider配置
- **AND** 验证必填字段（api_key、base_url等）
- **AND** 初始化各Provider的Adapter实例

#### Scenario: 运行时动态切换Provider
- **WHEN** 调用`set_default_provider("deepseek")`
- **THEN** 后续默认调用使用DeepSeek provider
- **AND** 不影响已指定provider的调用

---

### Requirement: Token计数与成本追踪

系统SHALL追踪每次LLM调用的token使用量和成本。

#### Scenario: 自动记录token使用
- **WHEN** LLM调用成功完成
- **THEN** 系统记录prompt_tokens、completion_tokens、total_tokens
- **AND** 根据Provider定价计算成本

#### Scenario: 本地模型token估算
- **WHEN** Provider未返回token计数（如部分Ollama模型）
- **THEN** 系统使用tiktoken本地估算token数量