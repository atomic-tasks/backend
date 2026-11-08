from typing import Protocol

from atomic_tasks.domain.entities.user import UserIdentity


class UserIdentityRepository(Protocol):
    def add(self, identity: UserIdentity) -> None: ...

    async def get(self, issuer: str, subject: str) -> UserIdentity | None: ...
