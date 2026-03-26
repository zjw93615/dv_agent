"""
意图路由器
将识别的意图映射到对应的 Agent
"""

from typing import Any, Optional
from pathlib import Path

import yaml

from .models import (
    IntentType,
    IntentResult,
    AgentRoute,
)
from .recognizer import IntentRecognizer, get_intent_recognizer
from ..config.logging import get_logger

logger = get_logger(__name__)


class IntentRouter:
    """
    意图路由器
    
    功能：
    - 意图到 Agent 的映射
    - 支持优先级和条件路由
    - 动态路由配置
    """
    
    def __init__(
        self,
        recognizer: Optional[IntentRecognizer] = None,
    ):
        self.recognizer = recognizer or get_intent_recognizer()
        
        # 路由表
        self._routes: dict[str, list[AgentRoute]] = {}
        
        # 默认 Agent
        self._default_agent: Optional[str] = None
        
        # 加载默认路由
        self._load_default_routes()
    
    def _load_default_routes(self) -> None:
        """加载默认路由配置"""
        # 默认路由：意图类型 -> Agent ID
        default_routes = [
            # 搜索任务 -> search_agent
            AgentRoute(intent_type=IntentType.SEARCH, agent_id="search_agent"),
            
            # 代码任务 -> code_agent
            AgentRoute(intent_type=IntentType.CODE, agent_id="code_agent"),
            
            # 文件操作 -> file_agent
            AgentRoute(intent_type=IntentType.FILE, agent_id="file_agent"),
            
            # 数据处理 -> data_agent
            AgentRoute(intent_type=IntentType.DATA, agent_id="data_agent"),
            
            # 创作/总结/翻译 -> creative_agent
            AgentRoute(intent_type=IntentType.CREATIVE, agent_id="creative_agent"),
            AgentRoute(intent_type=IntentType.SUMMARY, agent_id="creative_agent"),
            AgentRoute(intent_type=IntentType.TRANSLATE, agent_id="creative_agent"),
            
            # 通用查询 -> orchestrator
            AgentRoute(intent_type=IntentType.QUERY, agent_id="orchestrator"),
            AgentRoute(intent_type=IntentType.KNOWLEDGE, agent_id="orchestrator"),
            AgentRoute(intent_type=IntentType.TASK, agent_id="orchestrator"),
            
            # 对话控制 -> chat_agent
            AgentRoute(intent_type=IntentType.CHAT, agent_id="chat_agent"),
            AgentRoute(intent_type=IntentType.GREETING, agent_id="chat_agent"),
            AgentRoute(intent_type=IntentType.FAREWELL, agent_id="chat_agent"),
            AgentRoute(intent_type=IntentType.CLARIFY, agent_id="chat_agent"),
            
            # 系统控制 -> system_agent
            AgentRoute(intent_type=IntentType.COMMAND, agent_id="system_agent"),
            AgentRoute(intent_type=IntentType.SETTINGS, agent_id="system_agent"),
            AgentRoute(intent_type=IntentType.HELP, agent_id="system_agent"),
            AgentRoute(intent_type=IntentType.CANCEL, agent_id="system_agent"),
        ]
        
        for route in default_routes:
            self.add_route(route)
        
        # 设置默认 Agent
        self._default_agent = "orchestrator"
    
    def add_route(self, route: AgentRoute) -> None:
        """添加路由"""
        intent_key = route.intent_type if isinstance(route.intent_type, str) else route.intent_type.value
        
        if intent_key not in self._routes:
            self._routes[intent_key] = []
        
        self._routes[intent_key].append(route)
        
        # 按置信度要求排序（高要求优先）
        self._routes[intent_key].sort(
            key=lambda r: r.min_confidence,
            reverse=True,
        )
    
    def remove_route(
        self,
        intent_type: IntentType,
        agent_id: str,
    ) -> bool:
        """移除路由"""
        intent_key = intent_type.value
        
        if intent_key not in self._routes:
            return False
        
        original_len = len(self._routes[intent_key])
        self._routes[intent_key] = [
            r for r in self._routes[intent_key]
            if r.agent_id != agent_id
        ]
        
        return len(self._routes[intent_key]) < original_len
    
    async def route(
        self,
        text: str,
        context: Optional[dict] = None,
    ) -> tuple[str, IntentResult]:
        """
        路由到目标 Agent
        
        Args:
            text: 用户输入
            context: 上下文
            
        Returns:
            tuple[agent_id, intent_result]: 目标 Agent 和意图结果
        """
        # 识别意图
        intent_result = await self.recognizer.recognize(text, context)
        
        # 查找路由
        agent_id = self._find_agent(intent_result)
        
        logger.debug(
            f"Intent routed",
            intent=intent_result.intent_type.value,
            confidence=intent_result.confidence,
            agent=agent_id,
        )
        
        return agent_id, intent_result
    
    def _find_agent(self, intent_result: IntentResult) -> str:
        """查找匹配的 Agent"""
        intent_key = intent_result.intent_type.value
        
        # 1. 查找意图对应的路由
        routes = self._routes.get(intent_key, [])
        
        for route in routes:
            if not route.enabled:
                continue
            
            # 检查置信度
            if intent_result.confidence < route.min_confidence:
                continue
            
            # 检查必需实体
            if route.required_entities:
                entities = intent_result.primary_intent.entities
                if not all(e in entities for e in route.required_entities):
                    continue
            
            return route.agent_id
        
        # 2. 未知意图或无匹配 -> 默认 Agent
        return self._default_agent or "orchestrator"
    
    def route_direct(
        self,
        intent_result: IntentResult,
    ) -> str:
        """直接根据意图结果路由（不重新识别）"""
        return self._find_agent(intent_result)
    
    @property
    def default_agent(self) -> Optional[str]:
        """默认 Agent"""
        return self._default_agent
    
    @default_agent.setter
    def default_agent(self, agent_id: str) -> None:
        """设置默认 Agent"""
        self._default_agent = agent_id
    
    def get_routes(
        self,
        intent_type: Optional[IntentType] = None,
    ) -> list[AgentRoute]:
        """获取路由配置"""
        if intent_type:
            return self._routes.get(intent_type.value, [])
        
        # 返回所有路由
        all_routes = []
        for routes in self._routes.values():
            all_routes.extend(routes)
        return all_routes
    
    def load_config(self, config_path: str) -> None:
        """从配置文件加载路由"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Router config not found: {config_path}")
            return
        
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 清除现有路由
        self._routes.clear()
        
        # 加载路由
        routes_config = config.get("routes", [])
        for route_conf in routes_config:
            try:
                intent_type = IntentType(route_conf.get("intent_type"))
                route = AgentRoute(
                    intent_type=intent_type,
                    agent_id=route_conf.get("agent_id"),
                    min_confidence=route_conf.get("min_confidence", 0.5),
                    required_entities=route_conf.get("required_entities", []),
                    description=route_conf.get("description", ""),
                    enabled=route_conf.get("enabled", True),
                )
                self.add_route(route)
            except (KeyError, ValueError) as e:
                logger.warning(f"Invalid route config: {e}")
        
        # 默认 Agent
        self._default_agent = config.get("default_agent", "orchestrator")
        
        logger.info(
            f"Router config loaded",
            routes=sum(len(r) for r in self._routes.values()),
            default=self._default_agent,
        )
    
    def save_config(self, config_path: str) -> None:
        """保存路由配置"""
        routes_list = []
        for routes in self._routes.values():
            for route in routes:
                routes_list.append({
                    "intent_type": route.intent_type,
                    "agent_id": route.agent_id,
                    "min_confidence": route.min_confidence,
                    "required_entities": route.required_entities,
                    "description": route.description,
                    "enabled": route.enabled,
                })
        
        config = {
            "default_agent": self._default_agent,
            "routes": routes_list,
        }
        
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Router config saved to {config_path}")


# 全局路由器
_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """获取全局意图路由器"""
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router


async def route_to_agent(
    text: str,
    context: Optional[dict] = None,
) -> tuple[str, IntentResult]:
    """路由到 Agent（便捷函数）"""
    router = get_intent_router()
    return await router.route(text, context)
