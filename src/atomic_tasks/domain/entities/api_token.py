import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from atomic_tasks.domain.exceptions import InsufficientScopeError, InvalidTokenParamsError

TOKEN_MARKER = "at"  # noqa: S105 — маркер формата, не секрет
PREFIX_LENGTH = 8
SECRET_BYTES = 32
MAX_ACTIVE_TOKENS_PER_USER = 10
DEFAULT_TTL_DAYS = 90
MAX_TTL_DAYS = 365
MAX_NAME_LENGTH = 100
TOUCH_INTERVAL = timedelta(minutes=1)

_PREFIX_ALPHABET = string.ascii_lowercase + string.digits


class TokenScope(StrEnum):
    READ = "read"
    WRITE = "write"

    def allows(self, required: TokenScope) -> bool:
        return self is TokenScope.WRITE or required is TokenScope.READ


@dataclass(kw_only=True, eq=False)
class ApiToken:
    """Personal access token. Секрет не хранится — только SHA-256 от всего токена."""

    id: UUID
    user_id: UUID
    name: str
    prefix: str
    token_hash: str
    scope: TokenScope
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or now < self.expires_at

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now

    def require_scope(self, required: TokenScope) -> None:
        if not self.scope.allows(required):
            raise InsufficientScopeError(required)

    def touch(self, now: datetime) -> bool:
        """Отмечает использование не чаще раза в минуту. True — если запись изменилась."""
        if self.last_used_at is not None and now - self.last_used_at < TOUCH_INTERVAL:
            return False
        self.last_used_at = now
        return True


@dataclass(frozen=True, kw_only=True)
class GeneratedToken:
    raw: str
    prefix: str
    token_hash: str


def generate_token() -> GeneratedToken:
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(PREFIX_LENGTH))
    raw = f"{TOKEN_MARKER}_{prefix}_{secrets.token_urlsafe(SECRET_BYTES)}"
    return GeneratedToken(raw=raw, prefix=prefix, token_hash=hash_token(raw))


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def looks_like_api_token(raw: str) -> bool:
    parts = raw.split("_", 2)
    return len(parts) == 3 and parts[0] == TOKEN_MARKER and len(parts[1]) == PREFIX_LENGTH  # noqa: PLR2004


def validate_token_params(name: str, ttl_days: int | None) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise InvalidTokenParamsError(f"Название токена — от 1 до {MAX_NAME_LENGTH} символов.")
    if ttl_days is not None and not 1 <= ttl_days <= MAX_TTL_DAYS:
        raise InvalidTokenParamsError(f"Срок токена — от 1 до {MAX_TTL_DAYS} дней или бессрочно.")
    return name
