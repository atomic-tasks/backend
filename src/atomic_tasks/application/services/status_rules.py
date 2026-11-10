"""Смена статуса папки и задачи без commit: общий шаг FolderService, TaskService и BulkService.

Собирает факты из базы, которые нужны правилу, и вызывает правило домена.
Commit — забота вызывающего: одиночные сервисы коммитят сразу, пачка — один раз в конце.
"""

from datetime import datetime

from atomic_tasks.application.errors import NotFoundError
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.services.nodes import has_done
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import Task, TaskStatus


async def apply_folder_status(
    folders: FolderRepository,
    folder: Folder,
    status: FolderStatus,
    now: datetime,
) -> None:
    """Меняет статус папки; правила — в Folder.change_status."""
    # Считаем оба факта всегда, даже если для этого статуса нужен один:
    # тогда правило целиком живёт в домене, а не дублируется условием здесь.
    # На личных объёмах лишний запрос дешевле рассинхрона правил.
    open_descendants = await folders.count_open_descendants(folder)
    parent = await folders.get(folder.parent_id) if folder.parent_id else None
    ancestors = await folders.path_to_root(parent) if parent else []
    folder.change_status(
        status,
        open_descendants=open_descendants,
        has_done_ancestor=has_done(ancestors),
        now=now,
    )


async def apply_task_status(
    folders: FolderRepository,
    task: Task,
    status: TaskStatus,
    now: datetime,
) -> None:
    """Меняет статус задачи; открыть задачу под выполненной папкой нельзя."""
    # Папка задачи принадлежит тому же владельцу, поэтому отдельная проверка доступа не нужна:
    # из неё берутся только статусы для правила, наружу ничего не уходит.
    folder = await folders.get(task.folder_id)
    if folder is None:  # FK не даёт этому случиться
        raise NotFoundError("Папка")
    path = await folders.path_to_root(folder)
    task.change_status(status, has_done_ancestor=has_done(path), now=now)
