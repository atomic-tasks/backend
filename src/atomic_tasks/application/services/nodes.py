"""Общие шаги сервисов дерева: проверка доступа к узлу и перевод в DTO."""

from atomic_tasks.application.dto import FolderInfo, Identity, TaskInfo
from atomic_tasks.application.errors import NotFoundError
from atomic_tasks.application.ports.access import AccessPolicy
from atomic_tasks.application.ports.folders import FolderRef
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import Task


# N: (Folder, Task) — ограничение типа: mypy знает, что для папки вернётся именно Folder.
async def readable[N: (Folder, Task)](
    access: AccessPolicy,
    identity: Identity,
    node: N | None,
    what: str,
) -> N:
    """Возвращает узел, если его можно читать.

    Нет объекта или нет доступа — одинаково «не найден»: не раскрываем, что объект есть.
    """
    if node is None or not await access.can_read(identity, node):
        raise NotFoundError(what)
    return node


async def writable[N: (Folder, Task)](
    access: AccessPolicy,
    identity: Identity,
    node: N | None,
    what: str,
) -> N:
    """Возвращает узел, если его можно менять; иначе «не найден», как и в readable."""
    if node is None or not await access.can_write(identity, node):
        raise NotFoundError(what)
    return node


def has_done(path: list[FolderRef]) -> bool:
    """Есть ли на пути к корню выполненная папка — тогда открыть ничего нельзя."""
    return any(ref.status is FolderStatus.DONE for ref in path)


def folder_info(folder: Folder) -> FolderInfo:
    """Папка → DTO: наружу сервисы отдают DTO, не сущности."""
    return FolderInfo(
        id=folder.id,
        parent_id=folder.parent_id,
        title=folder.title,
        description=folder.description,
        weight=folder.weight.value,
        status=folder.status,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def task_info(task: Task) -> TaskInfo:
    """Задача → DTO."""
    return TaskInfo(
        id=task.id,
        folder_id=task.folder_id,
        title=task.title,
        description=task.description,
        weight=task.weight.value,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
