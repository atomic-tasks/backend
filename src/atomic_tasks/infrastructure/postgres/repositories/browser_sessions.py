from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.domain.entities.browser_session import BrowserSession, LoginAttempt
from atomic_tasks.infrastructure.postgres.tables import browser_sessions as s
from atomic_tasks.infrastructure.postgres.tables import login_attempts as a


class SqlBrowserSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, session: BrowserSession) -> None:
        self._session.add(session)

    async def get_by_hash(self, token_hash: str) -> BrowserSession | None:
        return await self._session.scalar(
            select(BrowserSession).where(s.c.token_hash == token_hash)
        )

    async def delete_by_hash(self, token_hash: str) -> None:
        await self._session.execute(delete(s).where(s.c.token_hash == token_hash))

    async def delete_expired(self, *, now: datetime, idle_before: datetime) -> None:
        await self._session.execute(
            delete(s).where(or_(s.c.expires_at <= now, s.c.last_seen_at <= idle_before)),
        )


class SqlLoginAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, attempt: LoginAttempt) -> None:
        self._session.add(attempt)

    async def pop_by_state_hash(self, state_hash: str) -> LoginAttempt | None:
        # DELETE … RETURNING: из двух одновременных callback строку получит только один
        result = await self._session.scalars(
            delete(LoginAttempt).where(a.c.state_hash == state_hash).returning(LoginAttempt),
        )
        return result.one_or_none()

    async def delete_expired(self, now: datetime) -> None:
        await self._session.execute(delete(a).where(a.c.expires_at <= now))
