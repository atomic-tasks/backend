import uuid
from decimal import Decimal
from uuid import UUID

from atomic_tasks.application.dto import Identity, TaskInfo
from atomic_tasks.application.ports.access import AccessPolicy
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.tasks import TaskRepository
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.services.nodes import readable, task_info, writable
from atomic_tasks.application.services.status_rules import apply_task_status
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.task import Task, TaskStatus
from atomic_tasks.domain.values import Weight

TASK = "Задача"
FOLDER = "Папка"


class TaskService:
    """Запись задач. Порядок проверок тот же, что в FolderService: scope → доступ → домен."""

    def __init__(
        self,
        tasks: TaskRepository,
        folders: FolderRepository,
        access: AccessPolicy,
        tx: TransactionManager,
        clock: Clock,
    ) -> None:
        self._tasks = tasks
        self._folders = folders
        self._access = access
        self._tx = tx
        self._clock = clock

    async def get(self, identity: Identity, task_id: UUID) -> TaskInfo:
        """Одна задача, если её можно читать."""
        task = await readable(self._access, identity, await self._tasks.get(task_id), TASK)
        return task_info(task)

    async def create(
        self,
        identity: Identity,
        *,
        folder_id: UUID,
        title: str,
        description: str | None = None,
        weight: Decimal | None = None,
    ) -> TaskInfo:
        """Создаёт задачу в папке folder_id; без веса — 1.0."""
        identity.require_scope(TokenScope.WRITE)
        folder = await self._writable_folder(identity, folder_id)
        task = Task.create(
            id=uuid.uuid7(),
            folder=folder,
            title=title,
            description=description,
            weight=Weight(weight) if weight is not None else Weight.default(),
            now=self._clock.now(),
        )
        self._tasks.add(task)
        await self._tx.commit()
        return task_info(task)

    async def update(
        self,
        identity: Identity,
        task_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        weight: Decimal | None = None,
    ) -> TaskInfo:
        """Меняет переданные поля. None — поле не меняется; пустое описание "" — очистить."""
        identity.require_scope(TokenScope.WRITE)
        task = await self._writable(identity, task_id)
        now = self._clock.now()
        if title is not None:
            task.rename(title, now)
        if description is not None:
            task.describe(description, now)
        if weight is not None:
            task.set_weight(Weight(weight), now)
        await self._tx.commit()
        return task_info(task)

    async def move(self, identity: Identity, task_id: UUID, *, new_folder_id: UUID) -> TaskInfo:
        """Переносит задачу в другую активную папку."""
        identity.require_scope(TokenScope.WRITE)
        task = await self._writable(identity, task_id)
        folder = await self._writable_folder(identity, new_folder_id)
        task.move_to(folder, self._clock.now())
        await self._tx.commit()
        return task_info(task)

    async def change_status(
        self, identity: Identity, task_id: UUID, status: TaskStatus
    ) -> TaskInfo:
        """Меняет статус; открыть задачу под выполненной папкой нельзя."""
        identity.require_scope(TokenScope.WRITE)
        task = await self._writable(identity, task_id)
        await apply_task_status(self._folders, task, status, self._clock.now())
        await self._tx.commit()
        return task_info(task)

    async def delete(self, identity: Identity, task_id: UUID) -> None:
        """Удаляет задачу физически."""
        identity.require_scope(TokenScope.WRITE)
        task = await self._writable(identity, task_id)
        await self._tasks.delete(task)
        await self._tx.commit()

    async def _writable(self, identity: Identity, task_id: UUID) -> Task:
        """Загружает задачу и проверяет право её менять."""
        return await writable(self._access, identity, await self._tasks.get(task_id), TASK)

    async def _writable_folder(self, identity: Identity, folder_id: UUID) -> Folder:
        """Загружает папку и проверяет право класть в неё задачи."""
        return await writable(self._access, identity, await self._folders.get(folder_id), FOLDER)
