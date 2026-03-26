"""
Ollama Adapter
支持本地 Ollama 部署
"""

import json
from typing import AsyncIterator, Optional, Any

import httpx

from .base_adapter import BaseAdapter
from .models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    Message,
    ToolCall,
    TokenUsage,
    ProviderConfig,
    RetryConfig,
)
from ..config.logging import get_logger

logger = get_logger(__name__)

# Ollama 默认配置
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "llama3.2"


class OllamaAdapter(BaseAdapter):
    """
    Ollama API Adapter
    
    Ollama 有自己的原生 API 格式，此适配器直接使用原生格式
    以获得最佳兼容性（如 Tool Calling 等特性）
    """
    
    provider_name: str = "ollama"
    
    def __init__(
        self,
        config: ProviderConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        super().__init__(config, retry_config)
        
        # 设置默认配置
        if not self.config.base_url:
            self.config.base_url = OLLAMA_DEFAULT_BASE_URL
        if not self.config.model:
            self.config.model = OLLAMA_DEFAULT_MODEL
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def initialize(self) -> None:
        """初始化 HTTP 客户端"""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(self.config.timeout),
                write=30.0,
                pool=10.0,
            ),
        )
        logger.info(
            f"Ollama adapter initialized",
            base_url=self.config.base_url,
            model=self.config.model,
        )
    
    async def close(self) -> None:
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _do_complete(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """执行完成请求"""
        params = self._build_params(request)
        params["stream"] = False
        
        response = await self._client.post("/api/chat", json=params)
        response.raise_for_status()
        
        data = response.json()
        return self._parse_response(data)
    
    async def _do_stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[StreamChunk]:
        """执行流式请求"""
        params = self._build_params(request)
        params["stream"] = True
        
        async with self._client.stream("POST", "/api/chat", json=params) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    yield self._parse_chunk(data)
                    
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse Ollama stream line: {line}")
                    continue
    
    def _build_params(self, request: LLMRequest) -> dict:
        """构建 Ollama API 请求参数"""
        merged = self._merge_params(request)
        
        params = {
            "model": merged["model"],
            "messages": [self._convert_message(m) for m in request.messages],
            "options": {
                "temperature": merged["temperature"],
                "num_predict": merged["max_tokens"],
            },
        }
        
        if merged["top_p"] is not None:
            params["options"]["top_p"] = merged["top_p"]
        
        # Ollama Tool Calling
        if request.tools:
            params["tools"] = self._convert_tools(request.tools)
        
        return params
    
    def _convert_message(self, message: Message) -> dict:
        """转换消息格式为 Ollama 格式"""
        msg = {
            "role": message.role if isinstance(message.role, str) else message.role.value,
            "content": message.content or "",
        }
        
        # Ollama 的工具调用格式
        if message.tool_calls:
            msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        
        return msg
    
    def _convert_tools(self, tools: list) -> list:
        """转换工具定义为 Ollama 格式"""
        return [
            {
                "type": "function",
                "function": t.function if hasattr(t, "function") else t.model_dump().get("function", {}),
            }
            for t in tools
        ]
    
    def _parse_response(self, data: dict) -> LLMResponse:
        """解析 Ollama 响应"""
        message = data.get("message", {})
        
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = self._parse_tool_calls(message["tool_calls"])
        
        # Ollama 的 token 统计
        usage = TokenUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )
        
        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            usage=usage,
            model=data.get("model", self.config.model),
            finish_reason="stop" if data.get("done") else None,
        )
    
    def _parse_chunk(self, data: dict) -> StreamChunk:
        """解析流式响应块"""
        message = data.get("message", {})
        
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = self._parse_tool_calls(message["tool_calls"])
        
        return StreamChunk(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason="stop" if data.get("done") else None,
            model=data.get("model", self.config.model),
        )
    
    def _parse_tool_calls(self, raw_tool_calls: list) -> list[ToolCall]:
        """解析工具调用"""
        tool_calls = []
        for i, tc in enumerate(raw_tool_calls):
            func = tc.get("function", {})
            args = func.get("arguments", {})
            
            tool_calls.append(ToolCall(
                id=f"call_{i}",  # Ollama 不提供 ID，生成一个
                name=func.get("name", ""),
                arguments=json.dumps(args) if isinstance(args, dict) else str(args),
            ))
        
        return tool_calls
    
    async def list_models(self) -> list[str]:
        """列出可用模型"""
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        
        data = response.json()
        return [m["name"] for m in data.get("models", [])]
    
    async def pull_model(self, model: str) -> bool:
        """拉取模型"""
        try:
            async with self._client.stream(
                "POST",
                "/api/pull",
                json={"name": model},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        logger.debug(f"Pulling {model}: {data.get('status', '')}")
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {model}: {e}")
            return False
