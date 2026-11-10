"""Что нужно каждому тулу: текущий пользователь, сервисы из request-scope и перевод ошибок."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from dishka import AsyncContainer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from atomic_tasks.application.dto import Identity
from atomic_tasks.application.errors import ApplicationError, AuthenticationError
from atomic_tasks.domain.exceptions import DomainError
from atomic_tasks.presentation.mcp.auth import current_identity


@dataclass(frozen=True)
class ToolRuntime:
    container: AsyncContainer

    @asynccontextmanager
    async def call(self) -> AsyncIterator[tuple[Identity, AsyncContainer]]:
        """Request-scope на вызов тула — своя сессия БД, как у HTTP-запроса.

        Ошибки сервисов и домена превращаются в ToolError: агент получит `isError` и текст,
        который объясняет, что исправить. Прочие исключения SDK скрывает за общим текстом.
        """
        try:
            identity = current_identity.get(None)
            if identity is None:  # middleware не пропустит запрос без токена
                raise AuthenticationError
            async with self.container() as request_container:
                yield identity, request_container
        except (ApplicationError, DomainError) as exc:
            raise ToolError(exc.message) from exc


def compact(result: BaseModel) -> CallToolResult:
    """Ответ тула: JSON без отступов в тексте и тот же JSON в structuredContent.

    По умолчанию SDK кладёт в текст JSON с отступом 2 — это заметная доля токенов
    в ответах-списках, а агент читает именно текст.
    """
    return CallToolResult(
        content=[TextContent(type="text", text=result.model_dump_json())],
        structured_content=result.model_dump(mode="json"),
    )
