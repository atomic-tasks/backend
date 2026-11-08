from datetime import datetime
from typing import Protocol
from uuid import UUID

from atomic_tasks.domain.entities.api_token import ApiToken


class ApiTokenRepository(Protocol):
    def add(self, token: ApiToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> ApiToken | None: ...

    async def get_for_user(self, user_id: UUID, token_id: UUID) -> ApiToken | None: ...

    async def list_for_user(self, user_id: UUID) -> list[ApiToken]: ...

    async def count_active(self, user_id: UUID, now: datetime) -> int: ...
