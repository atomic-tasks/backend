from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.application.dto import FolderCrumb, FolderInfo, NestedTask, TaskInfo
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus

# Как и в repositories/folders.py: «что открыто» и «что активно» берём из домена
# и передаём параметрами, чтобы правило не дублировалось в SQL.
_OPEN_FOLDER = [s.value for s in FolderStatus if s.is_open]
_OPEN_TASK = [s.value for s in TaskStatus if s.is_open]
_ACTIVE = FolderStatus.ACTIVE.value

# Вверх по parent_id. CYCLE (Postgres 14+) помечает повтор и останавливает ветку,
# если цикл появился в обход проверок; depth задаёт порядок «от корня».
_ANCESTORS = text("""
    WITH RECURSIVE up AS (
        SELECT id, parent_id, title, weight, status, 0 AS depth FROM folders
        WHERE id = :folder_id AND owner_id = :owner_id
        UNION ALL
        SELECT f.id, f.parent_id, f.title, f.weight, f.status, u.depth + 1 FROM folders f
        JOIN up u ON f.id = u.parent_id
        WHERE f.owner_id = :owner_id
    ) CYCLE id SET is_cycle USING visited
    SELECT id, title, weight, status FROM up
    WHERE NOT is_cycle
    ORDER BY depth DESC
""")

_CHILD_FOLDERS = text("""
    SELECT id, parent_id, title, description, weight, status, created_at, updated_at
    FROM folders
    WHERE owner_id = :owner_id AND parent_id = :folder_id
      AND (:include_closed OR status = ANY(:open))
    ORDER BY status = ANY(:open) DESC, weight DESC, created_at, id
""")

_CHILD_TASKS = text("""
    SELECT id, folder_id, title, description, weight, status, created_at, updated_at
    FROM tasks
    WHERE owner_id = :owner_id AND folder_id = :folder_id
      AND (:include_closed OR status = ANY(:open))
    ORDER BY status = ANY(:open) DESC, weight DESC, created_at, id
""")

# Порядок задач во «всём вложенном»: приоритет; при равном — начатое раньше (доделать),
# затем старшие (не забывать давнее), затем id — порядок детерминирован, и limit
# на одинаковых данных всегда отдаёт один и тот же набор.
_STARTED = TaskStatus.IN_PROGRESS.value
_NESTED_ORDER_BY = "priority DESC, t.status = :started DESC, t.created_at, t.id"

# Вниз от выбранной папки. В рекурсии несём приоритет и путь (id, названия, веса).
# UNION не спасает от цикла: строки с разными путями различаются, поэтому цикл
# отсекается явно — папка не может встретиться в собственном пути.
# Выбранная папка — якорь, её статус не проверяется; подпапки — только active.
_NESTED_TASKS = text(f"""
    WITH RECURSIVE sub AS (
        SELECT id,
               1::numeric AS priority,
               ARRAY[]::uuid[] AS path_ids,
               ARRAY[]::text[] AS path_titles,
               ARRAY[]::numeric[] AS path_weights
        FROM folders
        WHERE id = :folder_id AND owner_id = :owner_id
        UNION ALL
        SELECT f.id,
               s.priority * f.weight::numeric,
               s.path_ids || f.id,
               s.path_titles || f.title::text,
               s.path_weights || f.weight::numeric
        FROM folders f
        JOIN sub s ON f.parent_id = s.id
        WHERE f.owner_id = :owner_id
          AND f.status = :active
          AND f.id <> :folder_id
          AND NOT f.id = ANY(s.path_ids)
    )
    SELECT t.id, t.folder_id, t.title, t.description, t.weight, t.status,
           t.created_at, t.updated_at,
           s.priority * t.weight AS priority,
           s.path_ids, s.path_titles, s.path_weights
    FROM sub s
    JOIN tasks t ON t.folder_id = s.id AND t.owner_id = :owner_id
    WHERE t.status = ANY(:statuses)
    ORDER BY {_NESTED_ORDER_BY}
    LIMIT :limit
""")  # noqa: S608 — подставляется константа модуля, не ввод пользователя


class SqlFolderTreeReader:
    """FolderTreeReader на сырых SQL-запросах с bind-параметрами."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ancestors(self, folder: Folder) -> list[FolderCrumb]:
        """Путь от корня до папки включительно."""
        rows = await self._session.execute(
            _ANCESTORS,
            {"folder_id": folder.id, "owner_id": folder.owner_id},
        )
        return [
            FolderCrumb(id=r.id, title=r.title, weight=r.weight, status=FolderStatus(r.status))
            for r in rows
        ]

    async def children(
        self,
        folder: Folder,
        *,
        include_closed: bool,
    ) -> tuple[list[FolderInfo], list[TaskInfo]]:
        """Прямые дети: два запроса по индексам, без рекурсии."""
        base = {
            "folder_id": folder.id,
            "owner_id": folder.owner_id,
            "include_closed": include_closed,
        }
        folders = await self._session.execute(_CHILD_FOLDERS, {**base, "open": _OPEN_FOLDER})
        tasks = await self._session.execute(_CHILD_TASKS, {**base, "open": _OPEN_TASK})
        return [_folder_info(r) for r in folders], [_task_info(r) for r in tasks]

    async def nested_tasks(
        self,
        folder: Folder,
        *,
        statuses: Collection[TaskStatus],
        limit: int,
    ) -> list[NestedTask]:
        """Задачи активного поддерева по убыванию приоритета."""
        rows = await self._session.execute(
            _NESTED_TASKS,
            {
                "folder_id": folder.id,
                "owner_id": folder.owner_id,
                "active": _ACTIVE,
                "statuses": [s.value for s in statuses],
                "started": _STARTED,
                "limit": limit,
            },
        )
        return [
            NestedTask(
                info=_task_info(r),
                priority=r.priority,
                path=_crumbs(r.path_ids, r.path_titles, r.path_weights),
            )
            for r in rows
        ]


def _crumbs(ids: Sequence[Any], titles: Sequence[str], weights: Sequence[Any]) -> list[FolderCrumb]:
    """Путь из параллельных массивов CTE. В путь попадают только active-папки."""
    return [
        FolderCrumb(id=i, title=t, weight=w, status=FolderStatus.ACTIVE)
        for i, t, w in zip(ids, titles, weights, strict=True)
    ]


def _folder_info(r: Any) -> FolderInfo:
    return FolderInfo(
        id=r.id,
        parent_id=r.parent_id,
        title=r.title,
        description=r.description,
        weight=r.weight,
        status=FolderStatus(r.status),
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _task_info(r: Any) -> TaskInfo:
    return TaskInfo(
        id=r.id,
        folder_id=r.folder_id,
        title=r.title,
        description=r.description,
        weight=r.weight,
        status=TaskStatus(r.status),
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
