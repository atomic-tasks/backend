from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from atomic_tasks.domain.exceptions import (
    DomainError,
    DoneAncestorError,
    FolderCycleError,
    FolderHasOpenItemsError,
    FolderNotActiveError,
    FolderNotEmptyError,
    RootFolderProtectedError,
)
from atomic_tasks.domain.values import ItemCount, Weight, normalize_description, normalize_title

ROOT_TITLE = "Root"


class FolderStatus(StrEnum):
    """Статус папки. Любой, кроме active, делает ветку неактивной при чтении дерева."""

    ACTIVE = "active"
    PAUSED = "paused"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_open(self) -> bool:
        """Работа в папке ещё не закончена: active или paused."""
        return self in {FolderStatus.ACTIVE, FolderStatus.PAUSED}


@dataclass(kw_only=True, eq=False)
class Folder:
    """Узел дерева. Корень — единственная папка пользователя без родителя (parent_id is None).

    Методы проверяют правила, но данные о соседях (потомки, предки) не загружают:
    их собирает сервис и передаёт аргументами.
    """

    id: UUID
    owner_id: UUID
    parent_id: UUID | None
    title: str
    description: str | None
    weight: Weight
    status: FolderStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Нормализует название и описание при создании объекта в коде.

        При загрузке из базы SQLAlchemy конструктор не вызывает — там данные уже проверены.
        """
        self.title = normalize_title(self.title)
        self.description = normalize_description(self.description)

    @classmethod
    def new_root(cls, *, id: UUID, owner_id: UUID, now: datetime) -> Folder:
        """Корень нового пользователя: активный, с весом 1.0 и служебным названием."""
        return cls(
            id=id,
            owner_id=owner_id,
            parent_id=None,
            title=ROOT_TITLE,
            description=None,
            weight=Weight.default(),
            status=FolderStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        parent: Folder,
        title: str,
        description: str | None,
        weight: Weight,
        now: datetime,
    ) -> Folder:
        """Новая активная папка внутри parent; parent должна быть active."""
        parent.ensure_accepts_children()
        return cls(
            id=id,
            # Владелец берётся у родителя, а не у того, кто создаёт: при шаринге (ADR 0005)
            # гость будет добавлять папки в чужое дерево, и они должны остаться в нём.
            owner_id=parent.owner_id,
            parent_id=parent.id,
            title=title,
            description=description,
            weight=weight,
            status=FolderStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_root(self) -> bool:
        """Корень пользователя — единственная папка без родителя."""
        return self.parent_id is None

    def ensure_accepts_children(self) -> None:
        """Новое и перенесённое кладётся только в активную папку — так оно не окажется под done."""
        if self.status is not FolderStatus.ACTIVE:
            raise FolderNotActiveError(self.status)

    def rename(self, title: str, now: datetime) -> None:
        """Меняет название; у корня нельзя."""
        self._ensure_not_root()
        self.title = normalize_title(title)
        self.updated_at = now

    def describe(self, description: str | None, now: datetime) -> None:
        """Меняет описание; пустая строка очищает его. У корня нельзя."""
        self._ensure_not_root()
        self.description = normalize_description(description)
        self.updated_at = now

    def set_weight(self, weight: Weight, now: datetime) -> None:
        """Меняет вес; у корня нельзя — его вес всегда 1.0."""
        self._ensure_not_root()
        self.weight = weight
        self.updated_at = now

    def move_to(self, new_parent: Folder, new_parent_path: Collection[UUID], now: datetime) -> None:
        """Переносит папку в new_parent.

        new_parent_path — id новой родительской папки и всех её предков до корня.
        Если среди них есть эта папка, перенос создал бы цикл.
        """
        self._ensure_not_root()
        if new_parent.owner_id != self.owner_id:
            raise DomainError("Нельзя переносить папку в дерево другого владельца.")
        if self.id == new_parent.id or self.id in new_parent_path:
            raise FolderCycleError
        new_parent.ensure_accepts_children()
        self.parent_id = new_parent.id
        self.updated_at = now

    def change_status(
        self,
        new: FolderStatus,
        *,
        open_descendants: ItemCount,
        has_done_ancestor: bool,
        now: datetime,
    ) -> None:
        """Меняет статус по правилам spec 0002.

        open_descendants — открытые папки и задачи во всём поддереве;
        has_done_ancestor — есть ли выше по дереву папка в статусе done.
        paused и cancelled ставятся всегда; done — только при закрытом поддереве;
        открыть нельзя под done-предком. Повтор того же статуса ничего не меняет.
        """
        # Корень проверяется первым: агенту бесполезно знать про открытые задачи
        # в папке, которую всё равно нельзя закрыть.
        self._ensure_not_root()
        if new is self.status:
            return
        if new.is_open and has_done_ancestor:
            raise DoneAncestorError
        if new is FolderStatus.DONE and open_descendants.total:
            raise FolderHasOpenItemsError(open_descendants.folders, open_descendants.tasks)
        self.status = new
        self.updated_at = now

    def ensure_deletable(self, children: ItemCount, *, recursive: bool) -> None:
        """Корень не удаляется; непустая папка — только с recursive.

        children — прямые подпапки и задачи: для решения «пусто или нет» глубже смотреть не нужно.
        """
        self._ensure_not_root()
        if children.total and not recursive:
            raise FolderNotEmptyError(children.folders, children.tasks)

    def _ensure_not_root(self) -> None:
        """Общая защита корня для всех изменяющих методов."""
        if self.is_root:
            raise RootFolderProtectedError
