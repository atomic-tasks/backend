from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from atomic_tasks.domain.exceptions import DomainError, UserDisabledError

MAX_DISPLAY_NAME_LENGTH = 200


@dataclass(kw_only=True, eq=False)
class User:
    id: UUID
    display_name: str
    email: str | None
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None = None

    def __post_init__(self) -> None:
        self.display_name = _validate_name(self.display_name)

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None

    def ensure_active(self) -> None:
        if not self.is_active:
            raise UserDisabledError

    def disable(self, now: datetime) -> None:
        if self.disabled_at is None:
            self.disabled_at = now
            self.updated_at = now

    def enable(self, now: datetime) -> None:
        if self.disabled_at is not None:
            self.disabled_at = None
            self.updated_at = now


@dataclass(kw_only=True, eq=False)
class UserIdentity:
    """Вход через IdP: пользователь определяется только по (issuer, subject), не по email."""

    id: UUID
    user_id: UUID
    issuer: str
    subject: str
    created_at: datetime
    last_login_at: datetime | None = None


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise DomainError(f"Имя должно быть от 1 до {MAX_DISPLAY_NAME_LENGTH} символов.")
    return name
