from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from atomic_tasks.application.errors import PermissionDeniedError
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.domain.exceptions import InsufficientScopeError


class AuthMethod(StrEnum):
    PAT = "pat"
    SESSION = "session"  # JWT от IdP


@dataclass(frozen=True, kw_only=True)
class Identity:
    """Кто выполняет запрос и с какими правами."""

    user_id: UUID
    scope: TokenScope
    method: AuthMethod

    def require_scope(self, required: TokenScope) -> None:
        if not self.scope.allows(required):
            raise InsufficientScopeError(required)

    def require_session(self) -> None:
        """Только вход через IdP: утёкший PAT не должен выпускать и отзывать токены."""
        if self.method is not AuthMethod.SESSION:
            raise PermissionDeniedError(
                "Это действие доступно только после входа через браузер, не по токену."
            )


@dataclass(frozen=True, kw_only=True)
class TokenInfo:
    id: UUID
    name: str
    prefix: str
    scope: TokenScope
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class CreatedToken:
    info: TokenInfo
    token: str  # показывается один раз


@dataclass(frozen=True, kw_only=True)
class UserInfo:
    id: UUID
    display_name: str
    email: str | None
    created_at: datetime
    disabled: bool


@dataclass(frozen=True, kw_only=True)
class FolderInfo:
    id: UUID
    parent_id: UUID | None  # None — корень
    title: str
    description: str | None
    weight: Decimal
    status: FolderStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class TaskInfo:
    id: UUID
    folder_id: UUID
    title: str
    description: str | None
    weight: Decimal
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


# Чтение дерева (spec 0003). Приоритет — Decimal: произведение весов без потери точности.


@dataclass(frozen=True, kw_only=True)
class FolderCrumb:
    """Элемент пути по дереву: хлебные крошки и путь до задачи."""

    id: UUID
    title: str
    weight: Decimal
    status: FolderStatus


@dataclass(frozen=True, kw_only=True)
class RankedFolder:
    """Подпапка в проводнике с абсолютным приоритетом (от корня)."""

    info: FolderInfo
    priority: Decimal


@dataclass(frozen=True, kw_only=True)
class RankedTask:
    """Задача в проводнике с абсолютным приоритетом (от корня)."""

    info: TaskInfo
    priority: Decimal


@dataclass(frozen=True, kw_only=True)
class FolderListing:
    """Режим «проводник»: папка, путь к ней и прямые дети."""

    folder: FolderInfo
    path: list[FolderCrumb]  # от корня до папки включительно
    active_branch: bool  # папка и все предки active — ветка видна во «всём вложенном» от корня
    folders: list[RankedFolder]
    tasks: list[RankedTask]


@dataclass(frozen=True, kw_only=True)
class NestedTask:
    """Режим «всё вложенное»: задача с приоритетом относительно выбранной папки."""

    info: TaskInfo
    priority: Decimal
    path: list[
        FolderCrumb
    ]  # от подпапки выбранной папки до папки задачи; пусто — задача прямо в ней
