"""Вход через браузер у IdP: authorization code + PKCE (S256) по OIDC discovery.

Без Rauthy-специфики: смена IdP (ADR 0009) — только настройки. Бэкенд — конфиденциальный клиент
(`client_secret_basic`). Authorize URL — публичный (его открывает браузер), token endpoint —
серверный запрос, при необходимости через внутренний адрес IdP.
"""

import asyncio
import base64
import secrets
from typing import Any
from urllib.parse import quote_plus, urlencode

import jwt

from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.oidc import VerifiedClaims
from atomic_tasks.infrastructure.auth.oidc import (
    ALLOWED_ALGORITHMS,
    OidcProvider,
    claims_from,
    with_userinfo,
)

SCOPES = "openid email profile"


class OidcCodeFlowClient:
    def __init__(self, provider: OidcProvider, *, client_id: str, client_secret: str) -> None:
        self._provider = provider
        self._client_id = client_id
        # RFC 6749 §2.3.1: id и секрет кодируются как form-urlencoded до base64
        pair = f"{quote_plus(client_id)}:{quote_plus(client_secret)}"
        self._basic_auth = base64.b64encode(pair.encode()).decode()

    async def authorization_url(
        self, *, state: str, code_challenge: str, nonce: str, redirect_uri: str
    ) -> str:
        endpoint = (await self._provider.discovery())["authorization_endpoint"]
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{endpoint}?{urlencode(params)}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> VerifiedClaims:
        discovery = await self._provider.discovery()
        tokens = await asyncio.to_thread(
            self._provider.post_form,
            discovery["token_endpoint"],
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            basic_auth=self._basic_auth,
        )
        id_token, access_token = tokens.get("id_token"), tokens.get("access_token")
        if not isinstance(id_token, str) or not isinstance(access_token, str):
            raise AuthenticationError("IdP не вернул токены.")
        payload = await self._verify_id_token(id_token, nonce=nonce)
        return claims_from(await with_userinfo(self._provider, payload, access_token=access_token))

    async def _verify_id_token(self, raw: str, *, nonce: str) -> dict[str, Any]:
        try:
            key = await self._provider.signing_key(raw)
            payload: dict[str, Any] = jwt.decode(
                raw,
                key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._client_id,
                issuer=self._provider.issuer,
                options={"require": ["exp", "iss", "sub", "aud", "nonce"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("id_token недействителен.") from exc
        claimed_nonce = payload.get("nonce")
        if not isinstance(claimed_nonce, str) or not secrets.compare_digest(
            claimed_nonce.encode(), nonce.encode()
        ):
            raise AuthenticationError("id_token выдан для другого входа.")
        # OIDC Core §3.1.3.7: если azp есть, это должен быть наш клиент
        if "azp" in payload and payload["azp"] != self._client_id:
            raise AuthenticationError("id_token выдан другому клиенту.")
        return payload
