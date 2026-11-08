from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

from atomic_tasks.presentation.fastapi.auth import authenticate
from atomic_tasks.presentation.fastapi.errors import register_error_handlers
from atomic_tasks.presentation.fastapi.routers import health, me


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
    register_error_handlers(app)
    app.include_router(health.router)

    # Всё под /api/v1 требует аутентификации — доступ по умолчанию закрыт.
    api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])
    api_v1.include_router(me.router)
    app.include_router(api_v1)
    return app
