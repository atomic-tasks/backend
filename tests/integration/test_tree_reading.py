"""Чтение дерева на настоящем Postgres: приоритет, отсечение веток, порядок, циклы (spec 0003).

Дерево Алисы (вес в скобках):

    Root
    ├── A (2.0)
    │   ├── A1 (1.5)
    │   │   └── t_a1 (1.0)    приоритет от корня 3.0
    │   └── t_a (0.6)         1.2
    ├── P (2.0, paused)
    │   └── t_p (2.0)         скрыта от корня; от P — 2.0
    ├── t_root (1.0)          1.0
    └── t_done (2.0, done)    скрыта фильтром статусов
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import pytest
from dishka import AsyncContainer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atomic_tasks.application.dto import AuthMethod, Identity
from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.task_service import TaskService
from atomic_tasks.application.services.tree_service import TreeService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus


@pytest.fixture
async def container(empty_db: Settings) -> AsyncIterator[AsyncContainer]:
    container = create_container(empty_db)
    yield container
    await container.close()


@dataclass(frozen=True)
class Tree:
    me: Identity
    root: UUID
    a: UUID
    a1: UUID
    p: UUID
    t_a1: UUID
    t_a: UUID
    t_p: UUID
    t_root: UUID
    t_done: UUID


async def _folder(c: AsyncContainer, me: Identity, parent: UUID, title: str, w: str) -> UUID:
    svc = await c.get(FolderService)
    return (await svc.create(me, parent_id=parent, title=title, weight=Decimal(w))).id


async def _task(c: AsyncContainer, me: Identity, folder: UUID, title: str, w: str) -> UUID:
    svc = await c.get(TaskService)
    return (await svc.create(me, folder_id=folder, title=title, weight=Decimal(w))).id


@pytest.fixture
async def tree(container: AsyncContainer) -> Tree:
    async with container() as c:
        user = await (await c.get(UserService)).create(display_name="alice", email=None)
    me = Identity(user_id=user.id, scope=TokenScope.WRITE, method=AuthMethod.PAT)
    async with container() as c:
        root = (await (await c.get(FolderService)).get_root(me)).id
        a = await _folder(c, me, root, "A", "2.0")
        a1 = await _folder(c, me, a, "A1", "1.5")
        p = await _folder(c, me, root, "P", "2.0")
        t_a1 = await _task(c, me, a1, "t_a1", "1.0")
        t_a = await _task(c, me, a, "t_a", "0.6")
        t_p = await _task(c, me, p, "t_p", "2.0")
        t_root = await _task(c, me, root, "t_root", "1.0")
        t_done = await _task(c, me, root, "t_done", "2.0")
    async with container() as c:
        await (await c.get(FolderService)).change_status(me, p, FolderStatus.PAUSED)
    async with container() as c:
        await (await c.get(TaskService)).change_status(me, t_done, TaskStatus.DONE)
    return Tree(me, root, a, a1, p, t_a1, t_a, t_p, t_root, t_done)


async def test_nested_tasks_ranked_by_product_of_weights(
    container: AsyncContainer, tree: Tree
) -> None:
    async with container() as c:
        tasks = await (await c.get(TreeService)).nested_tasks(tree.me, tree.root)
    # Ветка P (paused) отсечена, t_done отфильтрована статусом.
    assert [t.info.id for t in tasks] == [tree.t_a1, tree.t_a, tree.t_root]
    assert [t.priority for t in tasks] == [Decimal("3.0"), Decimal("1.2"), Decimal("1.0")]
    assert [c.title for c in tasks[0].path] == ["A", "A1"]
    assert tasks[2].path == []


async def test_chosen_inactive_folder_is_still_traversed(
    container: AsyncContainer, tree: Tree
) -> None:
    async with container() as c:
        tasks = await (await c.get(TreeService)).nested_tasks(tree.me, tree.p)
    # Вес самой выбранной папки в приоритет не входит.
    assert [(t.info.id, t.priority) for t in tasks] == [(tree.t_p, Decimal("2.0"))]


async def test_nested_tasks_status_filter_and_limit(container: AsyncContainer, tree: Tree) -> None:
    async with container() as c:
        svc = await c.get(TreeService)
        done = await svc.nested_tasks(tree.me, tree.root, statuses={TaskStatus.DONE})
        top = await svc.nested_tasks(tree.me, tree.root, limit=1)
    assert [t.info.id for t in done] == [tree.t_done]
    assert [t.info.id for t in top] == [tree.t_a1]


async def test_browse_uses_ancestor_weights_and_hides_closed(
    container: AsyncContainer, tree: Tree
) -> None:
    async with container() as c:
        svc = await c.get(TreeService)
        a = await svc.browse(tree.me, tree.a)
        root = await svc.browse(tree.me, tree.root)
        root_all = await svc.browse(tree.me, tree.root, include_closed=True)
        paused = await svc.browse(tree.me, tree.p)

    assert [c.id for c in a.path] == [tree.root, tree.a]
    assert a.active_branch
    assert [(f.info.id, f.priority) for f in a.folders] == [(tree.a1, Decimal("3.0"))]
    assert [(t.info.id, t.priority) for t in a.tasks] == [(tree.t_a, Decimal("1.2"))]

    # Открытые раньше закрытых, затем вес по убыванию: paused P (2.0) — раньше закрытого,
    # t_done (2.0) — после t_root (1.0), хотя вес больше.
    assert [f.info.id for f in root.folders] == [tree.a, tree.p]
    assert [t.info.id for t in root.tasks] == [tree.t_root]
    assert [t.info.id for t in root_all.tasks] == [tree.t_root, tree.t_done]

    assert not paused.active_branch


async def test_cycle_in_data_does_not_hang_reading(container: AsyncContainer, tree: Tree) -> None:
    """Цикл, появившийся в обход проверок (гонка переносов), не зацикливает CTE."""
    async with container() as c:
        x = await _folder(c, tree.me, tree.root, "X", "1.0")
        y = await _folder(c, tree.me, x, "Y", "2.0")
        t_y = await _task(c, tree.me, y, "t_y", "1.0")
    async with container() as c:
        session = await c.get(AsyncSession)
        await session.execute(
            text("UPDATE folders SET parent_id = :y WHERE id = :x"), {"x": x, "y": y}
        )
        await session.commit()

    async with container() as c:
        svc = await c.get(TreeService)
        nested = await svc.nested_tasks(tree.me, x)
        listing = await svc.browse(tree.me, x)
    assert [(t.info.id, t.priority) for t in nested] == [(t_y, Decimal("2.0"))]
    assert {c.id for c in listing.path} == {x, y}


async def test_equal_priority_started_first_then_oldest(
    container: AsyncContainer, tree: Tree
) -> None:
    async with container() as c:
        q = await _folder(c, tree.me, tree.root, "Q", "1.0")
        old = await _task(c, tree.me, q, "old", "1.0")
        new = await _task(c, tree.me, q, "new", "1.0")
        started = await _task(c, tree.me, q, "started", "1.0")
    async with container() as c:
        await (await c.get(TaskService)).change_status(tree.me, started, TaskStatus.IN_PROGRESS)
    async with container() as c:
        tasks = await (await c.get(TreeService)).nested_tasks(tree.me, q)
    assert [t.info.id for t in tasks] == [started, old, new]
