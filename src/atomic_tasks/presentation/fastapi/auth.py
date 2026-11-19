from collections.abc import Awaitable, Callable
from typing import Annotated

from dishka import AsyncContainer
from fastapi import Depends, Request, Response, Security
from fastapi.security import (
    APIKeyCookie,
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
)

from atomic_tasks.application.dto import AuthMethod, AuthTarget, Identity
from atomic_tasks.application.errors import PermissionDeniedError
from atomic_tasks.application.services.auth_service import AuthService

# __Host-: только Secure, Path=/ и без Domain — cookie не уйдёт на поддомены и API_HOST (ADR 0013)
SESSION_COOKIE = "__Host-at_session"
LOGIN_COOKIE = "__Host-at_login"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_bearer = HTTPBearer(
    auto_error=False,
    description=(
        "Personal access token `at_...` (выпускается в /api/v1/tokens после входа через IdP "
        "или командой `python -m atomic_tasks tokens create`)."
    ),
)
_session_cookie = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    description=(
        "Сессия браузера: ставится после входа через `/api/v1/auth/login`, только на хосте сайта. "
        "Небезопасные методы требуют заголовок `Origin` сайта."
    ),
)


def set_cookie(response: Response, name: str, value: str, *, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="lax"
    )


def delete_cookie(response: Response, name: str) -> None:
    # Браузер удалит __Host- cookie, только если атрибуты совпадают с теми, с которыми её ставили
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")


def require_same_origin(request: Request, web_origin: str) -> None:
    """CSRF: небезопасный запрос с cookie должен прийти со страницы нашего сайта.

    Сравниваем только Origin: Host может переписать прокси (Vite changeOrigin, Traefik).
    """
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("origin") != web_origin:
        raise PermissionDeniedError("Запрос с cookie разрешён только со страниц сайта.")


def make_authenticate(issuer: str, web_origin: str | None) -> Callable[..., Awaitable[Identity]]:
    """Зависимость аутентификации для всего /api/v1: вход через IdP, PAT и cookie сессии."""
    base = issuer.rstrip("/")
    oauth = OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{base}/oidc/authorize",
        tokenUrl=f"{base}/oidc/token",
        scopes={"openid": "OpenID", "email": "Email", "profile": "Профиль"},
        auto_error=False,
        description="Вход через IdP (Rauthy).",
    )

    async def authenticate(
        request: Request,
        _oauth: Annotated[str | None, Security(oauth)],
        _pat: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
        session_cookie: Annotated[str | None, Security(_session_cookie)],
    ) -> Identity:
        cached: Identity | None = getattr(request.state, "identity", None)
        if cached is not None:
            return cached
        container: AsyncContainer = request.state.dishka_container
        auth = await container.get(AuthService)
        identity = await auth.authenticate(
            request.headers.get("authorization"),
            target=AuthTarget.API,
            session_cookie=session_cookie if web_origin else None,
        )
        if identity.method is AuthMethod.COOKIE:
            assert web_origin is not None  # noqa: S101 — cookie без origin не принимается выше
            require_same_origin(request, web_origin)
        request.state.identity = identity
        return identity

    return authenticate


async def current_identity(request: Request) -> Identity:
    """Identity, установленная зависимостью роутера /api/v1."""
    identity: Identity = request.state.identity
    return identity


CurrentIdentity = Annotated[Identity, Depends(current_identity)]
