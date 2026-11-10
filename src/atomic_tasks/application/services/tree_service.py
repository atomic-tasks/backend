import math
from collections.abc import Collection
from decimal import Decimal
from uuid import UUID

from atomic_tasks.application.dto import (
    FolderListing,
    Identity,
    NestedTask,
    RankedFolder,
    RankedTask,
)
from atomic_tasks.application.errors import InvalidQueryError
from atomic_tasks.application.ports.access import AccessPolicy
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.tree import FolderTreeReader
from atomic_tasks.application.services.nodes import folder_info, readable
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus

FOLDER = "Папка"

DEFAULT_NESTED_LIMIT = 50
MAX_NESTED_LIMIT = 500
DEFAULT_NESTED_STATUSES = frozenset({TaskStatus.TODO, TaskStatus.IN_PROGRESS})


class TreeService:
    """Чтение дерева (spec 0003): «проводник» и «всё вложенное» с приоритетом (ADR 0003)."""

    def __init__(
        self,
        folders: FolderRepository,
        reader: FolderTreeReader,
        access: AccessPolicy,
    ) -> None:
        self._folders = folders
        self._reader = reader
        self._access = access

    async def browse(
        self,
        identity: Identity,
        folder_id: UUID,
        *,
        include_closed: bool = False,
    ) -> FolderListing:
        """Папка, путь от корня и прямые дети с абсолютным приоритетом.

        Веса предков одинаково умножают всех детей, поэтому множитель считается один раз
        подъёмом к корню, а вниз рекурсии нет.
        """
        folder = await self._readable(identity, folder_id)
        path = await self._reader.ancestors(folder)
        folders, tasks = await self._reader.children(folder, include_closed=include_closed)
        scale = math.prod((crumb.weight for crumb in path), start=Decimal(1))
        return FolderListing(
            folder=folder_info(folder),
            path=path,
            active_branch=all(crumb.status is FolderStatus.ACTIVE for crumb in path),
            folders=[RankedFolder(info=f, priority=scale * f.weight) for f in folders],
            tasks=[RankedTask(info=t, priority=scale * t.weight) for t in tasks],
        )

    async def nested_tasks(
        self,
        identity: Identity,
        folder_id: UUID,
        *,
        statuses: Collection[TaskStatus] | None = None,
        limit: int = DEFAULT_NESTED_LIMIT,
    ) -> list[NestedTask]:
        """Задачи всего активного поддерева, сверху — с наибольшим приоритетом."""
        if not 1 <= limit <= MAX_NESTED_LIMIT:
            raise InvalidQueryError(f"limit — от 1 до {MAX_NESTED_LIMIT}.")
        if statuses is not None and not statuses:
            raise InvalidQueryError("Набор статусов не может быть пустым.")
        folder = await self._readable(identity, folder_id)
        return await self._reader.nested_tasks(
            folder,
            statuses=DEFAULT_NESTED_STATUSES if statuses is None else statuses,
            limit=limit,
        )

    async def _readable(self, identity: Identity, folder_id: UUID) -> Folder:
        """Чтение требует scope read; чужая папка — «не найдена»."""
        identity.require_scope(TokenScope.READ)
        return await readable(self._access, identity, await self._folders.get(folder_id), FOLDER)
