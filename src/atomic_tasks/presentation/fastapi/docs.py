from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse

OAUTH2_REDIRECT_URL = "/docs/oauth2-redirect"

# Swagger UI добавляет к запросу токена X-Requested-With, а Rauthy не разрешает его в CORS.
# Заголовок не нужен ни нам, ни IdP — убираем его перед отправкой.
_STRIP_HEADER = """
        requestInterceptor: (request) => {
            delete request.headers["X-Requested-With"];
            return request;
        },
    presets: ["""


def add_docs(app: FastAPI, *, swagger_client_id: str) -> None:
    """/docs со входом через IdP (PKCE). Стандартные docs FastAPI отключены в create_fastapi_app."""

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        body = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{app.title} — docs",
            oauth2_redirect_url=OAUTH2_REDIRECT_URL,
            init_oauth={
                "clientId": swagger_client_id,
                "usePkceWithAuthorizationCodeGrant": True,
                "scopes": "openid email profile",
            },
        ).body
        html = bytes(body).decode()
        return HTMLResponse(html.replace("\n    presets: [", _STRIP_HEADER, 1))

    @app.get(OAUTH2_REDIRECT_URL, include_in_schema=False)
    async def swagger_ui_redirect() -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()
