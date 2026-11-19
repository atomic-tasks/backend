"""Сессии браузера и временные данные входа (спека 0008, ADR 0013)."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import unquote
from uuid import UUID

SECRET_BYTES = 32
IDLE_TTL = timedelta(days=30)  # без активности
MAX_TTL = timedelta(days=90)  # со входа, продление не помогает
LOGIN_TTL = timedelta(minutes=10)  # от редиректа в IdP до callback
TOUCH_INTERVAL = timedelta(minutes=1)
MAX_RETURN_TO_LENGTH = 2048

_PRINTABLE_ASCII = frozenset(chr(code) for code in range(0x21, 0x7F))  # без пробела и управляющих


@dataclass(kw_only=True, eq=False)
class BrowserSession:
    """Вход через браузер. Секрет живёт только в httpOnly-cookie, в базе — его SHA-256."""

    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime  # абсолютный предел

    @classmethod
    def new(cls, *, id: UUID, user_id: UUID, token_hash: str, now: datetime) -> BrowserSession:
        return cls(
            id=id,
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            last_seen_at=now,
            expires_at=now + MAX_TTL,
        )

    def is_active(self, now: datetime) -> bool:
        return now < self.expires_at and now < self.last_seen_at + IDLE_TTL

    def touch(self, now: datetime) -> bool:
        """Продлевает сессию не чаще раза в минуту. True — если запись изменилась."""
        if now - self.last_seen_at < TOUCH_INTERVAL:
            return False
        self.last_seen_at = now
        return True


@dataclass(kw_only=True, eq=False)
class LoginAttempt:
    """Вход, начатый в браузере и ещё не завершённый. Одноразовый: читается вместе с удалением."""

    id: UUID
    state_hash: str
    code_verifier: str
    nonce: str
    return_to: str
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


def generate_secret() -> str:
    """Случайный секрет для cookie сессии, state, nonce и PKCE-verifier (43 символа base64url)."""
    return secrets.token_urlsafe(SECRET_BYTES)


def pkce_challenge(verifier: str) -> str:
    """code_challenge для метода S256 (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def safe_return_to(raw: str | None) -> str:
    """Куда вернуть браузер после входа: только путь на нашем хосте, иначе `/`.

    `//host` и `/\\host` браузер понимает как другой хост. Проверяем и раскодированную строку:
    `/%2F/evil` безопасен сам по себе, но не после прокси, который раскодирует `%2F`.
    Только печатный ASCII (остальное браузер кодирует сам): иначе ломается заголовок Location.
    """
    if not raw or len(raw) > MAX_RETURN_TO_LENGTH or not set(raw) <= _PRINTABLE_ASCII:
        return "/"
    decoded = unquote(raw)
    for candidate in (raw, decoded):
        if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
            return "/"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in decoded):  # noqa: PLR2004
        return "/"
    return raw
