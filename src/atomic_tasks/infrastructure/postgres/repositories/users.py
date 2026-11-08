from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.domain.entities.user import User
from atomic_tasks.infrastructure.postgres.tables import users as t


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, user: User) -> None:
        self._session.add(user)

    async def get(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list_all(self) -> list[User]:
        result = await self._session.scalars(select(User).order_by(t.c.created_at))
        return list(result)
