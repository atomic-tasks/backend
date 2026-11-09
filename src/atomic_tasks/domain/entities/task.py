from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.exceptions import DomainError, DoneAncestorError
from atomic_tasks.domain.values import Weight, normalize_description, normalize_title


class TaskStatus(StrEnum):
    """Статус задачи. Переходы между ними свободные."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_open(self) -> bool:
        """Задача ещё не закрыта: todo, in_progress или paused."""
        return self in {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.PAUSED}


@dataclass(kw_only=True, eq=False)
class Task:
    """Атомарная задача. Всегда лежит в папке; «задача в корне» — задача в корневой папке."""

    id: UUID
    owner_id: UUID
    folder_id: UUID
    title: str
    description: str | None
    weight: Weight
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Нормализует название и описание (при загрузке из базы не вызывается)."""
        self.title = normalize_title(self.title)
        self.description = normalize_description(self.description)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        folder: Folder,
        title: str,
        description: str | None,
        weight: Weight,
        now: datetime,
    ) -> Task:
        """Новая задача в статусе todo; папка должна быть active, владелец — её владелец."""
        folder.ensure_accepts_children()
        return cls(
            id=id,
            owner_id=folder.owner_id,
            folder_id=folder.id,
            title=title,
            description=description,
            weight=weight,
            status=TaskStatus.TODO,
            created_at=now,
            updated_at=now,
        )

    def rename(self, title: str, now: datetime) -> None:
        """Меняет название."""
        self.title = normalize_title(title)
        self.updated_at = now

    def describe(self, description: str | None, now: datetime) -> None:
        """Меняет описание; пустая строка очищает его."""
        self.description = normalize_description(description)
        self.updated_at = now

    def set_weight(self, weight: Weight, now: datetime) -> None:
        """Меняет вес."""
        self.weight = weight
        self.updated_at = now

    def move_to(self, folder: Folder, now: datetime) -> None:
        """Переносит задачу в другую папку того же владельца; папка должна быть active."""
        if folder.owner_id != self.owner_id:
            raise DomainError("Нельзя переносить задачу в дерево другого владельца.")
        folder.ensure_accepts_children()
        self.folder_id = folder.id
        self.updated_at = now

    def change_status(self, new: TaskStatus, *, has_done_ancestor: bool, now: datetime) -> None:
        """Переходы свободные; открыть нельзя только под выполненной папкой.

        has_done_ancestor — папка задачи или любой её предок в статусе done.
        Повтор того же статуса ничего не меняет.
        """
        if new is self.status:
            return
        if new.is_open and has_done_ancestor:
            raise DoneAncestorError
        self.status = new
        self.updated_at = now
