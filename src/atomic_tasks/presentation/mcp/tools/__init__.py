"""MCP-тулы (spec 0004): тонкие адаптеры над сервисами application."""

from dishka import AsyncContainer
from mcp.server.mcpserver import MCPServer

from atomic_tasks.presentation.mcp.tools.read import register_read_tools
from atomic_tasks.presentation.mcp.tools.runtime import ToolRuntime
from atomic_tasks.presentation.mcp.tools.write import register_write_tools


def register_tools(server: MCPServer, container: AsyncContainer) -> None:
    runtime = ToolRuntime(container)
    register_read_tools(server, runtime)
    register_write_tools(server, runtime)
