from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from atomic_tasks.presentation.fastapi.routers import health


def _operation_id(route: APIRoute) -> str:
    # Стабильные operation_id = имена методов в сгенерированных SDK (web, Flutter, бот).
    return route.name


def create_fastapi_app(
    *,
    version: str,
    debug: bool,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]],
) -> FastAPI:
    app = FastAPI(
        title="AtomicTasks API",
        version=version,
        debug=debug,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.include_router(health.router)
    return app
