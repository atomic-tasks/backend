from datetime import datetime
from typing import Protocol

from atomic_tasks.domain.entities.browser_session import BrowserSession, LoginAttempt


class BrowserSessionRepository(Protocol):
    def add(self, session: BrowserSession) -> None: ...

    async def get_by_hash(self, token_hash: str) -> BrowserSession | None: ...

    async def delete_by_hash(self, token_hash: str) -> None: ...

    async def delete_expired(self, *, now: datetime, idle_before: datetime) -> None:
        """Удаляет сессии с истёкшим абсолютным сроком или без активности с `idle_before`."""
        ...


class LoginAttemptRepository(Protocol):
    def add(self, attempt: LoginAttempt) -> None: ...

    async def pop_by_state_hash(self, state_hash: str) -> LoginAttempt | None:
        """Читает и удаляет одной операцией: второй callback с тем же state ничего не найдёт."""
        ...

    async def delete_expired(self, now: datetime) -> None: ...
