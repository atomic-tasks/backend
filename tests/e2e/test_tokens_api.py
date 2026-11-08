"""Управление токенами через REST: только из сессии IdP и только своими."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.fakes import FakeIdpProvider

from atomic_tasks.config.app import create_app
from atomic_tasks.config.settings import Settings

ALICE = {"Authorization": "Bearer jwt:alice-sub:alice@example.com"}
BOB = {"Authorization": "Bearer jwt:bob-sub:bob@example.com"}


@pytest.fixture
def client(
    empty_db: Settings,
    settings_with_allowlist: Settings,
) -> Iterator[TestClient]:
    app = create_app(settings_with_allowlist, FakeIdpProvider())
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client


def _create(client: TestClient, headers: dict[str, str], **body: object) -> dict[str, object]:
    response = client.post("/api/v1/tokens", json={"name": "test", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_session_can_issue_token_that_then_works(client: TestClient) -> None:
    created = _create(client, ALICE, scope="read", expires_in_days=7)
    pat = {"Authorization": f"Bearer {created['token']}"}
    me = client.get("/api/v1/me", headers=pat).json()
    assert me == client.get("/api/v1/me", headers=ALICE).json()
    listed = client.get("/api/v1/tokens", headers=ALICE).json()
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]


def test_token_cannot_manage_tokens(client: TestClient) -> None:
    pat = {"Authorization": f"Bearer {_create(client, ALICE)['token']}"}
    assert client.post("/api/v1/tokens", json={"name": "x"}, headers=pat).status_code == 403
    assert client.get("/api/v1/tokens", headers=pat).status_code == 403


def test_users_see_and_revoke_only_their_tokens(client: TestClient) -> None:
    alice_token = _create(client, ALICE)
    assert client.get("/api/v1/tokens", headers=BOB).json() == []
    assert client.delete(f"/api/v1/tokens/{alice_token['id']}", headers=BOB).status_code == 404
    assert client.delete(f"/api/v1/tokens/{alice_token['id']}", headers=ALICE).status_code == 204
    pat = {"Authorization": f"Bearer {alice_token['token']}"}
    assert client.get("/api/v1/me", headers=pat).status_code == 401


def test_stranger_is_not_registered(client: TestClient) -> None:
    stranger = {"Authorization": "Bearer jwt:eve-sub:eve@example.com"}
    assert client.get("/api/v1/me", headers=stranger).status_code == 403
