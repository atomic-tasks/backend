from dataclasses import dataclass
from typing import Protocol

from atomic_tasks.application.dto import AuthTarget


@dataclass(frozen=True, kw_only=True)
class VerifiedClaims:
    """Проверенный access token от IdP. Пользователь определяется только по (issuer, subject)."""

    issuer: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


class TokenVerifier(Protocol):
    async def verify(self, raw: str, *, target: AuthTarget) -> VerifiedClaims:
        """Проверяет подпись, iss, aud, exp. Недействительный токен — AuthenticationError.

        Допустимые `aud` зависят от `target`: токен, выданный для ресурса MCP, не годится для REST.
        """
        ...


class OidcClient(Protocol):
    """Вход через браузер у IdP: authorization code + PKCE, бэкенд — конфиденциальный клиент."""

    async def authorization_url(
        self, *, state: str, code_challenge: str, nonce: str, redirect_uri: str
    ) -> str: ...

    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> VerifiedClaims:
        """Меняет code на токены и проверяет id_token (подпись, iss, aud, exp, nonce).

        Токены IdP наружу не отдаются. Любая ошибка — AuthenticationError.
        """
        ...
