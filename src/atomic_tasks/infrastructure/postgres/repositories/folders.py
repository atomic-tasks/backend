from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.application.ports.folders import FolderRef
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.domain.values import ItemCount
from atomic_tasks.infrastructure.postgres.tables import folders as t

# Списки открытых статусов берутся из домена и передаются массивом в = ANY(:param),
# чтобы правило «что считается открытым» не дублировалось в SQL.
_OPEN_FOLDER = [s.value for s in FolderStatus if s.is_open]
_OPEN_TASK = [s.value for s in TaskStatus if s.is_open]

# UNION (не UNION ALL) отбрасывает повторные строки, поэтому рекурсия завершится
# даже на цикле, который мог появиться в обход проверок (гонка двух переносов).
# owner_id в каждой ветке — защита в глубину: CTE не выйдет за дерево владельца.

_PATH_TO_ROOT = text("""
    WITH RECURSIVE path AS (
        SELECT id, parent_id, status FROM folders
        WHERE id = :folder_id AND owner_id = :owner_id
        UNION
        SELECT f.id, f.parent_id, f.status FROM folders f
        JOIN path p ON f.id = p.parent_id
        WHERE f.owner_id = :owner_id
    )
    SELECT id, status FROM path
""")

_OPEN_DESCENDANTS = text("""
    WITH RECURSIVE sub AS (
        SELECT id, status FROM folders
        WHERE parent_id = :folder_id AND owner_id = :owner_id
        UNION
        SELECT f.id, f.status FROM folders f
        JOIN sub s ON f.parent_id = s.id
        WHERE f.owner_id = :owner_id
    )
    SELECT
        (SELECT count(*) FROM sub WHERE status = ANY(:open_folder)) AS folders,
        (SELECT count(*) FROM tasks
         WHERE owner_id = :owner_id
           AND status = ANY(:open_task)
           AND (folder_id = :folder_id OR folder_id IN (SELECT id FROM sub))) AS tasks
""")

_CHILDREN = text("""
    SELECT
        (SELECT count(*) FROM folders
         WHERE parent_id = :folder_id AND owner_id = :owner_id) AS folders,
        (SELECT count(*) FROM tasks
         WHERE folder_id = :folder_id AND owner_id = :owner_id) AS tasks
""")


class SqlFolderRepository:
    """FolderRepository на SQLAlchemy-сессии запроса.

    Рекурсивные запросы — сырой SQL с bind-параметрами: так CTE читается как SQL,
    а не как цепочка вызовов Core. Сессия не автофлашится, поэтому запросы видят
    только закоммиченное — сервисы вызывают их до изменений.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, folder: Folder) -> None:
        """Добавляет папку в сессию; INSERT — при commit."""
        self._session.add(folder)

    async def get(self, folder_id: UUID) -> Folder | None:
        """Папка по первичному ключу (сначала из identity map сессии)."""
        return await self._session.get(Folder, folder_id)

    async def get_root(self, owner_id: UUID) -> Folder | None:
        """Корень по частичному уникальному индексу (owner_id) WHERE parent_id IS NULL."""
        return await self._session.scalar(
            select(Folder).where(t.c.owner_id == owner_id, t.c.parent_id.is_(None)),
        )

    async def delete(self, folder: Folder) -> None:
        """Удаляет папку; поддерево удаляет ON DELETE CASCADE в базе, а не ORM."""
        await self._session.delete(folder)

    async def path_to_root(self, folder: Folder) -> list[FolderRef]:
        """Папка и её предки: рекурсия вверх по parent_id."""
        rows = await self._session.execute(
            _PATH_TO_ROOT,
            {"folder_id": folder.id, "owner_id": folder.owner_id},
        )
        return [FolderRef(id=r.id, status=FolderStatus(r.status)) for r in rows]

    async def count_open_descendants(self, folder: Folder) -> ItemCount:
        """Открытые подпапки на любой глубине и открытые задачи в папке и под ней."""
        row = (
            await self._session.execute(
                _OPEN_DESCENDANTS,
                {
                    "folder_id": folder.id,
                    "owner_id": folder.owner_id,
                    "open_folder": _OPEN_FOLDER,
                    "open_task": _OPEN_TASK,
                },
            )
        ).one()
        return ItemCount(folders=row.folders, tasks=row.tasks)

    async def count_children(self, folder: Folder) -> ItemCount:
        """Прямые дети: два count по индексам, без рекурсии."""
        row = (
            await self._session.execute(
                _CHILDREN,
                {"folder_id": folder.id, "owner_id": folder.owner_id},
            )
        ).one()
        return ItemCount(folders=row.folders, tasks=row.tasks)
