"""Вход через браузер (спека 0008): редиректы и cookie. Сценарий — в BrowserLoginService."""

from typing import Annotated
from urllib.parse import urlsplit

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from atomic_tasks.application.errors import LoginFailedError, NotFoundError
from atomic_tasks.application.services.browser_login_service import BrowserLoginService
from atomic_tasks.domain.entities.browser_session import LOGIN_TTL, MAX_TTL
from atomic_tasks.presentation.fastapi.auth import (
    LOGIN_COOKIE,
    SESSION_COOKIE,
    delete_cookie,
    require_same_origin,
    set_cookie,
)


def make_router(web_origin: str | None) -> APIRouter:
    """Без web_origin вход через браузер выключен: все эндпоинты отвечают 404."""

    def require_enabled() -> str:
        if web_origin is None:
            raise NotFoundError("Вход через браузер")
        return web_origin

    origin_dep = Annotated[str, Depends(require_enabled)]
    router = APIRouter(
        prefix="/api/v1/auth",
        tags=["auth"],
        route_class=DishkaRoute,
        dependencies=[Depends(require_enabled)],
    )

    @router.get(
        "/login",
        status_code=status.HTTP_302_FOUND,
        response_class=RedirectResponse,
        responses={302: {"description": "Редирект в IdP; ставит cookie входа."}},
    )
    async def login(
        service: FromDishka[BrowserLoginService],
        return_to: str | None = None,
    ) -> RedirectResponse:
        """Начать вход: браузер уходит в IdP и возвращается на `return_to` (путь на сайте)."""
        started = await service.start(return_to)
        response = RedirectResponse(started.redirect_url, status_code=status.HTTP_302_FOUND)
        set_cookie(response, LOGIN_COOKIE, started.state, max_age=int(LOGIN_TTL.total_seconds()))
        return response

    @router.get(
        "/callback",
        status_code=status.HTTP_302_FOUND,
        response_class=RedirectResponse,
        responses={
            302: {
                "description": (
                    "На `return_to` с cookie сессии "
                    "или на `/?login_error=access_denied|expired|failed`."
                ),
            },
        },
    )
    async def callback(  # noqa: PLR0917 — параметры redirect от IdP
        request: Request,
        origin: origin_dep,
        service: FromDishka[BrowserLoginService],
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        """Возврат из IdP. Вызывается браузером, не клиентом API."""
        try:
            result = await service.finish(
                state_cookie=request.cookies.get(LOGIN_COOKIE),
                state=state,
                code=code,
                idp_error=error,
            )
        except LoginFailedError as exc:
            response = _redirect(origin, f"/?login_error={exc.code}")
        else:
            response = _redirect(origin, result.return_to)
            # Срок держит сервер; Max-Age — чтобы cookie пережила перезапуск браузера
            set_cookie(
                response,
                SESSION_COOKIE,
                result.session_secret,
                max_age=int(MAX_TTL.total_seconds()),
            )
        delete_cookie(response, LOGIN_COOKIE)
        return response

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        request: Request,
        origin: origin_dep,
        service: FromDishka[BrowserLoginService],
    ) -> Response:
        """Выйти: удалить сессию и cookie. Без сессии — тоже 204."""
        # Cookie читаем из запроса, а не параметром: иначе она попадёт в SDK как обычный аргумент
        if session_cookie := request.cookies.get(SESSION_COOKIE):
            require_same_origin(request, origin)
            await service.logout(session_cookie)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        delete_cookie(response, SESSION_COOKIE)
        # "cookies" не шлём: директива стёрла бы cookie всего домена, включая сессию IdP
        response.headers["Clear-Site-Data"] = '"cache", "storage"'
        return response

    return router


def _redirect(origin: str, path: str) -> RedirectResponse:
    """Редирект только на сайт. `path` уже проверен в домене (safe_return_to); здесь — вторая
    линия: итоговый URL обязан указывать на тот же scheme и host, что и origin сайта."""
    url = f"{origin}{path}"
    target, site = urlsplit(url), urlsplit(origin)
    if (target.scheme, target.netloc) != (site.scheme, site.netloc):
        url = f"{origin}/"
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.headers["Cache-Control"] = "no-store"
    return response
