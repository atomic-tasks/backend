from contextvars import ContextVar

from dishka import AsyncContainer
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from atomic_tasks.application.dto import AuthTarget, Identity
from atomic_tasks.application.errors import ApplicationError
from atomic_tasks.application.services.auth_service import AuthService
from atomic_tasks.domain.exceptions import DomainError
from atomic_tasks.presentation.fastapi.errors import problem, status_for

# Текущий пользователь MCP-запроса; тулы читают его отсюда.
current_identity: ContextVar[Identity] = ContextVar("current_identity")

UNAUTHORIZED = 401


class McpAuthMiddleware:
    """Аутентификация запросов к MCP: тот же AuthService, что и у FastAPI."""

    def __init__(
        self,
        app: ASGIApp,
        container: AsyncContainer,
        *,
        path: str,
        resource_metadata_url: str | None = None,
    ) -> None:
        self._app = app
        self._container = container
        self._path = path
        # На 401 говорим клиенту, где искать сервер авторизации (RFC 9728 §5.1).
        self._challenge = (
            f'Bearer resource_metadata="{resource_metadata_url}"' if resource_metadata_url else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._path):
            await self._app(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization")
        try:
            async with self._container() as request_container:
                auth = await request_container.get(AuthService)
                identity = await auth.authenticate(authorization, target=AuthTarget.MCP)
        except (ApplicationError, DomainError) as exc:
            response = problem(status_for(exc), exc.message)
            if response.status_code == UNAUTHORIZED and self._challenge:
                response.headers["WWW-Authenticate"] = self._challenge
            await response(scope, receive, send)
            return

        token = current_identity.set(identity)
        try:
            await self._app(scope, receive, send)
        finally:
            current_identity.reset(token)
