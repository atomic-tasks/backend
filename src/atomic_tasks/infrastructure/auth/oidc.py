"""Проверка access-токенов от IdP (Rauthy) по OIDC discovery и JWKS."""

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

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
    # client_id CIMD-клиентов, которым можно в MCP; запись на "/" — префикс (ADR 0012).
    mcp_trusted_clients: tuple[str, ...] = ()


def _issued_to(payload: dict[str, Any], client_ids: list[str]) -> bool:
    """Токен выдан одному из наших клиентов (Swagger и т.п.), а не по ресурсу MCP."""
    aud = payload["aud"]
    values = [aud] if isinstance(aud, str) else aud
    return any(value in client_ids for value in values)


def _is_trusted_client(azp: object, trusted: tuple[str, ...]) -> bool:
    """client_id CIMD-клиента — https-URL его документа. Точное совпадение или префикс пути.

    Префикс сравнивается только для «чистого» URL: иначе `https://good/prefix/../evil` или
    userinfo/порт/query могли бы увести за пределы доверенного документа.
    """
    if not isinstance(azp, str):
        return False
    if any(azp == entry for entry in trusted if not entry.endswith("/")):
        return True
    try:
        url = urlsplit(azp)
        clean = (
            url.scheme == "https"
            and url.port is None  # ValueError на мусорном порту
            and url.username is None
            and not url.query
            and not url.fragment
            and "/." not in url.path
            and "%2e" not in url.path.lower()  # url crate в Rauthy раскрывает %2e%2e в ".."
        )
    except ValueError:
        return False
    return clean and any(
        entry.endswith("/") and azp.startswith(entry) and len(azp) > len(entry) for entry in trusted
    )


class OidcProvider:
    """Discovery, JWKS и HTTP-запросы к IdP. Один на приложение: кеш общий для проверки и входа."""

    def __init__(self, issuer: str, internal_url: str | None = None) -> None:
        self.issuer = issuer
        self._internal_url = internal_url
        self._discovery: dict[str, Any] | None = None
        self._jwks: PyJWKClient | None = None
        self._lock = asyncio.Lock()

    async def discovery(self) -> dict[str, Any]:
        async with self._lock:
            if self._discovery is None:
                self._discovery = await asyncio.to_thread(
                    self.get_json,
                    f"{self.issuer.rstrip('/')}/.well-known/openid-configuration",
                    None,
                )
            return self._discovery

    async def jwks(self) -> PyJWKClient:
        discovery = await self.discovery()
        if self._jwks is None:
            self._jwks = PyJWKClient(
                self.internal(discovery["jwks_uri"]),
                cache_keys=True,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        return self._jwks

    async def signing_key(self, raw: str) -> Any:
        jwks = await self.jwks()
        return (await asyncio.to_thread(jwks.get_signing_key_from_jwt, raw)).key

    def get_json(self, url: str, bearer: str | None) -> dict[str, Any]:
        request = urllib.request.Request(self.internal(url))  # noqa: S310 — URL из настроек
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        return self._send(request)

    def post_form(self, url: str, form: dict[str, str], *, basic_auth: str) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 — URL из discovery нашего issuer
            self.internal(url),
            data=urlencode(form).encode(),
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        return self._send(request)

    @staticmethod
    def _send(request: urllib.request.Request) -> dict[str, Any]:
        # Тело ответа об ошибке не логируем и не пробрасываем: в нём бывают детали запроса.
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
                data: dict[str, Any] = json.load(response)
        except (OSError, ValueError) as exc:
            raise AuthenticationError("IdP недоступен, попробуйте позже.") from exc
        return data

    def internal(self, url: str) -> str:
        public, internal = self.issuer, self._internal_url
        if not internal:
            return url
        public_root = public.split("/", 3)[:3]
        internal_root = internal.rstrip("/")
        return url.replace("/".join(public_root), internal_root, 1)


class OidcTokenVerifier:
    def __init__(self, config: OidcConfig, provider: OidcProvider | None = None) -> None:
        self._config = config
        self._provider = provider or OidcProvider(config.issuer, config.internal_url)

    async def verify(self, raw: str, *, target: AuthTarget) -> VerifiedClaims:
        audience = self._audience_for(target)
        if not audience:
            raise AuthenticationError("Вход через IdP не настроен.")
        try:
            key = await self._provider.signing_key(raw)
            payload: dict[str, Any] = jwt.decode(
                raw,
                key,
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

        payload = await with_userinfo(self._provider, payload, access_token=raw)
        return claims_from(payload)

    def _audience_for(self, target: AuthTarget) -> list[str]:
        """Наши client id годятся везде; ресурс MCP — только для /mcp (ADR 0012)."""
        audience = list(self._config.audience)
        if target is AuthTarget.MCP and self._config.mcp_resource:
            audience.append(self._config.mcp_resource)
        return audience

    def _require_trusted_client(self, azp: object) -> None:
        if not _is_trusted_client(azp, self._config.mcp_trusted_clients):
            raise AuthenticationError("Этот клиент не может подключаться к MCP.")


async def with_userinfo(
    provider: OidcProvider, payload: dict[str, Any], *, access_token: str
) -> dict[str, Any]:
    """Email, если его нет в токене, — из userinfo. Claims токена важнее."""
    if "email" in payload:
        return payload
    userinfo_url = (await provider.discovery()).get("userinfo_endpoint")
    if not userinfo_url:
        return payload
    userinfo = await asyncio.to_thread(provider.get_json, userinfo_url, access_token)
    return {**userinfo, **payload}


def claims_from(payload: dict[str, Any]) -> VerifiedClaims:
    return VerifiedClaims(
        issuer=payload["iss"],
        subject=str(payload["sub"]),
        email=payload.get("email"),
        email_verified=bool(payload.get("email_verified", False)),
        name=payload.get("name") or payload.get("preferred_username"),
    )
