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
