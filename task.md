# DV-Agent 上下文管理改进计划

> 基于 HelloAgents、LangChain、AutoGen 的最佳实践分析
> 创建时间: 2026-03-26

---

## Phase 1: 基础改进（快速实现）

### 1.1 使用 tiktoken 精确计算 Token ✅
- [x] 安装 tiktoken 依赖
- [x] 创建 TokenCounter 类（带缓存）
- [x] 替换现有的字符估算逻辑
- [x] 添加 Token 统计日志

### 1.2 实现 HistoryManager 历史摘要压缩 ✅
- [x] 创建 HistoryManager 类
- [x] 实现轮次边界检测
- [x] 实现 compress() 方法（summary + 保留最近N轮）
- [x] 集成到 generate_llm_response（通过 ContextBuilder）

---

## Phase 2: 结构化上下文（中期）

### 2.1 引入 GSSC 流水线 ✅
- [x] 创建 ContextBuilder 类
- [x] 实现 Gather 阶段（收集候选信息）
- [x] 实现 Select 阶段（筛选与排序）
- [x] 实现 Structure 阶段（结构化模板）
- [x] 实现 Compress 阶段（压缩规范化）

### 2.2 实现 ContextPacket 优先级排序 ✅
- [x] 定义 ContextPacket 数据类
- [x] 实现相关性评分（关键词重叠）
- [x] 实现新近性评分（指数衰减）
- [x] 实现复合打分（0.7*相关性 + 0.3*新近性）

### 2.3 添加结构化模板 ✅
- [x] 定义模板格式：[Role] [Task] [State] [Evidence] [Context] [Output]
- [x] 实现模板渲染逻辑
- [x] 支持自定义模板配置
- [x] 预定义模板（general/code/analyst/creative/executor）

---

## Phase 3: 高级特性（长期）

### 3.1 工具输出截断器 ✅
- [x] 创建 ObservationTruncator 类
- [x] 支持多方向截断（head/tail/head_tail/smart）
- [x] 自动保存完整输出到文件
- [ ] 集成到工具调用流程（待后续集成）

### 3.2 向量检索增强
- [ ] 对接 RAG 模块的 Milvus
- [ ] 实现历史对话向量化
- [ ] 基于相似度检索相关历史
- [ ] 融合到上下文构建流程

### 3.3 实体记忆 ✅
- [x] 实现实体提取（用户偏好、关键信息）
- [x] 持久化实体存储（JSON 文件）
- [x] 在上下文中注入相关实体
- [x] 基于规则的自动实体提取

---

## 进度追踪

| 阶段 | 任务数 | 已完成 | 进度 |
|------|--------|--------|------|
| Phase 1 | 8 | 8 | 100% |
| Phase 2 | 12 | 12 | 100% |
| Phase 3 | 9 | 6 | 67% |
| **总计** | **29** | **26** | **90%** |

---

## 更新日志

- 2026-03-26: 创建改进计划
- 2026-03-26: ✅ 完成 Phase 1.1 - TokenCounter 实现
  - 创建 `src/dv_agent/context/token_counter.py`
  - 支持 tiktoken 精确计算 + 缓存机制
  - 集成到 `session/api.py` 的上下文构建流程
- 2026-03-26: ✅ 完成 Phase 1.2 - HistoryManager 实现
  - 创建 `src/dv_agent/context/history_manager.py`
  - 支持轮次边界检测
  - 支持历史压缩（summary + 保留最近N轮）
  - Token 预算管理
- 2026-03-26: ✅ 完成 Phase 2.1 & 2.2 - GSSC 流水线 & ContextPacket
  - 创建 `src/dv_agent/context/context_builder.py`
  - 实现完整 GSSC 四阶段流水线
  - 支持多类型上下文片段（系统提示、历史、RAG、工具输出等）
  - 相关性 + 新近性复合评分
  - Token 预算管理与自动截断
- 2026-03-26: ✅ 完成 Phase 3.1 - 工具输出截断器
  - 创建 `src/dv_agent/context/observation_truncator.py`
  - 支持 4 种截断策略：head/tail/head_tail/smart
  - 自动保存完整输出到 `.dv_agent/tool_outputs/`
  - 统计信息追踪
- 2026-03-26: ✅ 集成 ContextBuilder 到 generate_llm_response
  - 重构 `session/api.py` 使用 GSSC 流水线
  - Phase 1 全部完成
- 2026-03-26: ✅ 完成 Phase 2.3 - 结构化模板系统
  - 创建 `src/dv_agent/context/prompt_template.py`
  - 支持 [Role][Task][State][Evidence][Context][Output] 结构
  - 5 个预定义模板（general/code/analyst/creative/executor）
  - 模板变量替换和自定义配置
  - Phase 2 全部完成
- 2026-03-26: ✅ 完成 Phase 3.3 - 实体记忆系统
  - 创建 `src/dv_agent/context/entity_memory.py`
  - 7 种实体类型（用户信息/偏好/事实/项目/技能/关系/自定义）
  - 持久化到 `.dv_agent/entity_memory/`
  - 基于规则的自动实体提取
  - 关键词搜索和上下文格式化
