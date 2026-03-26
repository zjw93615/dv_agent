"""
Application factory for DV-Agent.

Provides the main application bootstrap logic.
"""

import asyncio
import signal
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from .config.settings import Settings, get_settings
from .config.logging import setup_logging, get_logger
from .session.redis_client import RedisClient
from .session.manager import SessionManager
from .llm_gateway.gateway import LLMGateway
from .llm_gateway.openai_adapter import OpenAIAdapter
from .llm_gateway.deepseek_adapter import DeepSeekAdapter
from .llm_gateway.ollama_adapter import OllamaAdapter
from .tools.registry import ToolRegistry
from .tools.mcp_manager import MCPManager
from .tools.builtin_skills import CalculatorTool, DateTimeTool
from .intent.recognizer import IntentRecognizer
from .intent.router import IntentRouter
from .agents.orchestrator import Orchestrator
from .a2a.server import A2AServer


logger = get_logger(__name__)


class Application:
    """Main application container managing all components lifecycle."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize application with settings."""
        self.settings = settings or get_settings()
        self._components: Dict[str, Any] = {}
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        
        # Setup logging
        setup_logging(
            level=self.settings.logging.level,
            json_format=self.settings.logging.json_format,
        )
    
    @property
    def redis_client(self) -> RedisClient:
        """Get Redis client."""
        return self._components.get("redis_client")
    
    @property
    def session_manager(self) -> SessionManager:
        """Get session manager."""
        return self._components.get("session_manager")
    
    @property
    def llm_gateway(self) -> LLMGateway:
        """Get LLM gateway."""
        return self._components.get("llm_gateway")
    
    @property
    def tool_registry(self) -> ToolRegistry:
        """Get tool registry."""
        return self._components.get("tool_registry")
    
    @property
    def mcp_manager(self) -> MCPManager:
        """Get MCP manager."""
        return self._components.get("mcp_manager")
    
    @property
    def intent_recognizer(self) -> IntentRecognizer:
        """Get intent recognizer."""
        return self._components.get("intent_recognizer")
    
    @property
    def intent_router(self) -> IntentRouter:
        """Get intent router."""
        return self._components.get("intent_router")
    
    @property
    def orchestrator(self) -> Orchestrator:
        """Get orchestrator."""
        return self._components.get("orchestrator")
    
    @property
    def a2a_server(self) -> A2AServer:
        """Get A2A server."""
        return self._components.get("a2a_server")
    
    async def initialize(self) -> None:
        """Initialize all application components."""
        if self._initialized:
            logger.warning("Application already initialized")
            return
        
        logger.info(f"Initializing {self.settings.app_name} v{self.settings.app_version}")
        logger.info(f"Environment: {self.settings.environment}")
        
        try:
            # 1. Initialize Redis client
            await self._init_redis()
            
            # 2. Initialize Session Manager
            await self._init_session_manager()
            
            # 3. Initialize LLM Gateway
            await self._init_llm_gateway()
            
            # 4. Initialize Tools
            await self._init_tools()
            
            # 5. Initialize Intent Recognition
            await self._init_intent()
            
            # 6. Initialize Orchestrator
            await self._init_orchestrator()
            
            # 7. Initialize A2A Server
            await self._init_a2a_server()
            
            self._initialized = True
            logger.info("Application initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            await self.shutdown()
            raise
    
    async def _init_redis(self) -> None:
        """Initialize Redis client."""
        logger.info("Initializing Redis client...")
        
        from .session.redis_client import RedisSettings
        
        redis_settings = RedisSettings(
            redis_host=self.settings.redis.host,
            redis_port=self.settings.redis.port,
            redis_db=self.settings.redis.db,
            redis_password=self.settings.redis.password
        )
        
        self._components["redis_client"] = RedisClient(settings=redis_settings)
        await self.redis_client.connect()
        logger.info("Redis client initialized")
    
    async def _init_session_manager(self) -> None:
        """Initialize session manager."""
        logger.info("Initializing session manager...")
        self._components["session_manager"] = SessionManager(
            redis_client=self.redis_client,
            default_ttl=self.settings.agent.session_ttl
        )
        logger.info("Session manager initialized")
    
    async def _init_llm_gateway(self) -> None:
        """Initialize LLM gateway with providers."""
        logger.info("Initializing LLM gateway...")
        
        from .llm_gateway.models import ProviderConfig
        
        gateway = LLMGateway()
        llm_settings = self.settings.llm
        
        # Register OpenAI adapter if API key is available
        if llm_settings.openai_api_key:
            openai_config = ProviderConfig(
                type="openai",
                api_key=llm_settings.openai_api_key,
                base_url=llm_settings.openai_base_url,
                model=llm_settings.openai_model or "gpt-4",
            )
            await gateway.register_provider("openai", openai_config)
            logger.info("OpenAI adapter registered")
        
        # Register DeepSeek adapter if API key is available
        if llm_settings.deepseek_api_key:
            deepseek_config = ProviderConfig(
                type="deepseek",
                api_key=llm_settings.deepseek_api_key,
                base_url=llm_settings.deepseek_base_url,
                model=llm_settings.deepseek_model or "deepseek-chat",
            )
            await gateway.register_provider("deepseek", deepseek_config)
            logger.info("DeepSeek adapter registered")
        
        # Register Ollama adapter (always available for local deployment)
        ollama_config = ProviderConfig(
            type="ollama",
            base_url=llm_settings.ollama_base_url,
            model=llm_settings.ollama_model or "llama3.2",
        )
        await gateway.register_provider("ollama", ollama_config)
        logger.info("Ollama adapter registered")
        
        # Set default provider
        gateway._default_provider = llm_settings.primary_provider
        
        # Set fallback chain
        if llm_settings.fallback_providers:
            gateway._fallback_chain = llm_settings.fallback_providers
        
        self._components["llm_gateway"] = gateway
        logger.info("LLM gateway initialized")
    
    async def _init_tools(self) -> None:
        """Initialize tools and MCP manager."""
        logger.info("Initializing tools...")
        
        # Tool registry
        registry = ToolRegistry()
        
        # Register built-in skills
        if self.settings.tool.enable_calculator:
            registry.register(CalculatorTool())
            logger.info("Calculator tool registered")
        
        if self.settings.tool.enable_datetime:
            registry.register(DateTimeTool())
            logger.info("DateTime tool registered")
        
        self._components["tool_registry"] = registry
        
        # MCP Manager
        mcp_manager = MCPManager(tool_registry=registry)
        
        # Connect to configured MCP servers
        for server_config in self.settings.tool.mcp_servers:
            try:
                await mcp_manager.connect_server(
                    name=server_config.get("name"),
                    url=server_config.get("url"),
                    timeout=self.settings.tool.mcp_connection_timeout
                )
                logger.info(f"Connected to MCP server: {server_config.get('name')}")
            except Exception as e:
                logger.warning(f"Failed to connect MCP server {server_config.get('name')}: {e}")
        
        self._components["mcp_manager"] = mcp_manager
        logger.info("Tools initialized")
    
    async def _init_intent(self) -> None:
        """Initialize intent recognition."""
        logger.info("Initializing intent recognition...")
        
        from .intent.models import IntentConfig
        
        # Create intent config
        intent_config = IntentConfig(
            enable_embedding=self.settings.intent.use_embedding,
            enable_llm=self.settings.intent.use_llm_fallback,
        )
        
        # Intent recognizer
        recognizer = IntentRecognizer(
            config=intent_config,
            redis_client=self.redis_client,
            llm_gateway=self.llm_gateway,
        )
        self._components["intent_recognizer"] = recognizer
        
        # Intent router
        router = IntentRouter(recognizer=recognizer)
        self._components["intent_router"] = router
        
        logger.info("Intent recognition initialized")
    
    async def _init_orchestrator(self) -> None:
        """Initialize orchestrator."""
        logger.info("Initializing orchestrator...")
        
        from .agents.base_agent import AgentConfig
        
        config = AgentConfig(
            agent_id="orchestrator",
            name="Orchestrator",
            description="多 Agent 协调器",
            capabilities=["routing", "delegation", "aggregation"],
            max_steps=self.settings.agent.max_iterations,
        )
        
        orchestrator = Orchestrator(
            config=config,
            llm_gateway=self.llm_gateway,
            tool_registry=self.tool_registry,
            session_manager=self.session_manager,
            intent_router=self.intent_router,
        )
        
        self._components["orchestrator"] = orchestrator
        logger.info("Orchestrator initialized")
    
    async def _init_a2a_server(self) -> None:
        """Initialize A2A server."""
        logger.info("Initializing A2A server...")
        
        server = A2AServer(
            agent_id="dv-agent",
            agent_name=self.settings.app_name,
            description="DV-Agent A2A Server",
            version=self.settings.app_version,
        )
        
        # Store host/port for later use
        server._host = self.settings.a2a.host
        server._port = self.settings.a2a.port
        
        # Register orchestrator as task handler
        async def handle_task(request):
            """处理任务请求"""
            params = request.params
            if params and hasattr(params, 'input'):
                result = await self.orchestrator.process(
                    input_text=str(params.input),
                    session=None,
                    context=params.metadata if hasattr(params, 'metadata') else None
                )
                return {"output": result}
            return {"error": "Invalid task params"}
        
        server.register_handler("task/invoke", handle_task)
        
        self._components["a2a_server"] = server
        logger.info("A2A server initialized")
    
    async def run(self) -> None:
        """Run the application (blocking)."""
        if not self._initialized:
            await self.initialize()
        
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self._handle_shutdown())
                )
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass
        
        logger.info(f"Starting A2A server on {self.settings.a2a.host}:{self.settings.a2a.port}")
        
        try:
            # Start A2A server
            await self.a2a_server.run(
                host=self.settings.a2a.host,
                port=self.settings.a2a.port
            )
        except asyncio.CancelledError:
            logger.info("Application cancelled")
        finally:
            await self.shutdown()
    
    async def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
    
    async def shutdown(self) -> None:
        """Gracefully shutdown all components."""
        logger.info("Shutting down application...")
        
        # Shutdown in reverse order
        # Note: A2A server doesn't have a stop method, uvicorn handles graceful shutdown
        
        if self.mcp_manager:
            try:
                await self.mcp_manager.close()
            except Exception as e:
                logger.error(f"Error disconnecting MCP: {e}")
        
        if self.redis_client:
            try:
                await self.redis_client.disconnect()
            except Exception as e:
                logger.error(f"Error closing Redis: {e}")
        
        self._initialized = False
        logger.info("Application shutdown completed")
    
    async def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a user message through the orchestrator.
        
        Args:
            message: User input message
            session_id: Optional session ID for continuity
            metadata: Optional metadata
            
        Returns:
            Response dictionary with result
        """
        if not self._initialized:
            raise RuntimeError("Application not initialized")
        
        # Get or create session
        if session_id:
            session = await self.session_manager.get_session(session_id)
        else:
            session = await self.session_manager.create_session()
        
        # Process through orchestrator
        result = await self.orchestrator.process(
            input_text=message,
            session=session,
            context=metadata
        )
        
        return {
            "session_id": session.session_id,
            "response": result.response,
            "metadata": result.metadata
        }


@asynccontextmanager
async def create_application(settings: Optional[Settings] = None):
    """
    Async context manager for creating and managing application lifecycle.
    
    Usage:
        async with create_application() as app:
            result = await app.process_message("Hello")
    """
    app = Application(settings)
    try:
        await app.initialize()
        yield app
    finally:
        await app.shutdown()


def create_app(settings: Optional[Settings] = None) -> Application:
    """
    Factory function to create application instance.
    
    This is the main entry point for creating the application.
    """
    return Application(settings)
