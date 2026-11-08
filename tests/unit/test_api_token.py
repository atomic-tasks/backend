import uuid
from datetime import UTC, datetime, timedelta

import pytest

from atomic_tasks.application.dto import AuthMethod, Identity
from atomic_tasks.domain.entities.api_token import (
    ApiToken,
    TokenScope,
    generate_token,
    hash_token,
    looks_like_api_token,
    validate_token_params,
)
from atomic_tasks.domain.exceptions import InsufficientScopeError, InvalidTokenParamsError

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def make_token(**overrides: object) -> ApiToken:
    params: dict[str, object] = {
        "id": uuid.uuid7(),
        "user_id": uuid.uuid7(),
        "name": "test",
        "prefix": "abcd1234",
        "token_hash": "x" * 64,
        "scope": TokenScope.WRITE,
        "created_at": NOW,
        "expires_at": NOW + timedelta(days=1),
    }
    params.update(overrides)
    return ApiToken(**params)  # type: ignore[arg-type]


def test_expired_and_revoked_tokens_are_inactive() -> None:
    assert make_token().is_active(NOW)
    assert make_token(expires_at=None).is_active(NOW + timedelta(days=10_000))
    assert not make_token().is_active(NOW + timedelta(days=1))
    revoked = make_token()
    revoked.revoke(NOW)
    assert not revoked.is_active(NOW)


def test_write_scope_includes_read_but_not_vice_versa() -> None:
    write = Identity(user_id=uuid.uuid7(), scope=TokenScope.WRITE, method=AuthMethod.PAT)
    read = Identity(user_id=uuid.uuid7(), scope=TokenScope.READ, method=AuthMethod.PAT)
    write.require_scope(TokenScope.READ)
    write.require_scope(TokenScope.WRITE)
    read.require_scope(TokenScope.READ)
    with pytest.raises(InsufficientScopeError):
        read.require_scope(TokenScope.WRITE)


def test_last_used_is_updated_at_most_once_a_minute() -> None:
    token = make_token()
    assert token.touch(NOW)
    assert not token.touch(NOW + timedelta(seconds=30))
    assert token.touch(NOW + timedelta(seconds=61))


def test_generated_token_format_and_hash() -> None:
    generated = generate_token()
    marker, prefix, _ = generated.raw.split("_", 2)
    assert marker == "at"
    assert prefix == generated.prefix
    assert looks_like_api_token(generated.raw)
    assert generated.token_hash == hash_token(generated.raw)
    assert generated.raw not in generated.token_hash
    assert generate_token().raw != generated.raw


@pytest.mark.parametrize(
    "raw", ["", "Bearer x", "at_short_x", "xx_abcd1234_secret", "eyJhbGciOi.jwt.like"]
)
def test_garbage_is_not_an_api_token(raw: str) -> None:
    assert not looks_like_api_token(raw)


@pytest.mark.parametrize(
    ("name", "ttl"), [("", 30), (" ", 30), ("x" * 101, 30), ("ok", 0), ("ok", 366)]
)
def test_invalid_token_params(name: str, ttl: int) -> None:
    with pytest.raises(InvalidTokenParamsError):
        validate_token_params(name, ttl)
