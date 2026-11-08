from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.domain.entities.user import UserIdentity
from atomic_tasks.infrastructure.postgres.tables import user_identities as t


class SqlUserIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, identity: UserIdentity) -> None:
        self._session.add(identity)

    async def get(self, issuer: str, subject: str) -> UserIdentity | None:
        return await self._session.scalar(
            select(UserIdentity).where(t.c.issuer == issuer, t.c.subject == subject),
        )
