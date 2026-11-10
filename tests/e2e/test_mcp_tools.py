"""Изоляция пользователей и права токена через MCP (spec 0004): чужое — «не найдено»."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.fakes import FakeIdpProvider

from atomic_tasks.config.app import create_app
from atomic_tasks.config.settings import Settings

ACCEPT = {"Accept": "application/json, text/event-stream"}
ALICE = {"Authorization": "Bearer jwt:alice-sub:alice@example.com", **ACCEPT}
BOB = {"Authorization": "Bearer jwt:bob-sub:bob@example.com", **ACCEPT}


@pytest.fixture
def client(empty_db: Settings, settings_with_allowlist: Settings) -> Iterator[TestClient]:
    app = create_app(settings_with_allowlist, FakeIdpProvider())
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client


def _call(client: TestClient, headers: dict[str, str], tool: str, **args: Any) -> dict[str, Any]:
    """tools/call через настоящий HTTP-стек: middleware аутентификации, stateless-транспорт SDK."""
    response = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]  # type: ignore[no-any-return]


def _ok(client: TestClient, headers: dict[str, str], tool: str, **args: Any) -> dict[str, Any]:
    result = _call(client, headers, tool, **args)
    assert not result["isError"], result["content"]
    return result["structuredContent"]  # type: ignore[no-any-return]


def _error(client: TestClient, headers: dict[str, str], tool: str, **args: Any) -> str:
    result = _call(client, headers, tool, **args)
    assert result["isError"], f"{tool}: ожидалась ошибка"
    return str(result["content"][0]["text"])


def test_mcp_requires_token(client: TestClient) -> None:
    response = client.post(
        "/mcp", headers=ACCEPT, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert response.status_code == 401


def test_bob_cannot_read_or_change_alice_tree(client: TestClient) -> None:
    alice_root = _ok(client, ALICE, "browse_folder")["id"]
    folder, task = _ok(
        client,
        ALICE,
        "create_tree",
        parent_id=alice_root,
        folders=[{"title": "секрет", "tasks": [{"title": "t"}]}],
    )["items"]
    bob_root = _ok(client, BOB, "browse_folder")["id"]
    bob_task = _ok(client, BOB, "create_tree", parent_id=bob_root, tasks=[{"title": "b"}])["items"][
        0
    ]

    attempts: list[tuple[str, dict[str, Any]]] = [
        ("browse_folder", {"folder_id": folder["id"]}),
        ("list_next_tasks", {"folder_id": folder["id"]}),
        ("get_item", {"kind": "folder", "id": folder["id"]}),
        ("get_item", {"kind": "task", "id": task["id"]}),
        ("update_item", {"kind": "folder", "id": folder["id"], "title": "x"}),
        ("update_item", {"kind": "task", "id": task["id"], "parent_id": bob_root}),
        ("set_status", {"changes": [{"kind": "task", "id": task["id"], "status": "done"}]}),
        ("set_status", {"changes": [{"kind": "folder", "id": folder["id"], "status": "paused"}]}),
        ("delete_item", {"kind": "task", "id": task["id"]}),
        ("delete_item", {"kind": "folder", "id": folder["id"], "recursive": True}),
        # Своё — в чужую папку.
        ("create_tree", {"parent_id": folder["id"], "tasks": [{"title": "x"}]}),
        ("update_item", {"kind": "task", "id": bob_task["id"], "parent_id": folder["id"]}),
    ]
    for tool, args in attempts:
        text = _error(client, BOB, tool, **args)
        assert "не найден" in text, f"{tool}: {text}"
        assert "секрет" not in text

    # Ничего не изменилось и не исчезло.
    listing = _ok(client, ALICE, "browse_folder", folder_id=folder["id"])
    assert listing["title"] == "секрет"
    assert [t["status"] for t in listing["tasks"]] == ["todo"]


def test_read_token_cannot_write(client: TestClient) -> None:
    created = client.post("/api/v1/tokens", json={"name": "r", "scope": "read"}, headers=ALICE)
    assert created.status_code == 201, created.text
    pat = {"Authorization": f"Bearer {created.json()['token']}", **ACCEPT}

    root = _ok(client, pat, "browse_folder")["id"]
    _ok(client, pat, "list_next_tasks")
    for tool, args in [
        ("create_tree", {"parent_id": root, "tasks": [{"title": "x"}]}),
        ("set_status", {"changes": [{"kind": "folder", "id": root, "status": "paused"}]}),
        ("update_item", {"kind": "folder", "id": root, "title": "x"}),
        ("delete_item", {"kind": "folder", "id": root}),
    ]:
        assert "scope 'write'" in _error(client, pat, tool, **args), tool
