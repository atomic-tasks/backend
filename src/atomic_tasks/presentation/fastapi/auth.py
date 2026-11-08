from collections.abc import Awaitable, Callable
from typing import Annotated

from dishka import AsyncContainer
from fastapi import Depends, Request, Security
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
)

from atomic_tasks.application.dto import Identity
from atomic_tasks.application.services.auth_service import AuthService

_bearer = HTTPBearer(
    auto_error=False,
    description=(
        "Personal access token `at_...` (выпускается в /api/v1/tokens после входа через IdP "
        "или командой `python -m atomic_tasks tokens create`)."
    ),
)


def make_authenticate(issuer: str) -> Callable[..., Awaitable[Identity]]:
    """Зависимость аутентификации для всего /api/v1. Две схемы в Swagger: вход через IdP и PAT."""
    oauth = OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{issuer}/oidc/authorize",
        tokenUrl=f"{issuer}/oidc/token",
        scopes={"openid": "OpenID", "email": "Email", "profile": "Профиль"},
        auto_error=False,
        description="Вход через IdP (Rauthy).",
    )

    async def authenticate(
        request: Request,
        _oauth: Annotated[str | None, Security(oauth)],
        _pat: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    ) -> Identity:
        cached: Identity | None = getattr(request.state, "identity", None)
        if cached is not None:
            return cached
        container: AsyncContainer = request.state.dishka_container
        auth = await container.get(AuthService)
        identity = await auth.authenticate(request.headers.get("authorization"))
        request.state.identity = identity
        return identity

    return authenticate


async def current_identity(request: Request) -> Identity:
    """Identity, установленная зависимостью роутера /api/v1."""
    identity: Identity = request.state.identity
    return identity


CurrentIdentity = Annotated[Identity, Depends(current_identity)]
