# Spec: orchestrator-agent

主控Agent，负责任务分解、Agent调度、结果聚合、Session管理。

## ADDED Requirements

### Requirement: 任务分解与调度

系统SHALL将复杂用户请求分解为子任务，并调度合适的Worker Agent执行。

#### Scenario: 单一任务直接路由
- **WHEN** 用户请求"今天天气怎么样"
- **THEN** 系统识别为简单问答任务
- **AND** 直接路由到Q&A Agent处理

#### Scenario: 复杂任务分解执行
- **WHEN** 用户请求"搜索Python异步编程资料并总结成文档"
- **THEN** 系统分解为子任务：搜索任务、总结任务、文档生成任务
- **AND** 按依赖顺序调度Search Agent执行
- **AND** 汇总结果返回用户

---

### Requirement: Agent路由决策

系统SHALL根据Intent Recognition结果选择合适的Worker Agent。

#### Scenario: 根据意图路由到知识检索
- **WHEN** Intent Recognition返回intent为"knowledge_query"
- **THEN** 系统路由请求到Knowledge Agent
- **AND** 传递解析后的slot参数

#### Scenario: 无匹配Agent时降级处理
- **WHEN** Intent Recognition返回的intent没有对应的Worker Agent
- **THEN** 系统路由到Q&A Agent作为fallback
- **AND** 记录警告日志

---

### Requirement: 结果聚合

系统SHALL聚合多个Worker Agent的执行结果。

#### Scenario: 单Agent结果直接返回
- **WHEN** 只调度了一个Agent执行
- **THEN** 系统直接返回该Agent的结果

#### Scenario: 多Agent结果合并
- **WHEN** 调度了多个Agent并行执行
- **THEN** 系统等待所有Agent完成
- **AND** 将各结果合并为统一响应格式
- **AND** 根据任务类型处理冲突或重复信息

---

### Requirement: ReAct决策循环

系统SHALL基于LangGraph实现ReAct（Reasoning-Acting-Observing）决策循环。

#### Scenario: ReAct循环正常完成
- **WHEN** Agent执行Thought-Action-Observation循环
- **THEN** 系统在达到Final Answer或最大迭代次数时停止
- **AND** 返回最终答案给用户

#### Scenario: ReAct循环中断检测
- **WHEN** 连续3次Observation相似度超过阈值（>0.9）
- **THEN** 系统判定为无进展循环
- **AND** 中断循环并返回当前最佳答案
- **AND** 记录警告日志

#### Scenario: 最大迭代次数保护
- **WHEN** ReAct循环达到max_iterations（默认10次）
- **THEN** 系统强制中断循环
- **AND** 返回截断响应与状态说明

---

### Requirement: 错误恢复与重试

系统SHALL处理Worker Agent执行失败的情况。

#### Scenario: Agent执行失败降级
- **WHEN** Search Agent执行超时或返回错误
- **THEN** 系统尝试使用Q&A Agent基于知识库回答
- **AND** 告知用户答案可能不完整

#### Scenario: 部分Agent失败继续执行
- **WHEN** 并行调度多个Agent，其中部分失败
- **THEN** 系统聚合成功的Agent结果
- **AND** 在响应中标注失败的Agent及原因

---

### Requirement: Session生命周期管理

系统SHALL管理Session的创建、挂起、恢复、关闭生命周期。

#### Scenario: 新用户创建Session
- **WHEN** 用户首次发起请求
- **THEN** 系统创建新Session并分配唯一session_id
- **AND** 将Session信息存储到Redis
- **AND** 返回session_id给客户端

#### Scenario: Session超时自动清理
- **WHEN** Session超过24小时无活动
- **THEN** 系统自动清理Session数据
- **AND** 用户下次请求创建新Session