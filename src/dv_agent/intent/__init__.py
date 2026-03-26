"""
意图识别模块
三层识别 + 路由
"""

from .models import (
    IntentType,
    IntentConfidence,
    Intent,
    IntentResult,
    IntentExample,
    IntentRule,
    AgentRoute,
    IntentConfig,
    DEFAULT_INTENT_EXAMPLES,
    DEFAULT_INTENT_RULES,
)
from .recognizer import (
    IntentRecognizer,
    get_intent_recognizer,
    recognize_intent,
)
from .router import (
    IntentRouter,
    get_intent_router,
    route_to_agent,
)

__all__ = [
    # Models
    "IntentType",
    "IntentConfidence",
    "Intent",
    "IntentResult",
    "IntentExample",
    "IntentRule",
    "AgentRoute",
    "IntentConfig",
    "DEFAULT_INTENT_EXAMPLES",
    "DEFAULT_INTENT_RULES",
    # Recognizer
    "IntentRecognizer",
    "get_intent_recognizer",
    "recognize_intent",
    # Router
    "IntentRouter",
    "get_intent_router",
    "route_to_agent",
]
