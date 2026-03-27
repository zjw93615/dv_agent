"""结构化模板系统

提供可配置的提示词模板，支持：
- 预定义模板（通用、代码、分析等）
- 模板变量替换
- 自定义模板配置

标准模板结构：
[Role] [Task] [State] [Evidence] [Context] [Output]

Author: DV-Agent Team
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TemplateType(str, Enum):
    """模板类型"""
    GENERAL = "general"           # 通用对话
    CODE_ASSISTANT = "code"       # 代码助手
    DATA_ANALYST = "analyst"      # 数据分析
    CREATIVE_WRITER = "creative"  # 创意写作
    TASK_EXECUTOR = "executor"    # 任务执行
    CUSTOM = "custom"             # 自定义


@dataclass
class TemplateSection:
    """模板段落"""
    name: str                     # 段落名称
    content: str                  # 段落内容
    required: bool = True         # 是否必需
    order: int = 0                # 排序权重


@dataclass
class PromptTemplate:
    """提示词模板
    
    Example:
        ```python
        template = PromptTemplate(
            name="code_assistant",
            role="你是一个专业的编程助手",
            task="帮助用户解决编程问题",
            constraints=["使用清晰的代码注释", "提供最佳实践建议"],
        )
        
        prompt = template.render(
            context="用户正在开发一个 Python Web 应用",
            evidence=["Flask 框架", "SQLAlchemy ORM"],
        )
        ```
    """
    name: str                                    # 模板名称
    type: TemplateType = TemplateType.GENERAL    # 模板类型
    
    # 核心段落
    role: str = ""                               # 角色定义
    task: str = ""                               # 任务描述
    state: str = ""                              # 当前状态
    evidence: list[str] = field(default_factory=list)  # 证据/参考
    context: str = ""                            # 上下文信息
    output_format: str = ""                      # 输出格式要求
    
    # 附加配置
    constraints: list[str] = field(default_factory=list)  # 约束条件
    examples: list[dict] = field(default_factory=list)    # 示例
    metadata: dict = field(default_factory=dict)          # 元数据
    
    def render(
        self,
        variables: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """渲染模板为最终提示词
        
        Args:
            variables: 变量字典
            **kwargs: 额外变量（覆盖 variables）
            
        Returns:
            渲染后的提示词
        """
        vars_dict = {**(variables or {}), **kwargs}
        
        sections = []
        
        # [Role] 角色定义
        if self.role:
            role_text = self._substitute(self.role, vars_dict)
            sections.append(f"[Role]\n{role_text}")
        
        # [Task] 任务描述
        if self.task:
            task_text = self._substitute(self.task, vars_dict)
            sections.append(f"[Task]\n{task_text}")
        
        # [State] 当前状态
        state_text = vars_dict.get("state", self.state)
        if state_text:
            state_text = self._substitute(state_text, vars_dict)
            sections.append(f"[Current State]\n{state_text}")
        
        # [Evidence] 证据/参考
        evidence_list = vars_dict.get("evidence", self.evidence)
        if evidence_list:
            if isinstance(evidence_list, str):
                evidence_list = [evidence_list]
            evidence_text = "\n".join(f"- {e}" for e in evidence_list)
            sections.append(f"[Evidence]\n{evidence_text}")
        
        # [Context] 上下文
        context_text = vars_dict.get("context", self.context)
        if context_text:
            context_text = self._substitute(context_text, vars_dict)
            sections.append(f"[Context]\n{context_text}")
        
        # [Constraints] 约束条件
        constraints = vars_dict.get("constraints", self.constraints)
        if constraints:
            if isinstance(constraints, str):
                constraints = [constraints]
            constraint_text = "\n".join(f"- {c}" for c in constraints)
            sections.append(f"[Constraints]\n{constraint_text}")
        
        # [Examples] 示例
        examples = vars_dict.get("examples", self.examples)
        if examples:
            example_texts = []
            for i, ex in enumerate(examples, 1):
                if isinstance(ex, dict):
                    inp = ex.get("input", "")
                    out = ex.get("output", "")
                    example_texts.append(f"Example {i}:\nInput: {inp}\nOutput: {out}")
                else:
                    example_texts.append(f"Example {i}: {ex}")
            sections.append(f"[Examples]\n" + "\n\n".join(example_texts))
        
        # [Output] 输出格式
        output_text = vars_dict.get("output_format", self.output_format)
        if output_text:
            output_text = self._substitute(output_text, vars_dict)
            sections.append(f"[Output Format]\n{output_text}")
        
        return "\n\n".join(sections)
    
    def _substitute(self, text: str, variables: dict) -> str:
        """替换模板变量
        
        支持 {variable_name} 格式
        """
        result = text
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "type": self.type.value,
            "role": self.role,
            "task": self.task,
            "state": self.state,
            "evidence": self.evidence,
            "context": self.context,
            "output_format": self.output_format,
            "constraints": self.constraints,
            "examples": self.examples,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PromptTemplate":
        """从字典创建"""
        template_type = data.get("type", "general")
        if isinstance(template_type, str):
            template_type = TemplateType(template_type)
        
        return cls(
            name=data.get("name", "custom"),
            type=template_type,
            role=data.get("role", ""),
            task=data.get("task", ""),
            state=data.get("state", ""),
            evidence=data.get("evidence", []),
            context=data.get("context", ""),
            output_format=data.get("output_format", ""),
            constraints=data.get("constraints", []),
            examples=data.get("examples", []),
            metadata=data.get("metadata", {}),
        )


# ===== 预定义模板 =====

TEMPLATES: dict[str, PromptTemplate] = {}


def _register_builtin_templates():
    """注册内置模板"""
    
    # 通用对话模板
    TEMPLATES["general"] = PromptTemplate(
        name="general",
        type=TemplateType.GENERAL,
        role="你是 DV-Agent，一个智能助手。",
        task="帮助用户解答问题、完成任务。",
        constraints=[
            "使用中文回复",
            "保持友好、专业的语气",
            "如果不确定答案，请诚实地说明",
        ],
        output_format="清晰、结构化的回答",
    )
    
    # 代码助手模板
    TEMPLATES["code"] = PromptTemplate(
        name="code",
        type=TemplateType.CODE_ASSISTANT,
        role="你是一个专业的编程助手，精通多种编程语言和框架。",
        task="帮助用户解决编程问题、审查代码、提供最佳实践建议。",
        constraints=[
            "代码需要有清晰的注释",
            "遵循语言的编码规范",
            "考虑边界情况和错误处理",
            "提供可运行的完整代码示例",
        ],
        output_format="""
使用 Markdown 格式：
1. 简要说明解决方案
2. 提供代码实现（使用代码块）
3. 解释关键点
4. 如有必要，提供使用示例
""".strip(),
    )
    
    # 数据分析模板
    TEMPLATES["analyst"] = PromptTemplate(
        name="analyst",
        type=TemplateType.DATA_ANALYST,
        role="你是一个数据分析专家，擅长数据处理、统计分析和可视化。",
        task="帮助用户分析数据、发现洞察、生成报告。",
        constraints=[
            "基于数据说话，避免主观臆断",
            "提供清晰的分析步骤",
            "使用适当的统计方法",
            "可视化建议应简洁明了",
        ],
        output_format="""
分析报告格式：
1. 数据概览
2. 分析方法
3. 关键发现
4. 结论与建议
""".strip(),
    )
    
    # 创意写作模板
    TEMPLATES["creative"] = PromptTemplate(
        name="creative",
        type=TemplateType.CREATIVE_WRITER,
        role="你是一个富有创意的写作助手，擅长各种文体的创作。",
        task="帮助用户进行创意写作、内容创作、文案优化。",
        constraints=[
            "保持创意和原创性",
            "注意文字的韵律和美感",
            "适应不同的文体风格",
            "尊重用户的创作意图",
        ],
        output_format="根据用户需求提供相应格式的创作内容",
    )
    
    # 任务执行模板
    TEMPLATES["executor"] = PromptTemplate(
        name="executor",
        type=TemplateType.TASK_EXECUTOR,
        role="你是一个任务执行代理，能够分解和执行复杂任务。",
        task="理解用户的任务需求，制定执行计划，逐步完成任务。",
        constraints=[
            "将复杂任务分解为可执行的步骤",
            "每步执行后报告进度",
            "遇到问题时及时反馈",
            "保持任务的可追溯性",
        ],
        output_format="""
任务执行格式：
1. 任务理解
2. 执行计划
3. 当前步骤
4. 执行结果
5. 下一步行动
""".strip(),
    )


# 初始化内置模板
_register_builtin_templates()


class TemplateManager:
    """模板管理器
    
    管理和提供提示词模板。
    
    Example:
        ```python
        manager = TemplateManager()
        
        # 获取内置模板
        code_template = manager.get("code")
        
        # 注册自定义模板
        manager.register(my_template)
        
        # 渲染模板
        prompt = manager.render("code", context="Python Web 开发")
        ```
    """
    
    def __init__(self):
        """初始化模板管理器"""
        self._templates: dict[str, PromptTemplate] = {}
        # 加载内置模板
        self._templates.update(TEMPLATES)
    
    def get(self, name: str) -> Optional[PromptTemplate]:
        """获取模板
        
        Args:
            name: 模板名称
            
        Returns:
            模板对象，不存在返回 None
        """
        return self._templates.get(name)
    
    def register(self, template: PromptTemplate) -> None:
        """注册模板
        
        Args:
            template: 模板对象
        """
        self._templates[template.name] = template
    
    def unregister(self, name: str) -> bool:
        """注销模板
        
        Args:
            name: 模板名称
            
        Returns:
            是否成功注销
        """
        if name in self._templates:
            del self._templates[name]
            return True
        return False
    
    def list_templates(self) -> list[str]:
        """列出所有模板名称"""
        return list(self._templates.keys())
    
    def render(
        self,
        name: str,
        variables: Optional[dict] = None,
        **kwargs,
    ) -> Optional[str]:
        """渲染指定模板
        
        Args:
            name: 模板名称
            variables: 变量字典
            **kwargs: 额外变量
            
        Returns:
            渲染后的提示词，模板不存在返回 None
        """
        template = self.get(name)
        if template is None:
            return None
        return template.render(variables, **kwargs)
    
    def create_template(
        self,
        name: str,
        role: str,
        task: str,
        **kwargs,
    ) -> PromptTemplate:
        """创建并注册模板
        
        Args:
            name: 模板名称
            role: 角色定义
            task: 任务描述
            **kwargs: 其他模板属性
            
        Returns:
            创建的模板对象
        """
        template = PromptTemplate(
            name=name,
            role=role,
            task=task,
            **kwargs,
        )
        self.register(template)
        return template


# ===== 便捷函数 =====

_default_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """获取默认模板管理器"""
    global _default_manager
    if _default_manager is None:
        _default_manager = TemplateManager()
    return _default_manager


def get_template(name: str) -> Optional[PromptTemplate]:
    """获取模板（便捷函数）"""
    return get_template_manager().get(name)


def render_template(name: str, **kwargs) -> Optional[str]:
    """渲染模板（便捷函数）"""
    return get_template_manager().render(name, **kwargs)
