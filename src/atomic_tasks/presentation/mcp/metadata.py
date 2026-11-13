"""Protected resource metadata (RFC 9728): по ней MCP-клиент находит IdP (ADR 0012)."""

from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

# Без email бэкенд не проверит allowlist при первом входе.
SCOPES = ["openid", "email", "profile"]


def resource_metadata_url(resource_url: str) -> str:
    """https://host/mcp → https://host/.well-known/oauth-protected-resource/mcp."""
    return str(build_resource_metadata_url(AnyHttpUrl(resource_url)))


def register_resource_metadata(server: MCPServer, *, resource_url: str, issuer: str) -> None:
    """Публичный маршрут без данных пользователя. Путь вне /mcp: McpAuthMiddleware не трогает."""
    path = "/" + resource_metadata_url(resource_url).split("/", 3)[3]
    body = {
        "resource": resource_url,
        "authorization_servers": [issuer],
        "scopes_supported": SCOPES,
        "bearer_methods_supported": ["header"],
    }

    async def protected_resource_metadata(_: Request) -> JSONResponse:
        return JSONResponse(body, headers={"Cache-Control": "public, max-age=3600"})

    # Не декоратором: custom_route в SDK без типов, strict-mypy иначе теряет тип функции.
    server.custom_route(path, methods=["GET"])(protected_resource_metadata)
