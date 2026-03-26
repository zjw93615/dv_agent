"""
MCP (Model Context Protocol) 管理器
管理 MCP 服务器连接和工具
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

import httpx
import yaml

from .models import (
    BaseTool,
    ToolResult,
    ToolDefinition,
    ToolParameter,
    ToolResultStatus,
)
from .registry import ToolRegistry
from ..config.exceptions import MCPConnectionError, ToolExecutionError
from ..config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    url: str
    enabled: bool = True
    timeout: float = 30.0
    headers: dict[str, str] = None
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


class MCPTool(BaseTool):
    """
    MCP 远程工具
    
    通过 HTTP 调用 MCP 服务器的工具
    """
    
    def __init__(
        self,
        server_name: str,
        server_url: str,
        tool_name: str,
        description: str,
        parameters: list[ToolParameter],
        timeout: float = 30.0,
        headers: dict[str, str] = None,
    ):
        super().__init__()
        self.server_name = server_name
        self.server_url = server_url.rstrip("/")
        self.name = f"{server_name}.{tool_name}"  # 命名空间隔离
        self._tool_name = tool_name
        self.description = description
        self._parameters = parameters
        self._timeout = timeout
        self._headers = headers or {}
        self._client: Optional[httpx.AsyncClient] = None
    
    def _get_parameters(self) -> list[ToolParameter]:
        return self._parameters
    
    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=f"[MCP:{self.server_name}] {self.description}",
            parameters=self._parameters,
            category="mcp",
            timeout=self._timeout,
        )
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=httpx.Timeout(self._timeout),
                headers=self._headers,
            )
        return self._client
    
    async def execute(self, **kwargs) -> ToolResult:
        """调用 MCP 服务器工具"""
        client = await self._get_client()
        
        try:
            response = await client.post(
                "/tools/call",
                json={
                    "name": self._tool_name,
                    "arguments": kwargs,
                },
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("error"):
                return ToolResult.error(
                    self.name,
                    data["error"].get("message", "Unknown error"),
                )
            
            return ToolResult.success(
                self.name,
                data.get("result"),
            )
            
        except httpx.TimeoutException:
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.TIMEOUT,
                error=f"MCP call timed out after {self._timeout}s",
            )
        except Exception as e:
            return ToolResult.error(self.name, str(e))
    
    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None


class MCPManager:
    """
    MCP 服务器管理器
    
    功能：
    - 管理多个 MCP 服务器连接
    - 发现和注册 MCP 工具
    - 统一工具调用
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self._servers: dict[str, MCPServerConfig] = {}
        self._tools: dict[str, MCPTool] = {}
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._config_path = config_path
        self._tool_registry = tool_registry
    
    async def initialize(
        self,
        config_path: Optional[str] = None,
    ) -> None:
        """初始化（从配置加载）"""
        config_path = config_path or self._config_path
        
        if config_path:
            await self._load_config(config_path)
        
        logger.info(
            f"MCP Manager initialized",
            servers=len(self._servers),
            tools=len(self._tools),
        )
    
    async def _load_config(self, config_path: str) -> None:
        """从配置文件加载"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"MCP config file not found: {config_path}")
            return
        
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        servers = config.get("servers", {})
        for name, server_conf in servers.items():
            if not server_conf.get("enabled", True):
                continue
            
            server_config = MCPServerConfig(
                name=name,
                url=server_conf.get("url", ""),
                enabled=server_conf.get("enabled", True),
                timeout=server_conf.get("timeout", 30.0),
                headers=server_conf.get("headers", {}),
            )
            
            await self.connect_server(server_config)
    
    async def connect_server(
        self,
        config: MCPServerConfig,
    ) -> bool:
        """
        连接 MCP 服务器并发现工具
        
        Args:
            config: 服务器配置
            
        Returns:
            bool: 是否成功
        """
        if not config.enabled:
            return False
        
        name = config.name
        
        try:
            # 创建客户端
            client = httpx.AsyncClient(
                base_url=config.url,
                timeout=httpx.Timeout(config.timeout),
                headers=config.headers,
            )
            
            # 获取工具列表
            response = await client.get("/tools/list")
            response.raise_for_status()
            
            tools_data = response.json()
            tools = tools_data.get("tools", [])
            
            # 注册工具
            for tool_info in tools:
                tool = self._create_mcp_tool(config, tool_info)
                self._tools[tool.name] = tool
                
                # 注册到全局注册表
                if self._tool_registry:
                    self._tool_registry.register(tool)
            
            self._servers[name] = config
            self._clients[name] = client
            
            logger.info(
                f"MCP server connected",
                server=name,
                tools=len(tools),
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect MCP server: {name}", error=str(e))
            return False
    
    def _create_mcp_tool(
        self,
        config: MCPServerConfig,
        tool_info: dict,
    ) -> MCPTool:
        """创建 MCP 工具实例"""
        # 解析参数
        parameters = []
        input_schema = tool_info.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        
        for param_name, param_info in properties.items():
            parameters.append(ToolParameter(
                name=param_name,
                type=param_info.get("type", "string"),
                description=param_info.get("description", ""),
                required=param_name in required,
                enum=param_info.get("enum"),
            ))
        
        return MCPTool(
            server_name=config.name,
            server_url=config.url,
            tool_name=tool_info.get("name", "unknown"),
            description=tool_info.get("description", ""),
            parameters=parameters,
            timeout=config.timeout,
            headers=config.headers,
        )
    
    async def disconnect_server(self, name: str) -> None:
        """断开服务器连接"""
        if name in self._clients:
            await self._clients[name].aclose()
            del self._clients[name]
        
        # 移除相关工具
        tools_to_remove = [
            tool_name for tool_name in self._tools
            if tool_name.startswith(f"{name}.")
        ]
        for tool_name in tools_to_remove:
            tool = self._tools.pop(tool_name)
            await tool.close()
            
            if self._tool_registry:
                self._tool_registry.unregister(tool_name)
        
        if name in self._servers:
            del self._servers[name]
        
        logger.info(f"MCP server disconnected", server=name)
    
    async def close(self) -> None:
        """关闭所有连接"""
        for name in list(self._servers.keys()):
            await self.disconnect_server(name)
    
    # ===== 工具操作 =====
    
    def list_servers(self) -> list[str]:
        """列出已连接的服务器"""
        return list(self._servers.keys())
    
    def list_tools(
        self,
        server: Optional[str] = None,
    ) -> list[str]:
        """列出工具"""
        if server:
            return [
                name for name in self._tools
                if name.startswith(f"{server}.")
            ]
        return list(self._tools.keys())
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """获取工具"""
        return self._tools.get(name)
    
    async def execute(
        self,
        tool_name: str,
        arguments: dict,
    ) -> ToolResult:
        """执行 MCP 工具"""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult.error(
                tool_name,
                f"MCP tool not found: {tool_name}",
            )
        
        return await tool(**arguments)
    
    # ===== 资源访问 =====
    
    async def access_resource(
        self,
        server_name: str,
        uri: str,
    ) -> Optional[Any]:
        """
        访问 MCP 资源
        
        Args:
            server_name: 服务器名称
            uri: 资源 URI
            
        Returns:
            资源内容
        """
        if server_name not in self._clients:
            raise MCPConnectionError(
                message=f"MCP server not connected: {server_name}",
            )
        
        client = self._clients[server_name]
        
        try:
            response = await client.post(
                "/resources/read",
                json={"uri": uri},
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("contents", [])
            
        except Exception as e:
            logger.error(f"Failed to access MCP resource", server=server_name, uri=uri, error=str(e))
            return None
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 全局 MCP 管理器
_mcp_manager: Optional[MCPManager] = None


async def get_mcp_manager(
    config_path: Optional[str] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> MCPManager:
    """获取全局 MCP 管理器"""
    global _mcp_manager
    
    if _mcp_manager is None:
        _mcp_manager = MCPManager(config_path, tool_registry)
        await _mcp_manager.initialize()
    
    return _mcp_manager
