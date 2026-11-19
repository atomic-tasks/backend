"""Вход через браузер и сессии на настоящем Postgres: это граница безопасности, без моков БД."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from dishka import AsyncContainer, Provider, Scope, provide
from pydantic import SecretStr
from tests.fakes import FakeOidcClientProvider

from atomic_tasks.application.dto import AuthMethod, LoginResult, LoginStart
from atomic_tasks.application.errors import AuthenticationError, LoginFailedError, LoginFailure
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.services.browser_login_service import BrowserLoginService
from atomic_tasks.application.services.browser_session_service import BrowserSessionService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings, WebSettings
from atomic_tasks.domain.entities.browser_session import IDLE_TTL, LOGIN_TTL, MAX_TTL
from atomic_tasks.domain.exceptions import UserDisabledError

ALICE_CODE = "alice-sub:alice@example.com"


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current


@pytest.fixture
async def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def container(
    empty_db: Settings, settings_with_allowlist: Settings, clock: FakeClock
) -> AsyncIterator[AsyncContainer]:
    settings = settings_with_allowlist.model_copy(
        update={"web": WebSettings(origin="https://atomic.test", client_secret=SecretStr("s"))},
    )

    class ClockOverride(Provider):
        @provide(scope=Scope.APP, override=True)
        def clock(self) -> Clock:
            return clock

    container = create_container(settings, ClockOverride(), FakeOidcClientProvider())
    yield container
    await container.close()


async def _start(container: AsyncContainer, return_to: str | None = "/folders/1") -> LoginStart:
    async with container() as c:
        return await (await c.get(BrowserLoginService)).start(return_to)


async def _finish(
    container: AsyncContainer, started: LoginStart, code: str = ALICE_CODE
) -> LoginResult:
    async with container() as c:
        return await (await c.get(BrowserLoginService)).finish(
            state_cookie=started.state, state=started.state, code=code, idp_error=None
        )


async def _authenticate(container: AsyncContainer, secret: str) -> AuthMethod:
    async with container() as c:
        return (await (await c.get(BrowserSessionService)).authenticate(secret)).method


async def _failure(container: AsyncContainer, started: LoginStart, **kwargs: str) -> LoginFailure:
    params = {"state_cookie": started.state, "state": started.state, "code": ALICE_CODE, **kwargs}
    with pytest.raises(LoginFailedError) as exc:
        async with container() as c:
            await (await c.get(BrowserLoginService)).finish(idp_error=None, **params)
    return exc.value.code


async def test_login_creates_session(container: AsyncContainer) -> None:
    result = await _finish(container, await _start(container))
    assert result.return_to == "/folders/1"
    assert await _authenticate(container, result.session_secret) is AuthMethod.COOKIE


async def test_callback_cannot_be_replayed(container: AsyncContainer) -> None:
    started = await _start(container)
    await _finish(container, started)
    assert await _failure(container, started) is LoginFailure.EXPIRED


async def test_failed_exchange_also_burns_attempt(container: AsyncContainer) -> None:
    started = await _start(container)
    assert await _failure(container, started, code="bad") is LoginFailure.FAILED
    assert await _failure(container, started) is LoginFailure.EXPIRED


async def test_state_must_match_login_cookie(container: AsyncContainer) -> None:
    started, other = await _start(container), await _start(container)
    assert await _failure(container, started, state_cookie=other.state) is LoginFailure.FAILED
    # Подмена не сожгла настоящую попытку
    await _finish(container, started)


async def test_login_attempt_expires(container: AsyncContainer, clock: FakeClock) -> None:
    started = await _start(container)
    clock.current += LOGIN_TTL
    assert await _failure(container, started) is LoginFailure.EXPIRED


async def test_stranger_is_denied(container: AsyncContainer) -> None:
    started = await _start(container)
    code = "eve-sub:eve@example.com"
    assert await _failure(container, started, code=code) is LoginFailure.ACCESS_DENIED


async def test_session_expires_after_idle(container: AsyncContainer, clock: FakeClock) -> None:
    secret = (await _finish(container, await _start(container))).session_secret
    clock.current += IDLE_TTL - timedelta(minutes=1)
    await _authenticate(container, secret)  # продлевает
    clock.current += IDLE_TTL - timedelta(minutes=1)
    await _authenticate(container, secret)
    clock.current += IDLE_TTL
    with pytest.raises(AuthenticationError):
        await _authenticate(container, secret)


async def test_session_expires_after_absolute_limit(
    container: AsyncContainer, clock: FakeClock
) -> None:
    login_at = clock.current
    secret = (await _finish(container, await _start(container))).session_secret
    while clock.current + timedelta(days=20) < login_at + MAX_TTL:
        clock.current += timedelta(days=20)
        await _authenticate(container, secret)
    clock.current = login_at + MAX_TTL
    with pytest.raises(AuthenticationError):
        await _authenticate(container, secret)


async def test_disabled_user_loses_session_and_cannot_log_in(container: AsyncContainer) -> None:
    secret = (await _finish(container, await _start(container))).session_secret
    async with container() as c:
        users = await c.get(UserService)
        (user,) = await users.list_all()
        await users.set_disabled(user.id, disabled=True)
    with pytest.raises(UserDisabledError):
        await _authenticate(container, secret)
    assert await _failure(container, await _start(container)) is LoginFailure.ACCESS_DENIED


async def test_logout_ends_session(container: AsyncContainer) -> None:
    secret = (await _finish(container, await _start(container))).session_secret
    async with container() as c:
        await (await c.get(BrowserLoginService)).logout(secret)
    with pytest.raises(AuthenticationError):
        await _authenticate(container, secret)
