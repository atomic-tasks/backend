"""Дерево на настоящем Postgres: CTE, корень, каскад, изоляция (spec 0002)."""

import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from dishka import AsyncContainer
from sqlalchemy.exc import IntegrityError

from atomic_tasks.application.dto import AuthMethod, FolderInfo, Identity
from atomic_tasks.application.errors import NotFoundError
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.oidc import VerifiedClaims
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.identity_service import IdentityService
from atomic_tasks.application.services.task_service import TaskService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.dishka.container import create_container
from atomic_tasks.config.settings import Settings
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.domain.exceptions import FolderCycleError, InsufficientScopeError
from atomic_tasks.domain.values import ItemCount


@pytest.fixture
async def container(
    empty_db: Settings,
    settings_with_allowlist: Settings,
) -> AsyncIterator[AsyncContainer]:
    container = create_container(settings_with_allowlist)
    yield container
    await container.close()


def _me(user_id: UUID, scope: TokenScope = TokenScope.WRITE) -> Identity:
    """Identity как после входа по PAT с нужными правами."""
    return Identity(user_id=user_id, scope=scope, method=AuthMethod.PAT)


async def _new_user(container: AsyncContainer, name: str = "alice") -> Identity:
    """Пользователь через CLI-сценарий (вместе с ним создаётся корень)."""
    async with container() as c:
        user = await (await c.get(UserService)).create(display_name=name, email=None)
    return _me(user.id)


async def _root(container: AsyncContainer, me: Identity) -> FolderInfo:
    """Корень пользователя."""
    async with container() as c:
        return await (await c.get(FolderService)).get_root(me)


async def _folder(container: AsyncContainer, me: Identity, parent_id: UUID) -> FolderInfo:
    """Папка в parent_id, каждая — в своей сессии, как отдельный запрос клиента."""
    async with container() as c:
        return await (await c.get(FolderService)).create(me, parent_id=parent_id, title="f")


async def _repo_folder(c: AsyncContainer, folder_id: UUID) -> Folder:
    """Сущность из репозитория — для прямой проверки CTE-запросов."""
    folder = await (await c.get(FolderRepository)).get(folder_id)
    assert folder is not None
    return folder


async def test_every_new_user_gets_exactly_one_root(container: AsyncContainer) -> None:
    me = await _new_user(container)
    async with container() as c:
        bob = await (await c.get(IdentityService)).resolve(
            VerifiedClaims(
                issuer="https://idp.test/auth/v1",
                subject="sub-1",
                email="bob@example.com",
                email_verified=True,
                name=None,
            ),
        )
    root = await _root(container, me)
    assert root.parent_id is None
    assert (await _root(container, _me(bob.id))).parent_id is None

    # Второй корень запрещает база, а не сервис
    async with container() as c:
        repo = await c.get(FolderRepository)
        repo.add(Folder.new_root(id=uuid.uuid7(), owner_id=me.user_id, now=root.created_at))
        with pytest.raises(IntegrityError):
            await (await c.get(TransactionManager)).commit()


async def test_tree_queries(container: AsyncContainer) -> None:
    """root → a → b → c; задачи: в a (открыта), в c (открыта и закрыта)."""
    me = await _new_user(container)
    root = await _root(container, me)
    a = await _folder(container, me, root.id)
    b = await _folder(container, me, a.id)
    c_ = await _folder(container, me, b.id)
    async with container() as c:
        tasks = await c.get(TaskService)
        await tasks.create(me, folder_id=a.id, title="t1")
        await tasks.create(me, folder_id=c_.id, title="t2")
        closed = await tasks.create(me, folder_id=c_.id, title="t3")
        await tasks.change_status(me, closed.id, TaskStatus.DONE)

    async with container() as c:
        repo = await c.get(FolderRepository)
        path = await repo.path_to_root(await _repo_folder(c, c_.id))
        assert {ref.id for ref in path} == {c_.id, b.id, a.id, root.id}
        assert await repo.count_open_descendants(await _repo_folder(c, a.id)) == ItemCount(
            folders=2, tasks=2
        )
        assert await repo.count_children(await _repo_folder(c, a.id)) == ItemCount(
            folders=1, tasks=1
        )


async def test_move_into_descendant_is_rejected(container: AsyncContainer) -> None:
    me = await _new_user(container)
    root = await _root(container, me)
    a = await _folder(container, me, root.id)
    b = await _folder(container, me, a.id)
    async with container() as c:
        with pytest.raises(FolderCycleError):
            await (await c.get(FolderService)).move(me, a.id, new_parent_id=b.id)


async def test_recursive_delete_removes_subtree(container: AsyncContainer) -> None:
    me = await _new_user(container)
    root = await _root(container, me)
    a = await _folder(container, me, root.id)
    b = await _folder(container, me, a.id)
    async with container() as c:
        task = await (await c.get(TaskService)).create(me, folder_id=b.id, title="t")
        await (await c.get(FolderService)).delete(me, a.id, recursive=True)
    async with container() as c:
        with pytest.raises(NotFoundError):
            await (await c.get(FolderService)).get(me, b.id)
        with pytest.raises(NotFoundError):
            await (await c.get(TaskService)).get(me, task.id)


async def test_read_token_cannot_write(container: AsyncContainer) -> None:
    me = await _new_user(container)
    root = await _root(container, me)
    reader = _me(me.user_id, TokenScope.READ)
    async with container() as c:
        with pytest.raises(InsufficientScopeError):
            await (await c.get(FolderService)).create(reader, parent_id=root.id, title="x")
        with pytest.raises(InsufficientScopeError):
            await (await c.get(TaskService)).create(reader, folder_id=root.id, title="x")


async def test_users_are_isolated(container: AsyncContainer) -> None:
    alice = await _new_user(container, "alice")
    bob = await _new_user(container, "bob")
    alice_root = await _root(container, alice)
    bob_root = await _root(container, bob)
    alice_folder = await _folder(container, alice, alice_root.id)
    async with container() as c:
        alice_task = await (await c.get(TaskService)).create(
            alice, folder_id=alice_folder.id, title="secret"
        )

    async with container() as c:
        folders = await c.get(FolderService)
        tasks = await c.get(TaskService)
        attempts = [
            folders.get(bob, alice_folder.id),
            folders.update(bob, alice_folder.id, title="x"),
            folders.move(bob, alice_folder.id, new_parent_id=bob_root.id),
            folders.move(alice, alice_folder.id, new_parent_id=bob_root.id),
            folders.change_status(bob, alice_folder.id, FolderStatus.CANCELLED),
            folders.delete(bob, alice_folder.id, recursive=True),
            folders.create(bob, parent_id=alice_folder.id, title="x"),
            tasks.get(bob, alice_task.id),
            tasks.update(bob, alice_task.id, title="x"),
            tasks.move(bob, alice_task.id, new_folder_id=bob_root.id),
            tasks.change_status(bob, alice_task.id, TaskStatus.DONE),
            tasks.delete(bob, alice_task.id),
            tasks.create(bob, folder_id=alice_folder.id, title="x"),
        ]
        # Каждый вызов — чужой id или чужая папка-цель: везде одинаковый «не найден»
        for attempt in attempts:
            with pytest.raises(NotFoundError):
                await attempt

    async with container() as c:
        task = await (await c.get(TaskService)).get(alice, alice_task.id)
        assert task.title == "secret"
        assert task.status is TaskStatus.TODO
