"""Изоляция пользователей в REST папок и задач (spec 0003): чужое — всегда 404."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.fakes import FakeIdpProvider

from atomic_tasks.config.app import create_app
from atomic_tasks.config.settings import Settings

ALICE = {"Authorization": "Bearer jwt:alice-sub:alice@example.com"}
BOB = {"Authorization": "Bearer jwt:bob-sub:bob@example.com"}


@pytest.fixture
def client(empty_db: Settings, settings_with_allowlist: Settings) -> Iterator[TestClient]:
    app = create_app(settings_with_allowlist, FakeIdpProvider())
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client


def _ok(response: Any, code: int = 200) -> dict[str, Any]:
    assert response.status_code == code, response.text
    return response.json()  # type: ignore[no-any-return]


def _root(client: TestClient, headers: dict[str, str]) -> str:
    return str(_ok(client.get("/api/v1/folders/root", headers=headers))["id"])


def test_bob_cannot_read_or_change_alice_tree(client: TestClient) -> None:
    alice_root = _root(client, ALICE)
    folder = _ok(
        client.post("/api/v1/folders", json={"parent_id": alice_root, "title": "f"}, headers=ALICE),
        201,
    )["id"]
    task = _ok(
        client.post("/api/v1/tasks", json={"folder_id": folder, "title": "t"}, headers=ALICE), 201
    )["id"]
    bob_root = _root(client, BOB)
    bob_task = _ok(
        client.post("/api/v1/tasks", json={"folder_id": bob_root, "title": "b"}, headers=BOB), 201
    )["id"]

    attempts = [
        ("GET", f"/folders/{folder}", None),
        ("GET", f"/folders/{folder}/children", None),
        ("GET", f"/folders/{folder}/nested-tasks", None),
        ("PATCH", f"/folders/{folder}", {"title": "x"}),
        ("POST", f"/folders/{folder}/move", {"parent_id": bob_root}),
        ("POST", f"/folders/{folder}/status", {"status": "paused"}),
        ("DELETE", f"/folders/{folder}?recursive=true", None),
        ("GET", f"/tasks/{task}", None),
        ("PATCH", f"/tasks/{task}", {"title": "x"}),
        ("POST", f"/tasks/{task}/move", {"folder_id": bob_root}),
        ("POST", f"/tasks/{task}/status", {"status": "done"}),
        ("DELETE", f"/tasks/{task}", None),
        # Своё — в чужую папку.
        ("POST", "/folders", {"parent_id": folder, "title": "x"}),
        ("POST", "/tasks", {"folder_id": folder, "title": "x"}),
        ("POST", f"/tasks/{bob_task}/move", {"folder_id": folder}),
    ]
    for method, path, body in attempts:
        response = client.request(method, f"/api/v1{path}", json=body, headers=BOB)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"

    # Ничего не изменилось и не исчезло.
    assert _ok(client.get(f"/api/v1/tasks/{task}", headers=ALICE))["title"] == "t"
    listing = _ok(client.get(f"/api/v1/folders/{alice_root}/children", headers=ALICE))
    assert [f["id"] for f in listing["folders"]] == [folder]


def test_read_token_cannot_write(client: TestClient) -> None:
    created = _ok(
        client.post("/api/v1/tokens", json={"name": "r", "scope": "read"}, headers=ALICE), 201
    )
    pat = {"Authorization": f"Bearer {created['token']}"}
    root = _root(client, pat)
    assert client.get(f"/api/v1/folders/{root}/nested-tasks", headers=pat).status_code == 200
    response = client.post("/api/v1/folders", json={"parent_id": root, "title": "x"}, headers=pat)
    assert response.status_code == 403
