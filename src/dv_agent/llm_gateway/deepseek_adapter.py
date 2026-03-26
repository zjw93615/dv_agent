"""
DeepSeek Adapter
基于 OpenAI 兼容接口实现
"""

from typing import Optional

from .openai_adapter import OpenAIAdapter
from .models import ProviderConfig, RetryConfig
from ..config.logging import get_logger

logger = get_logger(__name__)

# DeepSeek 默认配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekAdapter(OpenAIAdapter):
    """
    DeepSeek API Adapter
    
    DeepSeek 使用 OpenAI 兼容的 API 格式，
    因此直接继承 OpenAIAdapter 并设置特定配置即可
    """
    
    provider_name: str = "deepseek"
    
    def __init__(
        self,
        config: ProviderConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        # 设置默认的 base_url（如果未配置）
        if not config.base_url:
            config.base_url = DEEPSEEK_BASE_URL
        
        # 设置默认模型（如果未配置）
        if not config.model:
            config.model = DEEPSEEK_DEFAULT_MODEL
        
        super().__init__(config, retry_config)
    
    async def initialize(self) -> None:
        """初始化 DeepSeek 客户端"""
        await super().initialize()
        logger.info(
            f"DeepSeek adapter initialized",
            base_url=self.config.base_url,
            model=self.config.model,
        )
