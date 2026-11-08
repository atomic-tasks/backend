"""Вход через IdP: пользователь находится по (issuer, sub), новый — только по allowlist."""

from collections.abc import AsyncIterator

import pytest
from dishka import AsyncContainer

from atomic_tasks.application.errors import PermissionDeniedError
from atomic_tasks.application.ports.oidc import VerifiedClaims
from atomic_tasks.application.services.identity_service import IdentityService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.exceptions import UserDisabledError


@pytest.fixture
async def container(
    empty_db: Settings,
    settings_with_allowlist: Settings,
) -> AsyncIterator[AsyncContainer]:
    container = create_container(settings_with_allowlist)
    yield container
    await container.close()


def _claims(subject: str, email: str | None, *, verified: bool = True) -> VerifiedClaims:
    return VerifiedClaims(
        issuer="https://idp.test/auth/v1",
        subject=subject,
        email=email,
        email_verified=verified,
        name=None,
    )


async def _resolve(container: AsyncContainer, claims: VerifiedClaims):  # type: ignore[no-untyped-def]
    async with container() as c:
        return await (await c.get(IdentityService)).resolve(claims)


async def test_first_login_creates_user_once(container: AsyncContainer) -> None:
    first = await _resolve(container, _claims("sub-1", "Alice@Example.com"))
    second = await _resolve(container, _claims("sub-1", "alice@example.com"))
    assert first.id == second.id
    assert first.email == "alice@example.com"
    async with container() as c:
        assert len(await (await c.get(UserService)).list_all()) == 1


async def test_user_is_identified_by_subject_not_email(container: AsyncContainer) -> None:
    alice = await _resolve(container, _claims("sub-1", "alice@example.com"))
    other = await _resolve(container, _claims("sub-2", "alice@example.com"))
    assert alice.id != other.id


@pytest.mark.parametrize(
    "claims",
    [
        _claims("sub-x", "stranger@example.com"),
        _claims("sub-x", "alice@example.com", verified=False),
        _claims("sub-x", None),
    ],
)
async def test_registration_requires_verified_allowlisted_email(
    container: AsyncContainer,
    claims: VerifiedClaims,
) -> None:
    with pytest.raises(PermissionDeniedError):
        await _resolve(container, claims)


async def test_disabled_user_cannot_log_in(container: AsyncContainer) -> None:
    user = await _resolve(container, _claims("sub-1", "alice@example.com"))
    async with container() as c:
        await (await c.get(UserService)).set_disabled(user.id, disabled=True)
    with pytest.raises(UserDisabledError):
        await _resolve(container, _claims("sub-1", "alice@example.com"))
