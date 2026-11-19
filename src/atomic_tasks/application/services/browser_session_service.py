from atomic_tasks.application.dto import AuthMethod, Identity
from atomic_tasks.application.errors import AuthenticationError
from atomic_tasks.application.ports.browser_sessions import BrowserSessionRepository
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.ports.users import UserRepository
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.secrets import hash_secret


class BrowserSessionService:
    """Секрет из cookie сессии → Identity. Права те же, что у входа через IdP."""

    def __init__(
        self,
        sessions: BrowserSessionRepository,
        users: UserRepository,
        tx: TransactionManager,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._tx = tx
        self._clock = clock

    async def authenticate(self, secret: str) -> Identity:
        session = await self._sessions.get_by_hash(hash_secret(secret))
        now = self._clock.now()
        if session is None or not session.is_active(now):
            raise AuthenticationError("Сессия недействительна или истекла, войдите снова.")
        user = await self._users.get(session.user_id)
        if user is None:
            raise AuthenticationError
        user.ensure_active()
        if session.touch(now):
            await self._tx.commit()
        return Identity(user_id=user.id, scope=TokenScope.WRITE, method=AuthMethod.COOKIE)
