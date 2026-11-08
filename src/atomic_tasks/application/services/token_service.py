import uuid
from datetime import timedelta
from uuid import UUID

from atomic_tasks.application.dto import AuthMethod, CreatedToken, Identity, TokenInfo
from atomic_tasks.application.errors import AuthenticationError, NotFoundError
from atomic_tasks.application.ports.api_tokens import ApiTokenRepository
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.ports.users import UserRepository
from atomic_tasks.domain.entities.api_token import (
    MAX_ACTIVE_TOKENS_PER_USER,
    ApiToken,
    TokenScope,
    generate_token,
    hash_token,
    looks_like_api_token,
    validate_token_params,
)
from atomic_tasks.domain.exceptions import TokenLimitExceededError


class TokenService:
    """Personal access tokens.

    Выпуск, список и отзыв вызываются только из доверенных точек: CLI администратора, а позже —
    из сессии IdP. REST-эндпоинтов выпуска по PAT нет: утёкший токен не выпустит себе новый.
    """

    def __init__(
        self,
        tokens: ApiTokenRepository,
        users: UserRepository,
        tx: TransactionManager,
        clock: Clock,
    ) -> None:
        self._tokens = tokens
        self._users = users
        self._tx = tx
        self._clock = clock

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        scope: TokenScope,
        ttl_days: int | None,
    ) -> CreatedToken:
        name = validate_token_params(name, ttl_days)
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("Пользователь")
        user.ensure_active()
        now = self._clock.now()
        if await self._tokens.count_active(user_id, now) >= MAX_ACTIVE_TOKENS_PER_USER:
            raise TokenLimitExceededError(MAX_ACTIVE_TOKENS_PER_USER)

        generated = generate_token()
        token = ApiToken(
            id=uuid.uuid7(),
            user_id=user_id,
            name=name,
            prefix=generated.prefix,
            token_hash=generated.token_hash,
            scope=scope,
            created_at=now,
            expires_at=now + timedelta(days=ttl_days) if ttl_days is not None else None,
        )
        self._tokens.add(token)
        await self._tx.commit()
        return CreatedToken(info=_to_info(token), token=generated.raw)

    async def list_for_user(self, user_id: UUID) -> list[TokenInfo]:
        return [_to_info(t) for t in await self._tokens.list_for_user(user_id)]

    async def revoke(self, *, user_id: UUID, token_id: UUID) -> None:
        token = await self._tokens.get_for_user(user_id, token_id)
        if token is None:
            raise NotFoundError("Токен")
        token.revoke(self._clock.now())
        await self._tx.commit()

    async def authenticate(self, raw: str) -> Identity:
        if not looks_like_api_token(raw):
            raise AuthenticationError
        token = await self._tokens.get_by_hash(hash_token(raw))
        now = self._clock.now()
        if token is None or not token.is_active(now):
            raise AuthenticationError("Токен недействителен, отозван или истёк.")
        user = await self._users.get(token.user_id)
        if user is None:
            raise AuthenticationError
        user.ensure_active()
        if token.touch(now):
            await self._tx.commit()
        return Identity(user_id=token.user_id, scope=token.scope, method=AuthMethod.PAT)


def _to_info(token: ApiToken) -> TokenInfo:
    return TokenInfo(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        scope=token.scope,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
    )
