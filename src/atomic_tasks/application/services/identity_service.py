import uuid

from atomic_tasks.application.errors import PermissionDeniedError
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.identities import UserIdentityRepository
from atomic_tasks.application.ports.oidc import VerifiedClaims
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.ports.users import UserRepository
from atomic_tasks.application.registration import RegistrationPolicy
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.user import User, UserIdentity

LAST_LOGIN_RESOLUTION_SECONDS = 3600


class IdentityService:
    """Пользователь по входу через IdP; при первом входе создаётся, если пускает allowlist."""

    def __init__(  # noqa: PLR0917 — зависимости внедряет dishka
        self,
        users: UserRepository,
        identities: UserIdentityRepository,
        folders: FolderRepository,
        tx: TransactionManager,
        clock: Clock,
        policy: RegistrationPolicy,
    ) -> None:
        self._users = users
        self._identities = identities
        self._folders = folders
        self._tx = tx
        self._clock = clock
        self._policy = policy

    async def resolve(self, claims: VerifiedClaims) -> User:
        now = self._clock.now()
        identity = await self._identities.get(claims.issuer, claims.subject)
        if identity is not None:
            user = await self._users.get(identity.user_id)
            if user is None:  # каскадное удаление не даёт этому случиться, но не падаем молча
                raise PermissionDeniedError("Аккаунт не найден.")
            user.ensure_active()
            last = identity.last_login_at
            if last is None or (now - last).total_seconds() > LAST_LOGIN_RESOLUTION_SECONDS:
                identity.last_login_at = now
                if claims.email_verified and claims.email:
                    user.email = claims.email.lower()
                await self._tx.commit()
            return user

        if not self._policy.allows(claims.email, email_verified=claims.email_verified):
            raise PermissionDeniedError(
                "Регистрация закрыта: этого email нет в списке допущенных.",
            )
        user = User(
            id=uuid.uuid7(),
            display_name=claims.name or (claims.email or "").split("@")[0] or "user",
            email=claims.email.lower() if claims.email else None,
            created_at=now,
            updated_at=now,
        )
        self._users.add(user)
        # Корень в той же транзакции: пользователя без корня не бывает
        self._folders.add(Folder.new_root(id=uuid.uuid7(), owner_id=user.id, now=now))
        self._identities.add(
            UserIdentity(
                id=uuid.uuid7(),
                user_id=user.id,
                issuer=claims.issuer,
                subject=claims.subject,
                created_at=now,
                last_login_at=now,
            ),
        )
        await self._tx.commit()
        return user
