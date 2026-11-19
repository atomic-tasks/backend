"""Правила сессии браузера: куда можно вернуть после входа и когда сессия истекает."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from atomic_tasks.domain.entities.browser_session import (
    IDLE_TTL,
    MAX_TTL,
    BrowserSession,
    pkce_challenge,
    safe_return_to,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "//evil.example",
        "//evil.example/path",
        "/\\evil.example",
        "\\\\evil.example",
        "https://evil.example",
        "http:/evil.example",
        "javascript:alert(1)",
        "evil.example",
        "/%2F/evil.example",
        "/%2f/evil.example",
        "/%5Cevil.example",
        "/\tevil",
        "/\n/evil",
        "/folders\r\nSet-Cookie: x=1",
        "/%0d%0aSet-Cookie:x=1",
        "/ space",
        "/пути",
        "/" + "a" * 3000,
    ],
)
def test_unsafe_return_to_falls_back_to_root(raw: str | None) -> None:
    assert safe_return_to(raw) == "/"


@pytest.mark.parametrize(
    "raw",
    ["/", "/folders/123", "/folders/123?tab=tasks#top", "/%D0%BF%D1%83%D1%82%D1%8C"],
)
def test_safe_return_to_keeps_local_paths(raw: str) -> None:
    assert safe_return_to(raw) == raw


def test_session_expires_after_idle_and_absolute_limits() -> None:
    session = BrowserSession.new(id=uuid.uuid7(), user_id=uuid.uuid7(), token_hash="h", now=NOW)  # noqa: S106
    assert session.is_active(NOW + IDLE_TTL - timedelta(seconds=1))
    assert not session.is_active(NOW + IDLE_TTL)

    # Активность продлевает, но не дальше 90 дней со входа
    now = NOW
    while now < NOW + MAX_TTL - timedelta(days=1):
        now += timedelta(days=20)
        session.touch(now)
    assert session.is_active(NOW + MAX_TTL - timedelta(seconds=1))
    assert not session.is_active(NOW + MAX_TTL)


def test_pkce_challenge_matches_rfc7636_example() -> None:
    # RFC 7636, приложение B
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
