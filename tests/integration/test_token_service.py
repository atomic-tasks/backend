"""Жизненный цикл токенов на настоящем Postgres: это граница безопасности, поэтому без моков."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from dishka import AsyncContainer, Provider, Scope, provide

from atomic_tasks.application.dto import AuthTarget
from atomic_tasks.application.errors import AuthenticationError, NotFoundError
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.services.auth_service import AuthService
from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.entities.api_token import MAX_ACTIVE_TOKENS_PER_USER, TokenScope
from atomic_tasks.domain.exceptions import TokenLimitExceededError, UserDisabledError


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current


@pytest.fixture
async def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def container(empty_db: Settings, clock: FakeClock) -> AsyncIterator[AsyncContainer]:
    settings = empty_db

    class ClockOverride(Provider):
        @provide(scope=Scope.APP, override=True)
        def clock(self) -> Clock:
            return clock

    container = create_container(settings, ClockOverride())
    yield container
    await container.close()


async def _user(container: AsyncContainer, name: str = "Alex") -> uuid.UUID:
    async with container() as c:
        return (await (await c.get(UserService)).create(display_name=name, email=None)).id


async def _token(container: AsyncContainer, user_id: uuid.UUID, ttl: int | None = 30) -> str:
    async with container() as c:
        service = await c.get(TokenService)
        created = await service.create(
            user_id=user_id, name="t", scope=TokenScope.WRITE, ttl_days=ttl
        )
        return created.token


async def _auth(container: AsyncContainer, raw: str) -> uuid.UUID:
    async with container() as c:
        return (
            await (await c.get(AuthService)).authenticate(f"Bearer {raw}", target=AuthTarget.API)
        ).user_id


async def test_token_authenticates_until_revoked(container: AsyncContainer) -> None:
    user_id = await _user(container)
    raw = await _token(container, user_id)
    assert await _auth(container, raw) == user_id

    async with container() as c:
        service = await c.get(TokenService)
        [info] = await service.list_for_user(user_id)
        assert info.last_used_at is not None
        await service.revoke(user_id=user_id, token_id=info.id)

    with pytest.raises(AuthenticationError):
        await _auth(container, raw)


async def test_expired_token_is_rejected(container: AsyncContainer, clock: FakeClock) -> None:
    raw = await _token(container, await _user(container), ttl=1)
    clock.current += timedelta(days=1, seconds=1)
    with pytest.raises(AuthenticationError):
        await _auth(container, raw)


async def test_unknown_and_malformed_tokens_are_rejected(container: AsyncContainer) -> None:
    raw = await _token(container, await _user(container))
    for bad in (raw[:-1] + ("A" if raw[-1] != "A" else "B"), "at_abcd1234_nope", "garbage"):
        with pytest.raises(AuthenticationError):
            await _auth(container, bad)
    async with container() as c:
        with pytest.raises(AuthenticationError):
            await (await c.get(AuthService)).authenticate(None, target=AuthTarget.API)


async def test_disabled_user_cannot_authenticate(container: AsyncContainer) -> None:
    user_id = await _user(container)
    raw = await _token(container, user_id)
    async with container() as c:
        await (await c.get(UserService)).set_disabled(user_id, disabled=True)
    with pytest.raises(UserDisabledError):
        await _auth(container, raw)


async def test_active_token_limit(container: AsyncContainer) -> None:
    user_id = await _user(container)
    for _ in range(MAX_ACTIVE_TOKENS_PER_USER):
        await _token(container, user_id)
    with pytest.raises(TokenLimitExceededError):
        await _token(container, user_id)


async def test_user_cannot_revoke_someone_elses_token(container: AsyncContainer) -> None:
    alice, bob = await _user(container, "Alice"), await _user(container, "Bob")
    await _token(container, bob)
    async with container() as c:
        service = await c.get(TokenService)
        [bob_token] = await service.list_for_user(bob)
        assert await service.list_for_user(alice) == []
        with pytest.raises(NotFoundError):
            await service.revoke(user_id=alice, token_id=bob_token.id)
