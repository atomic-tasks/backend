from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.domain.entities.task import Task


class SqlTaskRepository:
    """TaskRepository на SQLAlchemy-сессии запроса."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, task: Task) -> None:
        """Добавляет задачу в сессию; INSERT — при commit."""
        self._session.add(task)

    async def get(self, task_id: UUID) -> Task | None:
        """Задача по первичному ключу (сначала из identity map сессии)."""
        return await self._session.get(Task, task_id)

    async def delete(self, task: Task) -> None:
        """Помечает задачу на удаление; DELETE — при commit."""
        await self._session.delete(task)
