from typing import Annotated

from dishka import AsyncContainer
from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from atomic_tasks.application.dto import Identity
from atomic_tasks.application.services.auth_service import AuthService

_bearer = HTTPBearer(
    auto_error=False,
    description=(
        "Personal access token `at_...`. "
        "Выпускается командой `python -m atomic_tasks tokens create`."
    ),
)


async def authenticate(
    request: Request,
    _: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> Identity:
    """Подключается ко всему /api/v1 на уровне роутера: без аутентификации туда не попасть."""
    container: AsyncContainer = request.state.dishka_container
    auth = await container.get(AuthService)
    return await auth.authenticate(request.headers.get("authorization"))


CurrentIdentity = Annotated[Identity, Depends(authenticate)]
