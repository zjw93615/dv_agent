"""
LLM Gateway
统一的 LLM 访问入口，支持多 Provider 和 Fallback
"""

import asyncio
from typing import AsyncIterator, Optional, Type, Any
from pathlib import Path

import yaml

from .base_adapter import BaseAdapter
from .openai_adapter import OpenAIAdapter
from .deepseek_adapter import DeepSeekAdapter
from .ollama_adapter import OllamaAdapter
from .models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    ProviderConfig,
    RetryConfig,
)
from ..config.exceptions import (
    LLMProviderError,
    AllProvidersFailedError,
    ConfigurationError,
)
from ..config.logging import get_logger

logger = get_logger(__name__)


# Provider 类型映射
PROVIDER_ADAPTERS: dict[str, Type[BaseAdapter]] = {
    "openai": OpenAIAdapter,
    "deepseek": DeepSeekAdapter,
    "ollama": OllamaAdapter,
}


class LLMGateway:
    """
    LLM 统一网关
    
    功能：
    - 多 Provider 管理
    - 自动 Fallback
    - 配置化 Provider 选择
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        default_provider: Optional[str] = None,
    ):
        self._providers: dict[str, BaseAdapter] = {}
        self._fallback_chain: list[str] = []
        self._default_provider: Optional[str] = default_provider
        self._config_path = config_path
        self._initialized = False
    
    async def initialize(self, config_path: Optional[str] = None) -> None:
        """从配置文件初始化"""
        config_path = config_path or self._config_path
        
        if config_path:
            await self._load_from_config(config_path)
        
        self._initialized = True
        logger.info(
            "LLM Gateway initialized",
            providers=list(self._providers.keys()),
            fallback_chain=self._fallback_chain,
            default=self._default_provider,
        )
    
    async def _load_from_config(self, config_path: str) -> None:
        """从 YAML 配置加载"""
        path = Path(config_path)
        if not path.exists():
            raise ConfigurationError(f"LLM config file not found: {config_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 全局重试配置
        retry_config = None
        if "retry" in config:
            retry_config = RetryConfig(**config["retry"])
        
        # 加载 providers
        providers_config = config.get("providers", {})
        for name, provider_conf in providers_config.items():
            if not provider_conf.get("enabled", True):
                continue
            
            provider_type = provider_conf.get("type", name)
            
            provider_config = ProviderConfig(
                type=provider_type,
                api_key=provider_conf.get("api_key"),
                base_url=provider_conf.get("base_url"),
                model=provider_conf.get("model", ""),
                timeout=provider_conf.get("timeout", 30),
                max_retries=provider_conf.get("max_retries", 3),
                temperature=provider_conf.get("temperature", 0.7),
                max_tokens=provider_conf.get("max_tokens", 4096),
                extra=provider_conf.get("extra", {}),
            )
            
            await self.register_provider(name, provider_config, retry_config)
        
        # Fallback 链
        self._fallback_chain = config.get("fallback_chain", list(self._providers.keys()))
        
        # 默认 provider
        if not self._default_provider:
            self._default_provider = config.get("default_provider")
            if not self._default_provider and self._fallback_chain:
                self._default_provider = self._fallback_chain[0]
    
    async def register_provider(
        self,
        name: str,
        config: ProviderConfig,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """注册 Provider"""
        provider_type = config.type
        
        if provider_type not in PROVIDER_ADAPTERS:
            raise ConfigurationError(f"Unknown provider type: {provider_type}")
        
        adapter_class = PROVIDER_ADAPTERS[provider_type]
        adapter = adapter_class(config, retry_config)
        
        await adapter.initialize()
        self._providers[name] = adapter
        
        logger.debug(f"Registered provider: {name} ({provider_type})")
    
    def add_provider(
        self,
        name: str,
        adapter: BaseAdapter,
    ) -> None:
        """添加已初始化的 Provider"""
        self._providers[name] = adapter
        
        if not self._default_provider:
            self._default_provider = name
    
    async def close(self) -> None:
        """关闭所有 Provider"""
        for name, provider in self._providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider {name}: {e}")
        
        self._providers.clear()
        self._initialized = False
    
    def get_provider(self, name: Optional[str] = None) -> BaseAdapter:
        """获取指定 Provider"""
        name = name or self._default_provider
        
        if not name:
            raise ConfigurationError("No provider specified and no default provider set")
        
        if name not in self._providers:
            raise ConfigurationError(f"Provider not found: {name}")
        
        return self._providers[name]
    
    async def complete(
        self,
        request: LLMRequest,
        provider: Optional[str] = None,
        use_fallback: bool = True,
    ) -> LLMResponse:
        """
        执行 LLM 请求
        
        Args:
            request: LLM 请求
            provider: 指定 Provider（可选）
            use_fallback: 是否启用 Fallback
            
        Returns:
            LLMResponse
        """
        if provider:
            # 使用指定 provider，不 fallback
            return await self.get_provider(provider).complete(request)
        
        if not use_fallback:
            # 使用默认 provider，不 fallback
            return await self.get_provider().complete(request)
        
        # 使用 fallback 链
        return await self._complete_with_fallback(request)
    
    async def _complete_with_fallback(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """带 Fallback 的请求"""
        errors: list[tuple[str, Exception]] = []
        
        chain = self._fallback_chain or list(self._providers.keys())
        
        for provider_name in chain:
            if provider_name not in self._providers:
                continue
            
            try:
                logger.debug(f"Trying provider: {provider_name}")
                response = await self._providers[provider_name].complete(request)
                
                if errors:
                    logger.info(
                        f"Fallback succeeded",
                        provider=provider_name,
                        failed_providers=[e[0] for e in errors],
                    )
                
                return response
                
            except Exception as e:
                errors.append((provider_name, e))
                logger.warning(
                    f"Provider failed, trying next",
                    provider=provider_name,
                    error=str(e),
                )
        
        # 所有 provider 都失败
        raise AllProvidersFailedError(
            message="All providers failed",
            errors={name: str(err) for name, err in errors},
        )
    
    async def stream(
        self,
        request: LLMRequest,
        provider: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        流式请求
        
        注意：流式请求不支持 Fallback（因为已经开始返回数据）
        """
        adapter = self.get_provider(provider)
        async for chunk in adapter.stream(request):
            yield chunk
    
    @property
    def providers(self) -> list[str]:
        """可用 Provider 列表"""
        return list(self._providers.keys())
    
    @property
    def default_provider(self) -> Optional[str]:
        """默认 Provider"""
        return self._default_provider
    
    @default_provider.setter
    def default_provider(self, name: str) -> None:
        """设置默认 Provider"""
        if name not in self._providers:
            raise ConfigurationError(f"Provider not found: {name}")
        self._default_provider = name
    
    async def __aenter__(self):
        if not self._initialized:
            await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 全局单例
_gateway_instance: Optional[LLMGateway] = None


async def get_llm_gateway(
    config_path: Optional[str] = None,
    force_new: bool = False,
) -> LLMGateway:
    """获取 LLM Gateway 单例"""
    global _gateway_instance
    
    if _gateway_instance is None or force_new:
        _gateway_instance = LLMGateway(config_path)
        await _gateway_instance.initialize()
    
    return _gateway_instance
