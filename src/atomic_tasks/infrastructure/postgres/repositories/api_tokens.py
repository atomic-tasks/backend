from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.domain.entities.api_token import ApiToken
from atomic_tasks.infrastructure.postgres.tables import api_tokens as t


class SqlApiTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, token: ApiToken) -> None:
        self._session.add(token)

    async def get_by_hash(self, token_hash: str) -> ApiToken | None:
        return await self._session.scalar(select(ApiToken).where(t.c.token_hash == token_hash))

    async def get_for_user(self, user_id: UUID, token_id: UUID) -> ApiToken | None:
        return await self._session.scalar(
            select(ApiToken).where(t.c.id == token_id, t.c.user_id == user_id),
        )

    async def list_for_user(self, user_id: UUID) -> list[ApiToken]:
        result = await self._session.scalars(
            select(ApiToken).where(t.c.user_id == user_id).order_by(t.c.created_at.desc()),
        )
        return list(result)

    async def count_active(self, user_id: UUID, now: datetime) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(t)
            .where(
                t.c.user_id == user_id,
                t.c.revoked_at.is_(None),
                or_(t.c.expires_at.is_(None), t.c.expires_at > now),
            ),
        )
        return count or 0
