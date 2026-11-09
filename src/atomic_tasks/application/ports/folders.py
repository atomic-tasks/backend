from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.values import ItemCount


@dataclass(frozen=True, kw_only=True)
class FolderRef:
    """Лёгкая ссылка на папку из рекурсивного запроса: без загрузки сущности целиком."""

    id: UUID
    status: FolderStatus


class FolderRepository(Protocol):
    """Запись папок и запросы по дереву, нужные для проверки правил при записи.

    Методы, которые обходят дерево, принимают папку, а не id: им нужен её owner_id,
    чтобы рекурсия не вышла за дерево владельца.
    """

    def add(self, folder: Folder) -> None:
        """Добавляет папку в текущую транзакцию; запись — при commit."""
        ...

    async def get(self, folder_id: UUID) -> Folder | None:
        """Папка по id без проверки доступа — её делает сервис через AccessPolicy."""
        ...

    async def get_root(self, owner_id: UUID) -> Folder | None:
        """Корень пользователя."""
        ...

    async def delete(self, folder: Folder) -> None:
        """Удаляет папку вместе со всем поддеревом."""
        ...

    async def path_to_root(self, folder: Folder) -> list[FolderRef]:
        """Сама папка и все её предки до корня, без порядка."""
        ...

    async def count_open_descendants(self, folder: Folder) -> ItemCount:
        """Открытые папки и задачи во всём поддереве, саму папку не считая."""
        ...

    async def count_children(self, folder: Folder) -> ItemCount:
        """Прямые подпапки и задачи."""
        ...
