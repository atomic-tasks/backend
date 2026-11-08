"""Аутентификация через все входы приложения: REST и MCP."""

import asyncio
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.app import create_app
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.entities.api_token import TokenScope

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
MCP_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


async def _create_user_with_token(settings: Settings, name: str) -> tuple[str, str]:
    container = create_container(settings)
    try:
        async with container() as c:
            user = await (await c.get(UserService)).create(display_name=name, email=None)
            created = await (await c.get(TokenService)).create(
                user_id=user.id,
                name="e2e",
                scope=TokenScope.WRITE,
                ttl_days=30,
            )
            return str(user.id), created.token
    finally:
        await container.close()


async def _disable(settings: Settings, user_id: str) -> None:
    container = create_container(settings)
    try:
        async with container() as c:
            await (await c.get(UserService)).set_disabled(UUID(user_id), disabled=True)
    finally:
        await container.close()


@pytest.fixture
def client(empty_db: Settings) -> Iterator[TestClient]:
    settings = empty_db
    with TestClient(create_app(settings), base_url="http://localhost:8000") as client:
        yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/v1/me", headers=_bearer("at_abcd1234_wrong")).status_code == 401


def test_each_user_sees_only_themselves(client: TestClient, settings: Settings) -> None:
    alice_id, alice_token = asyncio.run(_create_user_with_token(settings, "Alice"))
    bob_id, bob_token = asyncio.run(_create_user_with_token(settings, "Bob"))
    assert client.get("/api/v1/me", headers=_bearer(alice_token)).json()["id"] == alice_id
    assert client.get("/api/v1/me", headers=_bearer(bob_token)).json()["id"] == bob_id


def test_disabled_user_is_forbidden(client: TestClient, settings: Settings) -> None:
    user_id, token = asyncio.run(_create_user_with_token(settings, "Alice"))
    asyncio.run(_disable(settings, user_id))
    assert client.get("/api/v1/me", headers=_bearer(token)).status_code == 403


def test_mcp_requires_token(client: TestClient, settings: Settings) -> None:
    _, token = asyncio.run(_create_user_with_token(settings, "Alice"))
    assert client.post("/mcp", json=MCP_INIT, headers=MCP_HEADERS).status_code == 401
    response = client.post("/mcp", json=MCP_INIT, headers={**MCP_HEADERS, **_bearer(token)})
    assert response.status_code == 200


def test_public_endpoints_stay_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/no-such-page").status_code == 404
