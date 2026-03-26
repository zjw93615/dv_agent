"""
OpenAI Adapter
支持 OpenAI 官方 API 及兼容接口
"""

import json
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

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


class OpenAIAdapter(BaseAdapter):
    """OpenAI API Adapter"""
    
    provider_name: str = "openai"
    
    def __init__(
        self,
        config: ProviderConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        super().__init__(config, retry_config)
        self._client: Optional[AsyncOpenAI] = None
    
    async def initialize(self) -> None:
        """初始化OpenAI客户端"""
        self._client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=float(self.config.timeout),
        )
        logger.info(
            f"OpenAI adapter initialized",
            base_url=self.config.base_url or "default",
            model=self.config.model,
        )
    
    async def close(self) -> None:
        """关闭客户端"""
        if self._client:
            await self._client.close()
            self._client = None
    
    async def _do_complete(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """执行完成请求"""
        params = self._build_params(request)
        
        response: ChatCompletion = await self._client.chat.completions.create(**params)
        
        return self._parse_response(response)
    
    async def _do_stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[StreamChunk]:
        """执行流式请求"""
        params = self._build_params(request)
        params["stream"] = True
        
        stream = await self._client.chat.completions.create(**params)
        
        tool_calls_buffer: dict[int, dict] = {}
        
        async for chunk in stream:
            yield self._parse_chunk(chunk, tool_calls_buffer)
    
    def _build_params(self, request: LLMRequest) -> dict:
        """构建API请求参数"""
        merged = self._merge_params(request)
        
        params = {
            "model": merged["model"],
            "messages": [self._convert_message(m) for m in request.messages],
            "temperature": merged["temperature"],
            "max_tokens": merged["max_tokens"],
        }
        
        if merged["top_p"] is not None:
            params["top_p"] = merged["top_p"]
        
        if request.tools:
            params["tools"] = [t.model_dump() for t in request.tools]
            if request.tool_choice:
                params["tool_choice"] = request.tool_choice
        
        return params
    
    def _convert_message(self, message: Message) -> dict:
        """转换消息格式"""
        msg = {
            "role": message.role if isinstance(message.role, str) else message.role.value,
            "content": message.content,
        }
        
        if message.name:
            msg["name"] = message.name
        
        if message.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        
        if message.tool_call_id:
            msg["tool_call_id"] = message.tool_call_id
        
        return msg
    
    def _parse_response(self, response: ChatCompletion) -> LLMResponse:
        """解析响应"""
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in message.tool_calls
            ]
        
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
            request_id=response.id,
        )
    
    def _parse_chunk(
        self,
        chunk: ChatCompletionChunk,
        tool_calls_buffer: dict[int, dict],
    ) -> StreamChunk:
        """解析流式响应块"""
        if not chunk.choices:
            return StreamChunk(model=chunk.model)
        
        choice = chunk.choices[0]
        delta = choice.delta
        
        content = delta.content
        tool_calls = None
        
        # 处理工具调用增量
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    }
                
                if tc_delta.id:
                    tool_calls_buffer[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_calls_buffer[idx]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments
            
            # 仅在结束时返回完整工具调用
            if choice.finish_reason == "tool_calls":
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    for tc in tool_calls_buffer.values()
                ]
        
        return StreamChunk(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            model=chunk.model,
        )
