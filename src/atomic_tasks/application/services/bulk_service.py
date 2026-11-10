import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from atomic_tasks.application.dto import (
    FolderStatusChange,
    Identity,
    NewFolder,
    NewTask,
    NodeInfo,
    StatusChange,
    TaskStatusChange,
)
from atomic_tasks.application.errors import ApplicationError, BulkItemError, InvalidQueryError
from atomic_tasks.application.ports.access import AccessPolicy
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.tasks import TaskRepository
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.services.nodes import folder_info, task_info, writable
from atomic_tasks.application.services.status_rules import apply_folder_status, apply_task_status
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.task import Task
from atomic_tasks.domain.exceptions import DomainError
from atomic_tasks.domain.values import Weight

MAX_TREE_NODES = 100
MAX_TREE_DEPTH = 5
MAX_STATUS_CHANGES = 100


class BulkService:
    """Пачечные операции для агента (spec 0004): всё или ничего, один commit в конце.

    При ошибке commit не вызывается, и request-scope закрывает сессию с откатом.
    Ошибка элемента оборачивается в BulkItemError с его адресом:
    агент исправит элемент и повторит пачку целиком.
    """

    def __init__(
        self,
        folders: FolderRepository,
        tasks: TaskRepository,
        access: AccessPolicy,
        tx: TransactionManager,
        clock: Clock,
    ) -> None:
        self._folders = folders
        self._tasks = tasks
        self._access = access
        self._tx = tx
        self._clock = clock

    async def create_tree(
        self,
        identity: Identity,
        *,
        parent_id: UUID,
        folders: Sequence[NewFolder] = (),
        tasks: Sequence[NewTask] = (),
    ) -> list[NodeInfo]:
        """Создаёт под parent_id вложенные папки и задачи. Возвращает созданное в порядке обхода."""
        identity.require_scope(TokenScope.WRITE)
        _check_tree_size(folders, tasks)
        parent = await writable(
            self._access, identity, await self._folders.get(parent_id), "Родительская папка"
        )
        created: list[NodeInfo] = []
        await self._create_children(
            parent, folders, tasks, prefix="", now=self._clock.now(), created=created
        )
        await self._tx.commit()
        return created

    async def set_statuses(
        self,
        identity: Identity,
        changes: Sequence[StatusChange],
    ) -> list[NodeInfo]:
        """Меняет статусы по порядку: каждое правило видит изменения предыдущих элементов."""
        identity.require_scope(TokenScope.WRITE)
        if not 1 <= len(changes) <= MAX_STATUS_CHANGES:
            raise InvalidQueryError(f"В пачке — от 1 до {MAX_STATUS_CHANGES} изменений.")
        now = self._clock.now()
        changed: list[NodeInfo] = []
        for index, change in enumerate(changes):
            with _item(f"changes[{index}]"):
                changed.append(await self._apply_status(identity, change, now))
                # Правило папки считает открытых потомков SQL-запросом,
                # а autoflush у сессии выключен.
                await self._tx.flush()
        await self._tx.commit()
        return changed

    async def _apply_status(
        self, identity: Identity, change: StatusChange, now: datetime
    ) -> NodeInfo:
        match change:
            case FolderStatusChange():
                folder = await writable(
                    self._access, identity, await self._folders.get(change.folder_id), "Папка"
                )
                await apply_folder_status(self._folders, folder, change.status, now)
                return folder_info(folder)
            case TaskStatusChange():
                task = await writable(
                    self._access, identity, await self._tasks.get(change.task_id), "Задача"
                )
                await apply_task_status(self._folders, task, change.status, now)
                return task_info(task)

    async def _create_children(
        self,
        parent: Folder,
        folders: Sequence[NewFolder],
        tasks: Sequence[NewTask],
        *,
        prefix: str,
        now: datetime,
        created: list[NodeInfo],
    ) -> None:
        for index, new_folder in enumerate(folders):
            address = f"{prefix}folders[{index}]"
            with _item(address):
                folder = Folder.create(
                    id=uuid.uuid7(),
                    parent=parent,
                    title=new_folder.title,
                    description=new_folder.description,
                    weight=_weight(new_folder.weight),
                    now=now,
                )
            # Родитель добавляется раньше детей, а unit of work вставляет строки одной таблицы
            # в порядке add — FK не нарушается без промежуточного flush (проверено тестом).
            self._folders.add(folder)
            created.append(folder_info(folder))
            await self._create_children(
                folder,
                new_folder.folders,
                new_folder.tasks,
                prefix=f"{address}.",
                now=now,
                created=created,
            )
        for index, new_task in enumerate(tasks):
            with _item(f"{prefix}tasks[{index}]"):
                task = Task.create(
                    id=uuid.uuid7(),
                    folder=parent,
                    title=new_task.title,
                    description=new_task.description,
                    weight=_weight(new_task.weight),
                    now=now,
                )
            self._tasks.add(task)
            created.append(task_info(task))


@contextmanager
def _item(address: str) -> Iterator[None]:
    """Добавляет к ошибке элемента его адрес в пачке."""
    try:
        yield
    except (ApplicationError, DomainError) as exc:
        raise BulkItemError(address, exc) from exc


def _weight(value: Decimal | None) -> Weight:
    return Weight(value) if value is not None else Weight.default()


def _check_tree_size(folders: Sequence[NewFolder], tasks: Sequence[NewTask]) -> None:
    """Лимиты до обращения к базе: защита от случайной «простыни» от агента."""
    nodes = 0
    depth = 0
    stack = [(f, 1) for f in folders]
    nodes += len(folders) + len(tasks)
    while stack:
        folder, level = stack.pop()
        depth = max(depth, level)
        nodes += len(folder.folders) + len(folder.tasks)
        stack.extend((child, level + 1) for child in folder.folders)
    if nodes == 0:
        raise InvalidQueryError("Пустая пачка: передайте хотя бы одну папку или задачу.")
    if nodes > MAX_TREE_NODES:
        raise InvalidQueryError(
            f"Слишком большая пачка: {nodes} узлов, максимум {MAX_TREE_NODES}. Разбейте на части."
        )
    if depth > MAX_TREE_DEPTH:
        raise InvalidQueryError(
            f"Слишком глубокая вложенность: максимум {MAX_TREE_DEPTH} уровней папок."
        )
