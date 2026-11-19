"""Сессии браузера через REST (спека 0008): вход, изоляция, CSRF, приоритет Bearer, выход."""

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.e2e.test_auth import MCP_HEADERS, MCP_INIT
from tests.fakes import FakeIdpProvider, FakeOidcClientProvider

from atomic_tasks.config.app import create_app
from atomic_tasks.config.settings import Settings, WebSettings

ORIGIN = "https://atomic.test"
SESSION = "__Host-at_session"
LOGIN = "__Host-at_login"
ALICE_CODE = "alice-sub:alice@example.com"
BOB_CODE = "bob-sub:bob@example.com"


def _app(settings: Settings, origin: str | None) -> Any:
    web = WebSettings(origin=origin, client_secret=SecretStr("s")) if origin else WebSettings()
    return create_app(
        settings.model_copy(update={"web": web}), FakeIdpProvider(), FakeOidcClientProvider()
    )


@pytest.fixture
def client(empty_db: Settings, settings_with_allowlist: Settings) -> Iterator[TestClient]:
    # https: иначе cookie-jar httpx не отправит Secure-cookie обратно
    with TestClient(_app(settings_with_allowlist, ORIGIN), base_url=ORIGIN) as client:
        yield client


def _login(client: TestClient, code: str, return_to: str = "/folders/1") -> str:
    """Вход как из браузера; возвращает секрет сессии и очищает cookie-jar."""
    started = client.get(
        "/api/v1/auth/login", params={"return_to": return_to}, follow_redirects=False
    )
    assert started.status_code == 302, started.text
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    done = client.get(
        "/api/v1/auth/callback", params={"code": code, "state": state}, follow_redirects=False
    )
    assert done.status_code == 302, done.text
    assert done.headers["location"] == f"{ORIGIN}{return_to}"
    secret = client.cookies[SESSION]
    client.cookies.clear()
    return secret


def _cookie(secret: str, *, origin: str | None = ORIGIN) -> dict[str, str]:
    headers = {"Cookie": f"{SESSION}={secret}"}
    return {**headers, "Origin": origin} if origin else headers


def test_login_sets_host_only_httponly_cookies(client: TestClient) -> None:
    started = client.get("/api/v1/auth/login", follow_redirects=False)
    login_cookie = started.headers["set-cookie"]
    assert login_cookie.startswith(f"{LOGIN}=")
    for attr in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=600"):
        assert attr in login_cookie
    assert "Domain" not in login_cookie

    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    done = client.get(
        "/api/v1/auth/callback", params={"code": ALICE_CODE, "state": state}, follow_redirects=False
    )
    set_cookies = done.headers.get_list("set-cookie")
    session_cookie = next(c for c in set_cookies if c.startswith(f"{SESSION}="))
    for attr in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert attr in session_cookie
    assert any(c.startswith(f'{LOGIN}=""') for c in set_cookies)  # cookie входа стёрта
    assert done.headers["location"] == f"{ORIGIN}/"


def test_failed_login_redirects_with_code(client: TestClient) -> None:
    denied = client.get(
        "/api/v1/auth/callback",
        params={"error": "access_denied", "state": "x"},
        follow_redirects=False,
    )
    assert denied.headers["location"] == f"{ORIGIN}/?login_error=access_denied"
    no_cookie = client.get(
        "/api/v1/auth/callback", params={"code": ALICE_CODE, "state": "x"}, follow_redirects=False
    )
    assert no_cookie.headers["location"] == f"{ORIGIN}/?login_error=expired"
    stranger = _login_failure(client, "eve-sub:eve@example.com")
    assert stranger == f"{ORIGIN}/?login_error=access_denied"


def _login_failure(client: TestClient, code: str) -> str:
    started = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    done = client.get(
        "/api/v1/auth/callback", params={"code": code, "state": state}, follow_redirects=False
    )
    client.cookies.clear()
    return str(done.headers["location"])


def test_open_redirect_is_not_possible(client: TestClient) -> None:
    started = client.get(
        "/api/v1/auth/login", params={"return_to": "//evil.example"}, follow_redirects=False
    )
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    done = client.get(
        "/api/v1/auth/callback", params={"code": ALICE_CODE, "state": state}, follow_redirects=False
    )
    assert done.headers["location"] == f"{ORIGIN}/"


def test_alice_cookie_cannot_see_or_change_bob_data(client: TestClient) -> None:
    alice, bob = _login(client, ALICE_CODE), _login(client, BOB_CODE)
    bob_root = client.get("/api/v1/folders/root", headers=_cookie(bob)).json()["id"]
    bob_folder = client.post(
        "/api/v1/folders", json={"parent_id": bob_root, "title": "b"}, headers=_cookie(bob)
    )
    assert bob_folder.status_code == 201, bob_folder.text
    folder_id = bob_folder.json()["id"]

    me = client.get("/api/v1/me", headers=_cookie(alice)).json()
    assert me["email"] == "alice@example.com"
    assert client.get(f"/api/v1/folders/{folder_id}", headers=_cookie(alice)).status_code == 404
    patch = client.patch(
        f"/api/v1/folders/{folder_id}", json={"title": "x"}, headers=_cookie(alice)
    )
    assert patch.status_code == 404
    delete = client.delete(f"/api/v1/folders/{folder_id}", headers=_cookie(alice))
    assert delete.status_code == 404


def test_unsafe_cookie_request_requires_site_origin(client: TestClient) -> None:
    secret = _login(client, ALICE_CODE)
    url, body = "/api/v1/tokens", {"name": "cli"}
    assert client.post(url, json=body, headers=_cookie(secret, origin=None)).status_code == 403
    evil = _cookie(secret, origin="https://evil.example")
    assert client.post(url, json=body, headers=evil).status_code == 403
    # Сессия браузера — интерактивный вход: можно выпускать PAT
    assert client.post(url, json=body, headers=_cookie(secret)).status_code == 201
    assert client.get(url, headers=_cookie(secret, origin=None)).status_code == 200


def test_bearer_wins_over_cookie(client: TestClient) -> None:
    alice = _login(client, ALICE_CODE)
    bob_bearer = {"Authorization": "Bearer jwt:bob-sub:bob@example.com"}
    headers = {**_cookie(alice, origin=None), **bob_bearer}
    assert client.get("/api/v1/me", headers=headers).json()["email"] == "bob@example.com"
    # Bearer-запрос не проверяет Origin
    assert client.post("/api/v1/tokens", json={"name": "x"}, headers=headers).status_code == 201
    broken_bearer = {**_cookie(alice), "Authorization": "Bearer at_abcd1234_wrong"}
    assert client.get("/api/v1/me", headers=broken_bearer).status_code == 401


def test_mcp_ignores_cookie(client: TestClient) -> None:
    secret = _login(client, ALICE_CODE)
    response = client.post("/mcp", json=MCP_INIT, headers={**MCP_HEADERS, **_cookie(secret)})
    assert response.status_code == 401


def test_logout(client: TestClient) -> None:
    secret = _login(client, ALICE_CODE)
    assert (
        client.post("/api/v1/auth/logout", headers=_cookie(secret, origin=None)).status_code == 403
    )
    response = client.post("/api/v1/auth/logout", headers=_cookie(secret))
    assert response.status_code == 204
    assert response.headers["clear-site-data"] == '"cache", "storage"'
    assert response.headers["set-cookie"].startswith(f'{SESSION}=""')
    assert client.get("/api/v1/me", headers=_cookie(secret)).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204  # без сессии — тоже 204


def test_browser_login_disabled_without_origin(
    empty_db: Settings, settings_with_allowlist: Settings
) -> None:
    with TestClient(_app(settings_with_allowlist, ORIGIN), base_url=ORIGIN) as enabled:
        secret = _login(enabled, ALICE_CODE)
    with TestClient(_app(settings_with_allowlist, None), base_url=ORIGIN) as client:
        for method, path in [("GET", "login"), ("GET", "callback"), ("POST", "logout")]:
            response = client.request(method, f"/api/v1/auth/{path}", follow_redirects=False)
            assert response.status_code == 404, path
        assert client.get("/api/v1/me", headers=_cookie(secret)).status_code == 401
