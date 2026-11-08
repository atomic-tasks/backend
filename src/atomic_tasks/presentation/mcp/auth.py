from contextvars import ContextVar

from dishka import AsyncContainer
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from atomic_tasks.application.dto import Identity
from atomic_tasks.application.errors import ApplicationError
from atomic_tasks.application.services.auth_service import AuthService
from atomic_tasks.domain.exceptions import DomainError
from atomic_tasks.presentation.fastapi.errors import problem, status_for

# Текущий пользователь MCP-запроса; тулы читают его отсюда.
current_identity: ContextVar[Identity] = ContextVar("current_identity")


class McpAuthMiddleware:
    """Аутентификация запросов к MCP: тот же AuthService, что и у FastAPI."""

    def __init__(self, app: ASGIApp, container: AsyncContainer, *, path: str) -> None:
        self._app = app
        self._container = container
        self._path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._path):
            await self._app(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization")
        try:
            async with self._container() as request_container:
                auth = await request_container.get(AuthService)
                identity = await auth.authenticate(authorization)
        except (ApplicationError, DomainError) as exc:
            response = problem(status_for(exc), exc.message)
            await response(scope, receive, send)
            return

        token = current_identity.set(identity)
        try:
            await self._app(scope, receive, send)
        finally:
            current_identity.reset(token)
