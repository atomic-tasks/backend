from typing import Protocol
from uuid import UUID

from atomic_tasks.domain.entities.task import Task


class TaskRepository(Protocol):
    """Запись задач."""

    def add(self, task: Task) -> None:
        """Добавляет задачу в текущую транзакцию; запись — при commit."""
        ...

    async def get(self, task_id: UUID) -> Task | None:
        """Задача по id без проверки доступа — её делает сервис через AccessPolicy."""
        ...

    async def delete(self, task: Task) -> None:
        """Удаляет задачу."""
        ...
