"""Пачки для агента на настоящем Postgres (spec 0004): атомарность и порядок внутри пачки."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from dishka import AsyncContainer

from atomic_tasks.application.dto import (
    AuthMethod,
    FolderInfo,
    FolderStatusChange,
    Identity,
    NewFolder,
    NewTask,
    TaskInfo,
    TaskStatusChange,
)
from atomic_tasks.application.errors import BulkItemError, InvalidQueryError
from atomic_tasks.application.services.bulk_service import BulkService
from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.tree_service import TreeService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.domain.exceptions import FolderHasOpenItemsError, InvalidFieldError


@pytest.fixture
async def container(
    empty_db: Settings,
    settings_with_allowlist: Settings,
) -> AsyncIterator[AsyncContainer]:
    container = create_container(settings_with_allowlist)
    yield container
    await container.close()


@pytest.fixture
async def me(container: AsyncContainer) -> Identity:
    async with container() as c:
        user = await (await c.get(UserService)).create(display_name="alice", email=None)
    return Identity(user_id=user.id, scope=TokenScope.WRITE, method=AuthMethod.PAT)


async def _root_id(container: AsyncContainer, me: Identity) -> UUID:
    async with container() as c:
        return (await (await c.get(FolderService)).get_root(me)).id


async def _subtree_size(container: AsyncContainer, me: Identity, folder_id: UUID) -> int:
    """Сколько задач в поддереве — отдельной сессией, как следующий запрос клиента."""
    async with container() as c:
        tasks = await (await c.get(TreeService)).nested_tasks(
            me, folder_id, statuses=set(TaskStatus), limit=500
        )
    return len(tasks)


async def test_create_tree_builds_nested_folders(container: AsyncContainer, me: Identity) -> None:
    """Три уровня папок: flush после каждой папки держит порядок вставок по FK."""
    root = await _root_id(container, me)
    tree = NewFolder(
        title="Go",
        folders=[
            NewFolder(
                title="Конкурентность",
                weight=None,
                folders=[NewFolder(title="Каналы", tasks=[NewTask(title="Прочитать главу")])],
                tasks=[NewTask(title="Горутины", weight=None)],
            ),
        ],
        tasks=[NewTask(title="Поставить Go")],
    )
    async with container() as c:
        created = await (await c.get(BulkService)).create_tree(me, parent_id=root, folders=[tree])

    by_title = {node.title: node for node in created}
    assert [node.title for node in created] == [
        "Go",
        "Конкурентность",
        "Каналы",
        "Прочитать главу",
        "Горутины",
        "Поставить Go",
    ]
    go, conc, chan = by_title["Go"], by_title["Конкурентность"], by_title["Каналы"]
    assert isinstance(go, FolderInfo)
    assert isinstance(conc, FolderInfo)
    assert isinstance(chan, FolderInfo)
    assert (go.parent_id, conc.parent_id, chan.parent_id) == (root, go.id, conc.id)
    reading = by_title["Прочитать главу"]
    assert isinstance(reading, TaskInfo)
    assert reading.folder_id == chan.id
    assert await _subtree_size(container, me, root) == 3


async def test_create_tree_error_deep_inside_creates_nothing(
    container: AsyncContainer, me: Identity
) -> None:
    root = await _root_id(container, me)
    tree = NewFolder(
        title="ok",
        folders=[NewFolder(title="ok", tasks=[NewTask(title="ok"), NewTask(title="  ")])],
    )
    async with container() as c:
        with pytest.raises(BulkItemError) as error:
            await (await c.get(BulkService)).create_tree(me, parent_id=root, folders=[tree])
    assert error.value.address == "folders[0].folders[0].tasks[1]"
    assert isinstance(error.value.cause, InvalidFieldError)

    async with container() as c:
        listing = await (await c.get(TreeService)).browse(me, root, include_closed=True)
    assert listing.folders == []
    assert listing.tasks == []


async def test_create_tree_limits(container: AsyncContainer, me: Identity) -> None:
    root = await _root_id(container, me)
    deep = NewFolder(title="6")
    for level in range(5, 0, -1):
        deep = NewFolder(title=str(level), folders=[deep])
    async with container() as c:
        bulk = await c.get(BulkService)
        with pytest.raises(InvalidQueryError, match="вложенность"):
            await bulk.create_tree(me, parent_id=root, folders=[deep])
        with pytest.raises(InvalidQueryError, match="большая"):
            await bulk.create_tree(
                me, parent_id=root, tasks=[NewTask(title=f"t{i}") for i in range(101)]
            )


async def test_set_statuses_sees_previous_items(container: AsyncContainer, me: Identity) -> None:
    """«Закрыть задачи, затем папку» в одной пачке: правило папки видит закрытые задачи."""
    root = await _root_id(container, me)
    async with container() as c:
        created = await (await c.get(BulkService)).create_tree(
            me,
            parent_id=root,
            folders=[NewFolder(title="f", tasks=[NewTask(title="a"), NewTask(title="b")])],
        )
    folder, a, b = created
    async with container() as c:
        changed = await (await c.get(BulkService)).set_statuses(
            me,
            [
                TaskStatusChange(task_id=a.id, status=TaskStatus.DONE),
                TaskStatusChange(task_id=b.id, status=TaskStatus.CANCELLED),
                FolderStatusChange(folder_id=folder.id, status=FolderStatus.DONE),
            ],
        )
    assert [node.status for node in changed] == ["done", "cancelled", "done"]
    async with container() as c:
        assert (await (await c.get(FolderService)).get(me, folder.id)).status is FolderStatus.DONE


async def test_set_statuses_error_rolls_back_earlier_items(
    container: AsyncContainer, me: Identity
) -> None:
    root = await _root_id(container, me)
    async with container() as c:
        created = await (await c.get(BulkService)).create_tree(
            me,
            parent_id=root,
            folders=[NewFolder(title="f", tasks=[NewTask(title="a"), NewTask(title="b")])],
        )
    folder, a, _ = created
    async with container() as c:
        with pytest.raises(BulkItemError) as error:
            await (await c.get(BulkService)).set_statuses(
                me,
                [
                    TaskStatusChange(task_id=a.id, status=TaskStatus.DONE),
                    # b ещё открыта — папку закрыть нельзя.
                    FolderStatusChange(folder_id=folder.id, status=FolderStatus.DONE),
                ],
            )
    assert error.value.address == "changes[1]"
    assert isinstance(error.value.cause, FolderHasOpenItemsError)
    # Первая задача тоже не закрылась: пачка откатилась целиком.
    assert await _subtree_size(container, me, folder.id) == 2
    async with container() as c:
        open_tasks = await (await c.get(TreeService)).nested_tasks(me, folder.id)
    assert {t.info.id for t in open_tasks} == {a.id, created[2].id}
