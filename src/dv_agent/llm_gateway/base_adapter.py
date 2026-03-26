"""
LLM Adapter 基类
定义统一的LLM访问接口
"""

import time
import random
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from .models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    Message,
    ProviderConfig,
    RetryConfig,
    TokenUsage,
)
from ..config.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
    LLMAuthenticationError,
    LLMTimeoutError,
    LLMInvalidRequestError,
)
from ..config.logging import get_logger

logger = get_logger(__name__)


class BaseAdapter(ABC):
    """LLM Adapter 基类"""
    
    # 子类需要定义
    provider_name: str = "base"
    
    def __init__(
        self,
        config: ProviderConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.config = config
        self.retry_config = retry_config or RetryConfig()
        self._client = None
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化客户端连接"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭客户端连接"""
        pass
    
    @abstractmethod
    async def _do_complete(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """执行实际的完成请求（子类实现）"""
        pass
    
    @abstractmethod
    async def _do_stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[StreamChunk]:
        """执行实际的流式请求（子类实现）"""
        pass
    
    async def complete(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        执行LLM完成请求（带重试）
        
        Args:
            request: LLM请求
            
        Returns:
            LLMResponse: LLM响应
        """
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                response = await self._do_complete(request)
                response.latency_ms = (time.time() - start_time) * 1000
                response.provider = self.provider_name
                
                logger.debug(
                    f"LLM complete success",
                    provider=self.provider_name,
                    model=response.model,
                    latency_ms=response.latency_ms,
                    tokens=response.usage.total_tokens,
                )
                return response
                
            except Exception as e:
                last_error = self._wrap_error(e)
                
                if not self._should_retry(last_error, attempt):
                    raise last_error
                
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"LLM request failed, retrying",
                    provider=self.provider_name,
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(last_error),
                )
                await asyncio.sleep(delay)
        
        raise last_error
    
    async def stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[StreamChunk]:
        """
        执行LLM流式请求（带重试）
        
        Args:
            request: LLM请求
            
        Yields:
            StreamChunk: 流式响应块
        """
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                chunk_index = 0
                async for chunk in self._do_stream(request):
                    chunk.index = chunk_index
                    chunk.provider = self.provider_name
                    chunk_index += 1
                    yield chunk
                
                logger.debug(
                    f"LLM stream complete",
                    provider=self.provider_name,
                    chunks=chunk_index,
                    latency_ms=(time.time() - start_time) * 1000,
                )
                return
                
            except Exception as e:
                last_error = self._wrap_error(e)
                
                if not self._should_retry(last_error, attempt):
                    raise last_error
                
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"LLM stream failed, retrying",
                    provider=self.provider_name,
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(last_error),
                )
                await asyncio.sleep(delay)
        
        raise last_error
    
    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.retry_config.max_retries:
            return False
        
        error_name = type(error).__name__
        
        # 检查不可重试错误
        if error_name in self.retry_config.non_retryable_errors:
            return False
        
        # 检查可重试错误
        if error_name in self.retry_config.retryable_errors:
            return True
        
        # 特定异常类型
        if isinstance(error, (LLMRateLimitError, LLMTimeoutError)):
            return True
        if isinstance(error, (LLMAuthenticationError, LLMInvalidRequestError)):
            return False
        
        # 默认重试
        return True
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟（指数退避）"""
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** attempt
        )
        delay = min(delay, self.retry_config.max_delay)
        
        if self.retry_config.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay
    
    def _wrap_error(self, error: Exception) -> Exception:
        """包装异常为统一类型"""
        if isinstance(error, LLMProviderError):
            return error
        
        error_str = str(error).lower()
        
        if "rate limit" in error_str or "429" in error_str:
            return LLMRateLimitError(
                message=str(error),
                provider=self.provider_name,
            )
        elif "unauthorized" in error_str or "401" in error_str or "api key" in error_str:
            return LLMAuthenticationError(
                message=str(error),
                provider=self.provider_name,
            )
        elif "timeout" in error_str or "timed out" in error_str:
            return LLMTimeoutError(
                message=str(error),
                provider=self.provider_name,
            )
        elif "invalid" in error_str or "400" in error_str:
            return LLMInvalidRequestError(
                message=str(error),
                provider=self.provider_name,
            )
        else:
            return LLMProviderError(
                message=str(error),
                provider=self.provider_name,
            )
    
    def _merge_params(self, request: LLMRequest) -> dict:
        """合并请求参数与默认配置"""
        return {
            "model": request.model or self.config.model,
            "temperature": request.temperature if request.temperature is not None else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
            "top_p": request.top_p,
            "timeout": request.timeout or self.config.timeout,
        }
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
