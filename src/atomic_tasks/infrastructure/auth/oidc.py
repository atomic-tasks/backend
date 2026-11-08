"""Проверка access-токенов от IdP (Rauthy) по OIDC discovery и JWKS."""

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.oidc import VerifiedClaims

ALLOWED_ALGORITHMS = ["EdDSA", "RS256", "ES256"]  # симметричные (HS*) запрещены
HTTP_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, kw_only=True)
class OidcConfig:
    # Сравнивается с claim iss посимвольно — включая слеш в конце (у Rauthy он есть).
    issuer: str
    audience: list[str]
    # Адрес IdP изнутри Docker-сети, если публичный (issuer) оттуда недоступен.
    internal_url: str | None = None


class OidcTokenVerifier:
    def __init__(self, config: OidcConfig) -> None:
        self._config = config
        self._jwks: PyJWKClient | None = None
        self._userinfo_url: str | None = None
        self._lock = asyncio.Lock()

    async def verify(self, raw: str) -> VerifiedClaims:
        if not self._config.audience:
            raise AuthenticationError("Вход через IdP не настроен.")
        jwks = await self._jwks_client()
        try:
            key = await asyncio.to_thread(jwks.get_signing_key_from_jwt, raw)
            payload: dict[str, Any] = jwt.decode(
                raw,
                key.key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._config.audience,
                issuer=self._config.issuer,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Токен недействителен или истёк.") from exc

        if "email" not in payload and self._userinfo_url:
            payload = {**await asyncio.to_thread(self._fetch_userinfo, raw), **payload}
        return VerifiedClaims(
            issuer=payload["iss"],
            subject=str(payload["sub"]),
            email=payload.get("email"),
            email_verified=bool(payload.get("email_verified", False)),
            name=payload.get("name") or payload.get("preferred_username"),
        )

    async def _jwks_client(self) -> PyJWKClient:
        async with self._lock:
            if self._jwks is None:
                discovery = await asyncio.to_thread(
                    self._get_json,
                    f"{self._config.issuer.rstrip('/')}/.well-known/openid-configuration",
                    None,
                )
                self._userinfo_url = discovery.get("userinfo_endpoint")
                self._jwks = PyJWKClient(
                    self._internal(discovery["jwks_uri"]),
                    cache_keys=True,
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            return self._jwks

    def _fetch_userinfo(self, raw: str) -> dict[str, Any]:
        assert self._userinfo_url is not None  # noqa: S101
        return self._get_json(self._userinfo_url, raw)

    def _get_json(self, url: str, bearer: str | None) -> dict[str, Any]:
        request = urllib.request.Request(self._internal(url))  # noqa: S310 — URL из настроек
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
                data: dict[str, Any] = json.load(response)
        except OSError as exc:
            raise AuthenticationError("IdP недоступен, попробуйте позже.") from exc
        return data

    def _internal(self, url: str) -> str:
        public, internal = self._config.issuer, self._config.internal_url
        if not internal:
            return url
        public_root = public.split("/", 3)[:3]
        internal_root = internal.rstrip("/")
        return url.replace("/".join(public_root), internal_root, 1)
