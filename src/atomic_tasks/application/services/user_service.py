import uuid
from uuid import UUID

from atomic_tasks.application.dto import UserInfo
from atomic_tasks.application.errors import NotFoundError
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.ports.users import UserRepository
from atomic_tasks.domain.entities.user import User


class UserService:
    def __init__(self, users: UserRepository, tx: TransactionManager, clock: Clock) -> None:
        self._users = users
        self._tx = tx
        self._clock = clock

    async def create(self, *, display_name: str, email: str | None) -> UserInfo:
        """Создание пользователя администратором (CLI). Вход через IdP — отдельной спекой."""
        now = self._clock.now()
        user = User(
            id=uuid.uuid7(),
            display_name=display_name,
            email=email.strip().lower() if email else None,
            created_at=now,
            updated_at=now,
        )
        self._users.add(user)
        await self._tx.commit()
        return _to_info(user)

    async def get(self, user_id: UUID) -> UserInfo:
        return _to_info(await self._get(user_id))

    async def list_all(self) -> list[UserInfo]:
        return [_to_info(u) for u in await self._users.list_all()]

    async def set_disabled(self, user_id: UUID, *, disabled: bool) -> UserInfo:
        user = await self._get(user_id)
        now = self._clock.now()
        if disabled:
            user.disable(now)
        else:
            user.enable(now)
        await self._tx.commit()
        return _to_info(user)

    async def _get(self, user_id: UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("Пользователь")
        return user


def _to_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        created_at=user.created_at,
        disabled=not user.is_active,
    )
