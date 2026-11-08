"""Composition root: собирает FastAPI, MCP и контейнер dishka в одно ASGI-приложение."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.presentation.fastapi.app import create_fastapi_app
from atomic_tasks.presentation.mcp.server import create_mcp_server, create_mcp_starlette_app


def create_app() -> FastAPI:
    settings = Settings()
    container = create_container()

    mcp_server = create_mcp_server(version=settings.version)
    mcp_app = create_mcp_starlette_app(mcp_server, allowed_hosts=settings.mcp.allowed_hosts)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            await container.close()

    app = create_fastapi_app(version=settings.version, debug=settings.debug, lifespan=lifespan)
    setup_dishka(container, app)
    # MCP монтируется последним: сначала матчатся маршруты FastAPI, остальное (/mcp) уходит в MCP
    app.mount("/", mcp_app)
    return app
