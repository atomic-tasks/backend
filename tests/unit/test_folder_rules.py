"""Доменные правила дерева (spec 0002): то, что дорого сломать незаметно."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.entities.task import Task, TaskStatus
from atomic_tasks.domain.exceptions import (
    DoneAncestorError,
    FolderCycleError,
    FolderHasOpenItemsError,
    FolderNotActiveError,
    FolderNotEmptyError,
    InvalidFieldError,
    RootFolderProtectedError,
)
from atomic_tasks.domain.values import ItemCount, Weight

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
NOTHING = ItemCount()


def make_root(owner_id: UUID | None = None) -> Folder:
    """Корень; owner_id — чтобы сделать второе дерево того же владельца."""
    return Folder.new_root(id=uuid.uuid7(), owner_id=owner_id or uuid.uuid7(), now=NOW)


def make_folder(parent: Folder, status: FolderStatus = FolderStatus.ACTIVE) -> Folder:
    """Папка в parent; статус ставится напрямую, в обход правил, чтобы собрать нужное дерево."""
    folder = Folder.create(
        id=uuid.uuid7(),
        parent=parent,
        title="f",
        description=None,
        weight=Weight.default(),
        now=NOW,
    )
    folder.status = status
    return folder


def make_task(folder: Folder) -> Task:
    """Задача в статусе todo."""
    return Task.create(
        id=uuid.uuid7(),
        folder=folder,
        title="t",
        description=None,
        weight=Weight.default(),
        now=NOW,
    )


@pytest.mark.parametrize("raw", ["0.49", "2.01", "1.005", "NaN", "Infinity"])
def test_weight_rejects_out_of_range_and_extra_precision(raw: str) -> None:
    with pytest.raises(InvalidFieldError):
        Weight(Decimal(raw))


def test_weight_normalizes_scale() -> None:
    assert Weight(Decimal("1.1")) == Weight(Decimal("1.10"))
    assert Weight(Decimal("0.5")).value == Decimal("0.50")


def test_folder_cannot_move_into_itself_or_descendant() -> None:
    root = make_root()
    a = make_folder(root)
    b = make_folder(a)
    with pytest.raises(FolderCycleError):
        a.move_to(a, {a.id, root.id}, NOW)
    with pytest.raises(FolderCycleError):
        a.move_to(b, {b.id, a.id, root.id}, NOW)


def test_root_is_protected() -> None:
    root = make_root()
    other = make_folder(make_root(root.owner_id))
    with pytest.raises(RootFolderProtectedError):
        root.rename("x", NOW)
    with pytest.raises(RootFolderProtectedError):
        root.set_weight(Weight(Decimal(2)), NOW)
    with pytest.raises(RootFolderProtectedError):
        root.move_to(other, {other.id}, NOW)
    with pytest.raises(RootFolderProtectedError):
        root.ensure_deletable(NOTHING, recursive=True)
    with pytest.raises(RootFolderProtectedError):
        root.change_status(
            FolderStatus.PAUSED, open_descendants=NOTHING, has_done_ancestor=False, now=NOW
        )


def test_done_requires_closed_subtree() -> None:
    folder = make_folder(make_root())
    with pytest.raises(FolderHasOpenItemsError):
        folder.change_status(
            FolderStatus.DONE,
            open_descendants=ItemCount(tasks=1),
            has_done_ancestor=False,
            now=NOW,
        )
    folder.change_status(
        FolderStatus.DONE, open_descendants=NOTHING, has_done_ancestor=False, now=NOW
    )
    assert folder.status is FolderStatus.DONE


@pytest.mark.parametrize("status", [FolderStatus.PAUSED, FolderStatus.CANCELLED])
def test_pause_and_cancel_ignore_open_content(status: FolderStatus) -> None:
    folder = make_folder(make_root())
    folder.change_status(
        status, open_descendants=ItemCount(folders=2, tasks=5), has_done_ancestor=False, now=NOW
    )
    assert folder.status is status


def test_nothing_reopens_under_done_ancestor() -> None:
    root = make_root()
    folder = make_folder(root, FolderStatus.CANCELLED)
    with pytest.raises(DoneAncestorError):
        folder.change_status(
            FolderStatus.ACTIVE, open_descendants=NOTHING, has_done_ancestor=True, now=NOW
        )
    task = make_task(make_folder(root))
    task.status = TaskStatus.DONE
    with pytest.raises(DoneAncestorError):
        task.change_status(TaskStatus.TODO, has_done_ancestor=True, now=NOW)
    # Закрыть под done можно
    task.change_status(TaskStatus.CANCELLED, has_done_ancestor=True, now=NOW)


@pytest.mark.parametrize("status", [FolderStatus.PAUSED, FolderStatus.DONE, FolderStatus.CANCELLED])
def test_nothing_is_created_or_moved_into_inactive_folder(status: FolderStatus) -> None:
    root = make_root()
    inactive = make_folder(root, status)
    with pytest.raises(FolderNotActiveError):
        make_task(inactive)
    with pytest.raises(FolderNotActiveError):
        make_folder(inactive)
    with pytest.raises(FolderNotActiveError):
        make_task(root).move_to(inactive, NOW)
    with pytest.raises(FolderNotActiveError):
        make_folder(root).move_to(inactive, {inactive.id, root.id}, NOW)


def test_non_empty_folder_needs_recursive_delete() -> None:
    folder = make_folder(make_root())
    with pytest.raises(FolderNotEmptyError):
        folder.ensure_deletable(ItemCount(tasks=1), recursive=False)
    folder.ensure_deletable(ItemCount(tasks=1), recursive=True)
    folder.ensure_deletable(NOTHING, recursive=False)
