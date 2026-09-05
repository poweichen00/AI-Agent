from __future__ import annotations

import logging

from agentx.core.config import McpServerConfig
from agentx.core.mcp.client import McpClient
from agentx.core.mcp.tool import McpTool
from agentx.core.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


# 管理所有 MCP server 連線的生命週期：啟動、工具發現、註冊、關閉
class McpServerManager:
    def __init__(self) -> None:
        self._clients: dict[str, McpClient] = {}
        self._tools: list[McpTool] = []

    # 依次連線每個 MCP server，發現工具後快取供後續 registry 使用；失敗時記錄日誌並跳過
    async def start_all(self, servers: list[McpServerConfig]) -> None:
        for cfg in servers:
            try:
                client = await self._connect(cfg)
                tool_defs = await client.list_tools()
                for tool_def in tool_defs:
                    self._tools.append(McpTool(client, cfg.name, tool_def))
                self._clients[cfg.name] = client
                log.info(
                    "mcp: server '%s' connected, %d tool(s) discovered",
                    cfg.name, len(tool_defs),
                )
            except Exception:
                log.exception("mcp: server '%s' failed to start, skipping", cfg.name)

    # 將所有已發現的 MCP 工具註冊到指定 registry
    def register_tools(self, registry: ToolRegistry) -> None:
        for tool in self._tools:
            registry.register(tool)

    # 返回已發現的 MCP 工具列表（用於 runner 每次 run 時注入新 registry）
    def get_tools(self) -> list[McpTool]:
        return list(self._tools)

    # 關閉所有 MCP 連線並終止 stdio 子程式
    async def stop_all(self) -> None:
        for name, client in list(self._clients.items()):
            try:
                await client.close()
                log.info("mcp: server '%s' closed", name)
            except Exception:
                log.warning("mcp: error closing server '%s'", name)
        self._clients.clear()

    # 根據 transport 型別建立連線
    async def _connect(self, cfg: McpServerConfig) -> McpClient:
        client = McpClient()
        if cfg.transport == "stdio":
            if not cfg.command:
                raise ValueError(f"mcp server '{cfg.name}': stdio transport requires 'command'")
            await client.connect_stdio(cfg.command, cfg.args, cfg.env or None)
        elif cfg.transport == "tcp":
            await client.connect_tcp(cfg.host, cfg.port)
        else:
            raise ValueError(f"mcp server '{cfg.name}': unknown transport '{cfg.transport}'")
        return client
