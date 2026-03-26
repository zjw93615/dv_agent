"""
Configuration settings for DV-Agent.

Uses Pydantic Settings for configuration management with environment variable support.
"""

from typing import Optional, Dict, Any, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    ssl: bool = Field(default=False, description="Use SSL connection")
    max_connections: int = Field(default=10, description="Maximum connections in pool")
    
    @property
    def url(self) -> str:
        """Generate Redis URL from settings."""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"


class LLMProviderSettings(BaseSettings):
    """LLM provider settings."""
    
    model_config = SettingsConfigDict(env_prefix="LLM_")
    
    # Primary provider
    primary_provider: str = Field(default="openai", description="Primary LLM provider")
    
    # Fallback chain
    fallback_providers: List[str] = Field(
        default=["deepseek", "ollama"],
        description="Fallback providers in order"
    )
    
    # OpenAI settings
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API base URL"
    )
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
    
    # DeepSeek settings
    deepseek_api_key: Optional[str] = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="DeepSeek API base URL"
    )
    deepseek_model: str = Field(default="deepseek-chat", description="Default DeepSeek model")
    
    # Ollama settings (local deployment)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama local server URL"
    )
    ollama_model: str = Field(default="llama3.2", description="Default Ollama model")
    
    # Common settings
    default_temperature: float = Field(default=0.7, description="Default temperature")
    default_max_tokens: int = Field(default=4096, description="Default max tokens")
    request_timeout: float = Field(default=60.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")


class A2ASettings(BaseSettings):
    """A2A protocol settings."""
    
    model_config = SettingsConfigDict(env_prefix="A2A_")
    
    host: str = Field(default="0.0.0.0", description="A2A server host")
    port: int = Field(default=8080, description="A2A server port")
    workers: int = Field(default=4, description="Number of workers")
    
    # Client settings
    connection_timeout: float = Field(default=30.0, description="Connection timeout")
    read_timeout: float = Field(default=120.0, description="Read timeout")
    max_connections: int = Field(default=100, description="Max connections per host")
    
    # Security
    enable_cors: bool = Field(default=True, description="Enable CORS")
    allowed_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins"
    )


class AgentSettings(BaseSettings):
    """Agent behavior settings."""
    
    model_config = SettingsConfigDict(env_prefix="AGENT_")
    
    # ReAct loop settings
    max_iterations: int = Field(default=10, description="Max ReAct iterations")
    thinking_timeout: float = Field(default=30.0, description="Thinking step timeout")
    action_timeout: float = Field(default=60.0, description="Action step timeout")
    
    # Session settings
    session_ttl: int = Field(default=3600, description="Session TTL in seconds")
    context_window: int = Field(default=20, description="Context window size")
    
    # Orchestrator settings
    enable_parallel_dispatch: bool = Field(
        default=False,
        description="Enable parallel task dispatch"
    )
    dispatch_timeout: float = Field(default=120.0, description="Task dispatch timeout")


class IntentSettings(BaseSettings):
    """Intent recognition settings."""
    
    model_config = SettingsConfigDict(env_prefix="INTENT_")
    
    # Recognition mode
    use_embedding: bool = Field(default=False, description="Use embedding-based recognition")
    use_llm_fallback: bool = Field(default=True, description="Use LLM as fallback")
    
    # Thresholds
    rule_confidence_threshold: float = Field(default=0.7, description="Rule matching threshold")
    embedding_confidence_threshold: float = Field(default=0.85, description="Embedding threshold")
    llm_confidence_threshold: float = Field(default=0.6, description="LLM classification threshold")
    
    # Embedding settings
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name"
    )


class ToolSettings(BaseSettings):
    """Tool and MCP settings."""
    
    model_config = SettingsConfigDict(env_prefix="TOOL_")
    
    # Built-in skills
    enable_calculator: bool = Field(default=True, description="Enable calculator skill")
    enable_datetime: bool = Field(default=True, description="Enable datetime skill")
    enable_web_search: bool = Field(default=False, description="Enable web search skill")
    
    # MCP settings
    mcp_servers: List[Dict[str, Any]] = Field(
        default=[],
        description="List of MCP server configurations"
    )
    mcp_connection_timeout: float = Field(default=10.0, description="MCP connection timeout")
    mcp_auto_reconnect: bool = Field(default=True, description="Auto reconnect to MCP servers")


class LoggingSettings(BaseSettings):
    """Logging settings."""
    
    model_config = SettingsConfigDict(env_prefix="LOG_")
    
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    json_format: bool = Field(default=False, description="Use JSON log format")
    file_path: Optional[str] = Field(default=None, description="Log file path")
    max_file_size: int = Field(default=10485760, description="Max log file size (10MB)")
    backup_count: int = Field(default=5, description="Number of backup files")


class Settings(BaseSettings):
    """Main application settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="DV_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Application info
    app_name: str = Field(default="dv-agent", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")
    
    # Sub-settings
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    a2a: A2ASettings = Field(default_factory=A2ASettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    intent: IntentSettings = Field(default_factory=IntentSettings)
    tool: ToolSettings = Field(default_factory=ToolSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment name."""
        allowed = {"development", "staging", "production", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v.lower()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary (safe for logging)."""
        data = self.model_dump()
        # Mask sensitive values
        sensitive_keys = {"password", "api_key", "secret"}
        
        def mask_sensitive(d: dict) -> dict:
            result = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    result[k] = mask_sensitive(v)
                elif any(sk in k.lower() for sk in sensitive_keys):
                    result[k] = "***" if v else None
                else:
                    result[k] = v
            return result
        
        return mask_sensitive(data)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings() -> Settings:
    """Reload settings (clear cache)."""
    get_settings.cache_clear()
    return get_settings()
