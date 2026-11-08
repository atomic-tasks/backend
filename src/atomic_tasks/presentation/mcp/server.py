from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

INSTRUCTIONS = """\
AtomicTasks: дерево папок и задач пользователя.
Перед созданием задач посмотри существующее дерево, чтобы не плодить дубли.
"""


def create_mcp_server(*, version: str) -> MCPServer:
    server: MCPServer = MCPServer(
        name="atomic-tasks",
        version=version,
        instructions=INSTRUCTIONS,
    )
    # Тулы регистрируются из presentation/mcp/tools по мере реализации.
    return server


def create_mcp_starlette_app(server: MCPServer, *, allowed_hosts: list[str]) -> Starlette:
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )
