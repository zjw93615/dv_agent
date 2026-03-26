"""
A2A Server
基于 FastAPI 的 Agent-to-Agent 服务端
"""

import time
import asyncio
from typing import Any, Callable, Optional, Awaitable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    A2ARequest,
    A2AResponse,
    A2AError,
    A2AMethod,
    AgentInfo,
    AgentCapability,
    TaskInvokeParams,
    TaskResult,
    TaskState,
)
from ..config.logging import get_logger

logger = get_logger(__name__)

# 方法处理器类型
MethodHandler = Callable[[A2ARequest], Awaitable[Any]]


class A2AServer:
    """
    A2A 协议服务端
    
    提供标准的 JSON-RPC 2.0 端点供其他 Agent 调用
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        description: str = "",
        version: str = "1.0.0",
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.description = description
        self.version = version
        
        # FastAPI 应用
        self.app = FastAPI(
            title=f"A2A Server - {agent_name}",
            description=description,
            version=version,
        )
        
        # 方法处理器注册表
        self._handlers: dict[str, MethodHandler] = {}
        
        # 能力列表
        self._capabilities: list[AgentCapability] = []
        
        # 活跃任务
        self._active_tasks: dict[str, TaskResult] = {}
        self._max_concurrent_tasks = 10
        
        # 设置路由
        self._setup_routes()
        self._setup_middleware()
        self._register_builtin_handlers()
    
    def _setup_routes(self) -> None:
        """设置路由"""
        
        @self.app.post("/a2a")
        async def handle_a2a_request(request: Request) -> dict:
            """A2A JSON-RPC 端点"""
            start_time = time.time()
            
            try:
                body = await request.json()
                a2a_request = A2ARequest(**body)
            except Exception as e:
                return A2AResponse.failure(
                    request_id="unknown",
                    code=A2AError.PARSE_ERROR,
                    message=f"Parse error: {str(e)}",
                ).model_dump()
            
            try:
                response = await self._dispatch(a2a_request)
                response.latency_ms = (time.time() - start_time) * 1000
                return response.model_dump()
            except Exception as e:
                logger.exception(f"A2A request failed: {e}")
                return A2AResponse.failure(
                    request_id=a2a_request.id,
                    code=A2AError.INTERNAL_ERROR,
                    message=str(e),
                    source_agent=self.agent_id,
                ).model_dump()
        
        @self.app.get("/health")
        async def health_check() -> dict:
            """健康检查"""
            return {
                "status": "healthy",
                "agent_id": self.agent_id,
                "active_tasks": len(self._active_tasks),
            }
        
        @self.app.get("/info")
        async def agent_info() -> dict:
            """Agent 信息"""
            return self._get_agent_info().model_dump()
    
    def _setup_middleware(self) -> None:
        """设置中间件"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _register_builtin_handlers(self) -> None:
        """注册内置处理器"""
        
        @self.handler(A2AMethod.PING)
        async def handle_ping(request: A2ARequest) -> dict:
            return {"pong": True, "timestamp": time.time()}
        
        @self.handler(A2AMethod.INFO)
        async def handle_info(request: A2ARequest) -> dict:
            return self._get_agent_info().model_dump()
        
        @self.handler(A2AMethod.CAPABILITIES)
        async def handle_capabilities(request: A2ARequest) -> list:
            return [cap.model_dump() for cap in self._capabilities]
        
        @self.handler(A2AMethod.STATUS)
        async def handle_status(request: A2ARequest) -> dict:
            task_id = request.params.get("task_id") if request.params else None
            if not task_id:
                return {
                    "active_tasks": len(self._active_tasks),
                    "task_ids": list(self._active_tasks.keys()),
                }
            
            if task_id not in self._active_tasks:
                raise ValueError(f"Task not found: {task_id}")
            
            return self._active_tasks[task_id].model_dump()
        
        @self.handler(A2AMethod.CANCEL)
        async def handle_cancel(request: A2ARequest) -> dict:
            task_id = request.params.get("task_id") if request.params else None
            if not task_id or task_id not in self._active_tasks:
                raise ValueError(f"Task not found: {task_id}")
            
            task = self._active_tasks[task_id]
            if task.state == TaskState.RUNNING:
                task.state = TaskState.CANCELLED
            
            return {"cancelled": True, "task_id": task_id}
    
    async def _dispatch(self, request: A2ARequest) -> A2AResponse:
        """分发请求到对应处理器"""
        method = request.method
        
        if method not in self._handlers:
            return A2AResponse.failure(
                request_id=request.id,
                code=A2AError.METHOD_NOT_FOUND,
                message=f"Method not found: {method}",
                source_agent=self.agent_id,
            )
        
        try:
            handler = self._handlers[method]
            result = await handler(request)
            
            return A2AResponse.success(
                request_id=request.id,
                result=result,
                source_agent=self.agent_id,
            )
        except ValueError as e:
            return A2AResponse.failure(
                request_id=request.id,
                code=A2AError.INVALID_PARAMS,
                message=str(e),
                source_agent=self.agent_id,
            )
        except Exception as e:
            logger.exception(f"Handler error: {e}")
            return A2AResponse.failure(
                request_id=request.id,
                code=A2AError.INTERNAL_ERROR,
                message=str(e),
                source_agent=self.agent_id,
            )
    
    def handler(
        self,
        method: str | A2AMethod,
    ) -> Callable[[MethodHandler], MethodHandler]:
        """
        注册方法处理器装饰器
        
        用法：
            @server.handler("task.invoke")
            async def handle_invoke(request: A2ARequest) -> Any:
                ...
        """
        method_str = method.value if isinstance(method, A2AMethod) else method
        
        def decorator(func: MethodHandler) -> MethodHandler:
            self._handlers[method_str] = func
            logger.debug(f"Registered handler: {method_str}")
            return func
        
        return decorator
    
    def register_handler(
        self,
        method: str | A2AMethod,
        handler: MethodHandler,
    ) -> None:
        """直接注册处理器"""
        method_str = method.value if isinstance(method, A2AMethod) else method
        self._handlers[method_str] = handler
    
    def register_capability(self, capability: AgentCapability) -> None:
        """注册能力"""
        self._capabilities.append(capability)
    
    def _get_agent_info(self) -> AgentInfo:
        """获取 Agent 信息"""
        return AgentInfo(
            agent_id=self.agent_id,
            name=self.agent_name,
            description=self.description,
            version=self.version,
            capabilities=[cap.name for cap in self._capabilities],
            supported_methods=list(self._handlers.keys()),
            status="ready",
            active_tasks=len(self._active_tasks),
            max_concurrent_tasks=self._max_concurrent_tasks,
        )
    
    def create_task(self, task_type: str) -> TaskResult:
        """创建任务记录"""
        task_id = f"task-{uuid4().hex[:12]}"
        task = TaskResult(
            task_id=task_id,
            state=TaskState.PENDING,
        )
        self._active_tasks[task_id] = task
        return task
    
    def complete_task(
        self,
        task_id: str,
        output: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """完成任务"""
        if task_id not in self._active_tasks:
            return
        
        task = self._active_tasks[task_id]
        if error:
            task.state = TaskState.FAILED
            task.error = error
        else:
            task.state = TaskState.COMPLETED
            task.output = output
        
        from datetime import datetime
        task.completed_at = datetime.utcnow()
    
    async def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
    ) -> None:
        """运行服务器"""
        import uvicorn
        
        logger.info(
            f"Starting A2A server",
            agent_id=self.agent_id,
            host=host,
            port=port,
        )
        
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
