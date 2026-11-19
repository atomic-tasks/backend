"""Вход через браузер у IdP: обмен кода и проверка id_token (aud, nonce, подпись) на мини-IdP."""

import base64
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.infrastructure.auth.oidc import OidcProvider
from atomic_tasks.infrastructure.auth.oidc_client import OidcCodeFlowClient

CLIENT_ID = "atomic-tasks-web"
CLIENT_SECRET = "s3cret:with/odd chars"  # noqa: S105 — тестовое значение
NONCE = "nonce-1"
REDIRECT_URI = "https://atomic.test/api/v1/auth/callback"
KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()


class FakeIdp:
    def __init__(self) -> None:
        self.base = ""
        self.claims: dict[str, Any] = {}
        self.key: Any = KEY
        self.token_requests: list[tuple[str, dict[str, list[str]]]] = []

    @property
    def issuer(self) -> str:
        return f"{self.base}/auth/v1/"

    def id_token(self) -> str:
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "sub": "user-1",
            "aud": CLIENT_ID,
            "exp": int(time.time()) + 300,
            "nonce": NONCE,
            "email": "a@example.com",
            "email_verified": True,
            **self.claims,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.key, algorithm="EdDSA", headers={"kid": "k1"})


@pytest.fixture
def idp() -> Iterator[FakeIdp]:
    fake = FakeIdp()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            jwk = {**json.loads(OKPAlgorithm.to_jwk(KEY.public_key())), "kid": "k1"}
            routes: dict[str, Any] = {
                "/auth/v1/.well-known/openid-configuration": {
                    "issuer": fake.issuer,
                    "authorization_endpoint": f"{fake.issuer}oidc/authorize",
                    "token_endpoint": f"{fake.issuer}oidc/token",
                    "jwks_uri": f"{fake.issuer}oidc/certs",
                },
                "/auth/v1/oidc/certs": {"keys": [jwk]},
            }
            self._reply(200 if self.path in routes else 404, routes.get(self.path, {}))

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            fake.token_requests.append((self.headers["Authorization"], parse_qs(body)))
            self._reply(200, {"access_token": "at", "id_token": fake.id_token()})

        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    fake.base = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield fake
    server.shutdown()


def _client(idp: FakeIdp) -> OidcCodeFlowClient:
    return OidcCodeFlowClient(
        OidcProvider(idp.issuer), client_id=CLIENT_ID, client_secret=CLIENT_SECRET
    )


async def _exchange(idp: FakeIdp) -> Any:
    return await _client(idp).exchange_code(
        code="c", code_verifier="v" * 43, nonce=NONCE, redirect_uri=REDIRECT_URI
    )


async def test_authorization_url_carries_pkce_and_nonce(idp: FakeIdp) -> None:
    url = await _client(idp).authorization_url(
        state="st", code_challenge="ch", nonce=NONCE, redirect_uri=REDIRECT_URI
    )
    query = parse_qs(urlsplit(url).query)
    assert url.startswith(f"{idp.issuer}oidc/authorize?")
    assert query["code_challenge_method"] == ["S256"]
    assert (query["state"], query["nonce"], query["client_id"]) == (["st"], [NONCE], [CLIENT_ID])


async def test_valid_exchange(idp: FakeIdp) -> None:
    claims = await _exchange(idp)
    assert (claims.issuer, claims.subject, claims.email) == (idp.issuer, "user-1", "a@example.com")
    authorization, form = idp.token_requests[-1]
    assert form["code_verifier"] == ["v" * 43]
    user, _, password = (
        base64.b64decode(authorization.removeprefix("Basic ")).decode().partition(":")
    )
    assert (user, password) == (CLIENT_ID, "s3cret%3Awith%2Fodd+chars")


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "atomic-tasks-swagger"},
        {"nonce": "someone-elses-login"},
        {"nonce": None},
        {"azp": "atomic-tasks-swagger", "aud": [CLIENT_ID, "atomic-tasks-swagger"]},
        {"iss": "https://evil.example/auth/v1/"},
        {"exp": int(time.time()) - 10},
    ],
)
async def test_rejected_id_tokens(idp: FakeIdp, claims: dict[str, Any]) -> None:
    idp.claims = claims
    with pytest.raises(AuthenticationError):
        await _exchange(idp)


async def test_id_token_signed_by_other_key_is_rejected(idp: FakeIdp) -> None:
    idp.key = OTHER_KEY
    with pytest.raises(AuthenticationError):
        await _exchange(idp)
