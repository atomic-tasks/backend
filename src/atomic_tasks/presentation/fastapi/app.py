from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

from atomic_tasks.presentation.fastapi.auth import make_authenticate
from atomic_tasks.presentation.fastapi.docs import add_docs
from atomic_tasks.presentation.fastapi.errors import register_error_handlers
from atomic_tasks.presentation.fastapi.routers import folders, health, me, tasks, tokens


def _operation_id(route: APIRoute) -> str:
    # Стабильные operation_id = имена методов в сгенерированных SDK (web, Flutter, бот).
    return route.name


def create_fastapi_app(
    *,
    version: str,
    debug: bool,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]],
    oidc_issuer: str,
    swagger_client_id: str,
) -> FastAPI:
    app = FastAPI(
        title="AtomicTasks API",
        version=version,
        debug=debug,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        docs_url=None,
        redoc_url=None,
    )
    add_docs(app, swagger_client_id=swagger_client_id)
    register_error_handlers(app)
    app.include_router(health.router)

    # Всё под /api/v1 требует аутентификации — доступ по умолчанию закрыт.
    api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(make_authenticate(oidc_issuer))])
    api_v1.include_router(me.router)
    api_v1.include_router(tokens.router)
    api_v1.include_router(folders.router)
    api_v1.include_router(tasks.router)
    app.include_router(api_v1)
    return app
