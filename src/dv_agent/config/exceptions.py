"""
通用异常类定义
定义dv-agent系统中使用的所有自定义异常
"""

from typing import Any, Optional


class DVAgentError(Exception):
    """dv-agent基础异常类"""
    
    def __init__(
        self, 
        message: str, 
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ==================== LLM Gateway 异常 ====================

class LLMError(DVAgentError):
    """LLM相关异常基类"""
    pass


class ProviderNotFoundError(LLMError):
    """Provider未找到"""
    pass


class ProviderConfigError(LLMError):
    """Provider配置错误"""
    pass


class RateLimitError(LLMError):
    """速率限制错误（可重试）"""
    pass


class AuthenticationError(LLMError):
    """认证错误（不可重试）"""
    pass


class InvalidRequestError(LLMError):
    """无效请求错误（不可重试）"""
    pass


class ContentPolicyViolation(LLMError):
    """内容策略违规（不可重试）"""
    pass


class AllProvidersFailedError(LLMError):
    """所有Provider都失败"""
    
    def __init__(self, failures: dict[str, str]):
        message = "All LLM providers failed"
        super().__init__(message, details={"failures": failures})
        self.failures = failures


class LLMTimeoutError(LLMError):
    """LLM调用超时"""
    pass


# ==================== A2A Protocol 异常 ====================

class A2AError(DVAgentError):
    """A2A协议相关异常基类"""
    pass


class AgentNotFoundError(A2AError):
    """Agent未找到"""
    pass


class UnsupportedCapabilityError(A2AError):
    """不支持的能力"""
    pass


class A2ATimeoutError(A2AError):
    """A2A调用超时"""
    pass


class A2AInvokeError(A2AError):
    """A2A调用失败"""
    pass


# ==================== Session 异常 ====================

class SessionError(DVAgentError):
    """Session相关异常基类"""
    pass


class SessionNotFoundError(SessionError):
    """Session未找到"""
    pass


class SessionExpiredError(SessionError):
    """Session已过期"""
    pass


class SessionStateError(SessionError):
    """Session状态错误"""
    pass


# ==================== Intent 异常 ====================

class IntentError(DVAgentError):
    """意图识别相关异常基类"""
    pass


class IntentRecognitionError(IntentError):
    """意图识别失败"""
    pass


class UnknownIntentError(IntentError):
    """无法识别意图"""
    pass


# ==================== Tool 异常 ====================

class ToolError(DVAgentError):
    """工具相关异常基类"""
    pass


class ToolNotFoundError(ToolError):
    """工具未找到"""
    pass


class ToolExecutionError(ToolError):
    """工具执行失败"""
    pass


class ToolValidationError(ToolError):
    """工具参数验证失败"""
    pass


class MCPConnectionError(ToolError):
    """MCP连接失败"""
    pass


class MCPInvokeError(ToolError):
    """MCP调用失败"""
    pass


# ==================== Agent 异常 ====================

class AgentError(DVAgentError):
    """Agent相关异常基类"""
    pass


class AgentExecutionError(AgentError):
    """Agent执行失败"""
    pass


class ReActLoopError(AgentError):
    """ReAct循环异常"""
    pass


class MaxIterationsReachedError(ReActLoopError):
    """达到最大迭代次数"""
    pass


class NoProgressError(ReActLoopError):
    """无进展循环检测"""
    pass


# ==================== Config 异常 ====================

class ConfigError(DVAgentError):
    """配置相关异常基类"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置文件未找到"""
    pass


class ConfigValidationError(ConfigError):
    """配置验证失败"""
    pass


# ==================== 别名 (兼容性) ====================
# 以下是为了兼容不同命名风格的别名

# LLM 异常别名
LLMProviderError = LLMError
LLMRateLimitError = RateLimitError
LLMAuthenticationError = AuthenticationError
LLMTimeoutError = LLMTimeoutError  # 保持原名
LLMInvalidRequestError = InvalidRequestError

# Config 异常别名
ConfigurationError = ConfigError

# ReAct 异常别名
ReActMaxStepsError = MaxIterationsReachedError
