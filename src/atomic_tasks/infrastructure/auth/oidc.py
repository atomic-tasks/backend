"""Проверка access-токенов от IdP (Rauthy) по OIDC discovery и JWKS."""

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient

from atomic_tasks.application.dto import AuthTarget
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
    # Публичный адрес ресурса MCP (RFC 8707). Токен с таким aud принимается только на /mcp.
    mcp_resource: str | None = None
    # Хосты документов CIMD-клиентов, которым можно выдавать доступ к MCP (ADR 0012).
    mcp_trusted_client_hosts: frozenset[str] = frozenset()


def _issued_to(payload: dict[str, Any], client_ids: list[str]) -> bool:
    """Токен выдан одному из наших клиентов (Swagger и т.п.), а не по ресурсу MCP."""
    aud = payload["aud"]
    values = [aud] if isinstance(aud, str) else aud
    return any(value in client_ids for value in values)


class OidcTokenVerifier:
    def __init__(self, config: OidcConfig) -> None:
        self._config = config
        self._jwks: PyJWKClient | None = None
        self._userinfo_url: str | None = None
        self._lock = asyncio.Lock()

    async def verify(self, raw: str, *, target: AuthTarget) -> VerifiedClaims:
        audience = self._audience_for(target)
        if not audience:
            raise AuthenticationError("Вход через IdP не настроен.")
        jwks = await self._jwks_client()
        try:
            key = await asyncio.to_thread(jwks.get_signing_key_from_jwt, raw)
            payload: dict[str, Any] = jwt.decode(
                raw,
                key.key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=audience,
                issuer=self._config.issuer,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Токен недействителен или истёк.") from exc

        if not _issued_to(payload, self._config.audience):
            # Принят только по ресурсу MCP — значит, клиент зарегистрировался сам (CIMD).
            # Rauthy выдаёт таким код без экрана согласия, поэтому доверяем лишь известным хостам.
            self._require_trusted_client(payload.get("azp"))

        if "email" not in payload and self._userinfo_url:
            payload = {**await asyncio.to_thread(self._fetch_userinfo, raw), **payload}
        return VerifiedClaims(
            issuer=payload["iss"],
            subject=str(payload["sub"]),
            email=payload.get("email"),
            email_verified=bool(payload.get("email_verified", False)),
            name=payload.get("name") or payload.get("preferred_username"),
        )

    def _audience_for(self, target: AuthTarget) -> list[str]:
        """Наши client id годятся везде; ресурс MCP — только для /mcp (ADR 0012)."""
        audience = list(self._config.audience)
        if target is AuthTarget.MCP and self._config.mcp_resource:
            audience.append(self._config.mcp_resource)
        return audience

    def _require_trusted_client(self, azp: object) -> None:
        """client_id CIMD-клиента — https-URL его документа; доверяем только хосту из настройки."""
        try:
            url = urlsplit(azp) if isinstance(azp, str) else None
            trusted = (
                url is not None
                and url.scheme == "https"
                and url.port is None  # ValueError на мусорном порту
                and url.username is None
                and (url.hostname or "") in self._config.mcp_trusted_client_hosts
            )
        except ValueError:
            trusted = False
        if not trusted:
            raise AuthenticationError("Этот клиент не может подключаться к MCP.")

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
