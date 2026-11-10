from collections.abc import Collection
from typing import Protocol

from atomic_tasks.application.dto import FolderCrumb, FolderInfo, NestedTask, TaskInfo
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.task import TaskStatus


class FolderTreeReader(Protocol):
    """Чтение деревьев для показа: отдаёт DTO, минуя сущности.

    Методы принимают папку, а не id: доступ к ней уже проверил сервис,
    а её owner_id ограничивает запросы деревом владельца.
    """

    async def ancestors(self, folder: Folder) -> list[FolderCrumb]:
        """Путь от корня до папки включительно, по порядку."""
        ...

    async def children(
        self,
        folder: Folder,
        *,
        include_closed: bool,
    ) -> tuple[list[FolderInfo], list[TaskInfo]]:
        """Прямые подпапки и задачи: открытые раньше закрытых, затем вес по убыванию, затем дата."""
        ...

    async def nested_tasks(
        self,
        folder: Folder,
        *,
        statuses: Collection[TaskStatus],
        limit: int,
    ) -> list[NestedTask]:
        """Задачи активного поддерева по убыванию приоритета относительно папки.

        Сама папка обходится всегда; подпапки — только active.
        """
        ...
