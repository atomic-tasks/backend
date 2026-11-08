from typing import Protocol
from uuid import UUID

from atomic_tasks.domain.entities.user import User


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def list_all(self) -> list[User]: ...
