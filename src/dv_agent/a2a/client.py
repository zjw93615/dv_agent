"""
A2A Client
Agent-to-Agent 客户端，用于调用远程 Agent
"""

import time
import asyncio
from typing import Any, Optional
from uuid import uuid4

import httpx

from .models import (
    A2ARequest,
    A2AResponse,
    A2AError,
    A2AMethod,
    TaskInvokeParams,
    TaskResult,
    AgentInfo,
    AgentCapability,
)
from ..config.exceptions import A2AInvokeError, A2ATimeoutError
from ..config.logging import get_logger

logger = get_logger(__name__)


class A2AClient:
    """
    A2A 协议客户端
    
    用于调用远程 Agent 的 A2A 端点
    """
    
    def __init__(
        self,
        base_url: str,
        source_agent_id: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        初始化 A2A 客户端
        
        Args:
            base_url: 目标 Agent 的基础 URL（如 http://localhost:8000）
            source_agent_id: 来源 Agent ID
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.base_url = base_url.rstrip("/")
        self.source_agent_id = source_agent_id
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._client: Optional[httpx.AsyncClient] = None
        self._target_agent_id: Optional[str] = None
    
    async def connect(self) -> None:
        """建立连接"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=self.timeout,
                write=30.0,
                pool=10.0,
            ),
        )
        
        # 获取目标 Agent 信息
        try:
            info = await self.get_info()
            self._target_agent_id = info.agent_id
            logger.info(
                f"Connected to agent",
                target_agent=self._target_agent_id,
                base_url=self.base_url,
            )
        except Exception as e:
            logger.warning(f"Could not get agent info: {e}")
    
    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _send_request(
        self,
        request: A2ARequest,
    ) -> A2AResponse:
        """发送 A2A 请求"""
        if not self._client:
            await self.connect()
        
        request.source_agent = self.source_agent_id
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                
                response = await self._client.post(
                    "/a2a",
                    json=request.model_dump(mode="json"),
                )
                response.raise_for_status()
                
                data = response.json()
                a2a_response = A2AResponse(**data)
                
                logger.debug(
                    f"A2A request completed",
                    method=request.method,
                    latency_ms=(time.time() - start_time) * 1000,
                    success=a2a_response.is_success,
                )
                
                return a2a_response
                
            except httpx.TimeoutException as e:
                last_error = A2ATimeoutError(
                    message=f"Request timed out: {request.method}",
                    target_agent=self._target_agent_id,
                )
                logger.warning(f"A2A request timeout, attempt {attempt + 1}")
                
            except httpx.HTTPStatusError as e:
                last_error = A2AInvokeError(
                    message=f"HTTP error: {e.response.status_code}",
                    target_agent=self._target_agent_id,
                )
                logger.warning(f"A2A request HTTP error: {e.response.status_code}")
                
            except Exception as e:
                last_error = A2AInvokeError(
                    message=str(e),
                    target_agent=self._target_agent_id,
                )
                logger.warning(f"A2A request failed: {e}")
            
            # 重试延迟
            if attempt < self.max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
        
        raise last_error
    
    async def call(
        self,
        method: str | A2AMethod,
        params: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        调用远程方法
        
        Args:
            method: 方法名
            params: 参数
            session_id: 会话ID
            timeout: 超时时间
            
        Returns:
            方法返回值
            
        Raises:
            A2AInvokeError: 调用失败
        """
        method_str = method.value if isinstance(method, A2AMethod) else method
        
        request = A2ARequest(
            method=method_str,
            params=params,
            session_id=session_id,
            timeout=timeout or self.timeout,
            target_agent=self._target_agent_id,
        )
        
        response = await self._send_request(request)
        
        if not response.is_success:
            raise A2AInvokeError(
                message=response.error.message if response.error else "Unknown error",
                target_agent=self._target_agent_id,
                error_code=response.error.code if response.error else None,
            )
        
        return response.result
    
    # ===== 便捷方法 =====
    
    async def ping(self) -> bool:
        """Ping 目标 Agent"""
        try:
            result = await self.call(A2AMethod.PING)
            return result.get("pong", False)
        except Exception:
            return False
    
    async def get_info(self) -> AgentInfo:
        """获取 Agent 信息"""
        result = await self.call(A2AMethod.INFO)
        return AgentInfo(**result)
    
    async def get_capabilities(self) -> list[AgentCapability]:
        """获取 Agent 能力列表"""
        result = await self.call(A2AMethod.CAPABILITIES)
        return [AgentCapability(**cap) for cap in result]
    
    async def invoke_task(
        self,
        task_type: str,
        input_data: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
        async_mode: bool = False,
        timeout: Optional[float] = None,
    ) -> TaskResult:
        """
        调用任务
        
        Args:
            task_type: 任务类型
            input_data: 输入数据
            context: 上下文
            async_mode: 是否异步执行
            timeout: 超时时间
            
        Returns:
            TaskResult: 任务结果
        """
        params = TaskInvokeParams(
            task_type=task_type,
            input=input_data,
            context=context,
            async_mode=async_mode,
            timeout=timeout,
        ).model_dump()
        
        result = await self.call(
            A2AMethod.INVOKE,
            params=params,
            timeout=timeout,
        )
        
        return TaskResult(**result)
    
    async def get_task_status(self, task_id: str) -> TaskResult:
        """获取任务状态"""
        result = await self.call(
            A2AMethod.STATUS,
            params={"task_id": task_id},
        )
        return TaskResult(**result)
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        result = await self.call(
            A2AMethod.CANCEL,
            params={"task_id": task_id},
        )
        return result.get("cancelled", False)
    
    async def send_message(
        self,
        content: str,
        message_type: str = "text",
        metadata: Optional[dict] = None,
    ) -> Any:
        """发送消息"""
        return await self.call(
            A2AMethod.MESSAGE,
            params={
                "content": content,
                "type": message_type,
                "metadata": metadata or {},
            },
        )
    
    @property
    def target_agent_id(self) -> Optional[str]:
        """目标 Agent ID"""
        return self._target_agent_id
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class A2AClientPool:
    """
    A2A 客户端池
    
    管理多个 Agent 的连接
    """
    
    def __init__(
        self,
        source_agent_id: Optional[str] = None,
        default_timeout: float = 30.0,
    ):
        self.source_agent_id = source_agent_id
        self.default_timeout = default_timeout
        self._clients: dict[str, A2AClient] = {}
    
    async def get_client(
        self,
        agent_url: str,
    ) -> A2AClient:
        """获取或创建客户端"""
        if agent_url not in self._clients:
            client = A2AClient(
                base_url=agent_url,
                source_agent_id=self.source_agent_id,
                timeout=self.default_timeout,
            )
            await client.connect()
            self._clients[agent_url] = client
        
        return self._clients[agent_url]
    
    async def call(
        self,
        agent_url: str,
        method: str | A2AMethod,
        params: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """调用指定 Agent 的方法"""
        client = await self.get_client(agent_url)
        return await client.call(method, params, **kwargs)
    
    async def broadcast(
        self,
        method: str | A2AMethod,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """广播调用所有已连接的 Agent"""
        results = {}
        
        for url, client in self._clients.items():
            try:
                result = await client.call(method, params)
                results[url] = {"success": True, "result": result}
            except Exception as e:
                results[url] = {"success": False, "error": str(e)}
        
        return results
    
    async def close(self) -> None:
        """关闭所有客户端"""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
