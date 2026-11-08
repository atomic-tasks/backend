"""Проверка JWT по JWKS: подпись, iss, aud, exp и запрет симметричных алгоритмов."""

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.infrastructure.auth.oidc import OidcConfig, OidcTokenVerifier

AUDIENCE = "atomic-tasks-web"
KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()


def _jwk() -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(OKPAlgorithm.to_jwk(KEY.public_key()))
    return {**jwk, "kid": "k1", "alg": "EdDSA", "use": "sig"}


@pytest.fixture(scope="module")
def idp() -> Iterator[str]:
    """Мини-IdP: discovery, JWKS и userinfo на локальном порту."""
    state: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            base = state["base"]
            routes: dict[str, Any] = {
                "/auth/v1/.well-known/openid-configuration": {
                    "issuer": f"{base}/auth/v1",
                    "jwks_uri": f"{base}/auth/v1/oidc/certs",
                    "userinfo_endpoint": f"{base}/auth/v1/oidc/userinfo",
                },
                "/auth/v1/oidc/certs": {"keys": [_jwk()]},
                "/auth/v1/oidc/userinfo": {"email": "u@example.com", "email_verified": True},
            }
            body = json.dumps(routes.get(self.path, {})).encode()
            self.send_response(200 if self.path in routes else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state["base"] = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state["base"]
    server.shutdown()


def _token(idp: str, *, key: Any = KEY, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "iss": f"{idp}/auth/v1",
        "sub": "user-1",
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "email": "a@example.com",
        "email_verified": True,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": "k1"})


def _verifier(idp: str, **overrides: Any) -> OidcTokenVerifier:
    params: dict[str, Any] = {"issuer": f"{idp}/auth/v1", "audience": [AUDIENCE]}
    params.update(overrides)
    return OidcTokenVerifier(OidcConfig(**params))


async def test_valid_token(idp: str) -> None:
    claims = await _verifier(idp).verify(_token(idp))
    assert (claims.issuer, claims.subject, claims.email) == (
        f"{idp}/auth/v1",
        "user-1",
        "a@example.com",
    )
    assert claims.email_verified


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example/auth/v1"},
        {"exp": int(time.time()) - 10},
        {"key": OTHER_KEY},
    ],
)
async def test_rejected_tokens(idp: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(AuthenticationError):
        await _verifier(idp).verify(_token(idp, **overrides))


async def test_symmetric_algorithm_is_rejected(idp: str) -> None:
    forged = jwt.encode(
        {"iss": f"{idp}/auth/v1", "sub": "x", "aud": AUDIENCE, "exp": int(time.time()) + 60},
        "secret",
        algorithm="HS256",
        headers={"kid": "k1"},
    )
    with pytest.raises(AuthenticationError):
        await _verifier(idp).verify(forged)


async def test_issuer_is_compared_exactly_including_trailing_slash(idp: str) -> None:
    rauthy_style = await _verifier(idp, issuer=f"{idp}/auth/v1/").verify(
        _token(idp, iss=f"{idp}/auth/v1/"),
    )
    assert rauthy_style.issuer == f"{idp}/auth/v1/"
    with pytest.raises(AuthenticationError):
        await _verifier(idp).verify(_token(idp, iss=f"{idp}/auth/v1/"))


async def test_no_audience_configured_means_idp_login_disabled(idp: str) -> None:
    with pytest.raises(AuthenticationError):
        await _verifier(idp, audience=[]).verify(_token(idp))


async def test_email_from_userinfo_when_not_in_token(idp: str) -> None:
    claims = await _verifier(idp).verify(_token(idp, email=None, email_verified=None))
    assert claims.email == "u@example.com"
    assert claims.email_verified


async def test_internal_url_is_used_for_server_side_requests(idp: str) -> None:
    # Публичный issuer недоступен, ключи берутся по внутреннему адресу; iss в токене — публичный.
    public = "http://localhost:59999"
    verifier = OidcTokenVerifier(
        OidcConfig(issuer=f"{public}/auth/v1", audience=[AUDIENCE], internal_url=idp),
    )
    with pytest.raises(
        AuthenticationError
    ):  # discovery отдаёт issuer idp, а не public — iss не совпадёт
        await verifier.verify(_token(idp))
    claims = await verifier.verify(_token(idp, iss=f"{public}/auth/v1"))
    assert claims.subject == "user-1"
