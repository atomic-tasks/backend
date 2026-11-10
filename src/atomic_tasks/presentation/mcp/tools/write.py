from typing import Annotated
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import Field

from atomic_tasks.application.dto import (
    FolderInfo,
    FolderStatusChange,
    NewFolder,
    NewTask,
    StatusChange,
    TaskInfo,
    TaskStatusChange,
)
from atomic_tasks.application.services.bulk_service import BulkService
from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.task_service import TaskService
from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.presentation.mcp.tools.runtime import ToolRuntime, compact
from atomic_tasks.presentation.mcp.tools.schemas import (
    ChangedNode,
    ChangedNodes,
    Deleted,
    FolderInput,
    ItemDetails,
    Kind,
    StatusChangeInput,
    TaskInput,
    Weight,
)

WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)


def _new_task(task: TaskInput) -> NewTask:
    return NewTask(title=task.title, description=task.description, weight=task.weight)


def _new_folder(folder: FolderInput) -> NewFolder:
    return NewFolder(
        title=folder.title,
        description=folder.description,
        weight=folder.weight,
        folders=[_new_folder(f) for f in folder.folders],
        tasks=[_new_task(t) for t in folder.tasks],
    )


def _status_change(index: int, change: StatusChangeInput) -> StatusChange:
    """Разбор входа: статус должен подходить к типу узла. Правила переходов — в домене."""
    try:
        if change.kind == "folder":
            return FolderStatusChange(folder_id=change.id, status=FolderStatus(change.status))
        return TaskStatusChange(task_id=change.id, status=TaskStatus(change.status))
    except ValueError:
        allowed = FolderStatus if change.kind == "folder" else TaskStatus
        raise ToolError(
            f"changes[{index}]: у {'папки' if change.kind == 'folder' else 'задачи'} нет статуса "
            f"'{change.status}'. Допустимо: {', '.join(allowed)}."
        ) from None


def register_write_tools(server: MCPServer, runtime: ToolRuntime) -> None:
    @server.tool(annotations=WRITE)
    async def create_tree(
        parent_id: Annotated[
            UUID, Field(description="Папка, в которую кладём. Корень — тоже папка.")
        ],
        folders: list[FolderInput] | None = None,
        tasks: list[TaskInput] | None = None,
    ) -> Annotated[CallToolResult, ChangedNodes]:
        """Создать папки и задачи одной пачкой, с любой вложенностью (до 5 уровней, до 100 узлов).

        Всё или ничего: при ошибке не создаётся ничего, а текст ошибки указывает узел
        (например, `folders[1].tasks[0]`). Создавать можно только в active-папке.
        Вызывай после того, как пользователь подтвердил структуру. Вернёт созданное с id.
        """
        async with runtime.call() as (identity, rc):
            created = await (await rc.get(BulkService)).create_tree(
                identity,
                parent_id=parent_id,
                folders=[_new_folder(f) for f in folders or []],
                tasks=[_new_task(t) for t in tasks or []],
            )
        return compact(ChangedNodes(items=[ChangedNode.of(node) for node in created]))

    @server.tool(annotations=WRITE)
    async def set_status(
        changes: list[StatusChangeInput],
    ) -> Annotated[CallToolResult, ChangedNodes]:
        """Сменить статусы папок и задач (до 100 за раз). Применяются по порядку, всё или ничего.

        Папку можно закрыть (done), только когда внутри нет открытого — сначала закрой задачи,
        затем папку, в одном вызове. paused/cancelled у папки прячут её ветку из list_next_tasks.
        Если пользователь отказывается от задачи — cancelled, а не delete_item.
        """
        parsed = [_status_change(i, change) for i, change in enumerate(changes)]
        async with runtime.call() as (identity, rc):
            changed = await (await rc.get(BulkService)).set_statuses(identity, parsed)
        return compact(ChangedNodes(items=[ChangedNode.of(node) for node in changed]))

    @server.tool(annotations=WRITE)
    async def update_item(
        kind: Kind,
        id: UUID,
        *,
        title: str | None = None,
        description: Annotated[
            str | None, Field(description="Пустая строка очищает описание.")
        ] = None,
        weight: Weight = None,
        parent_id: Annotated[
            UUID | None, Field(description="Перенести в эту папку (она должна быть active).")
        ] = None,
    ) -> Annotated[CallToolResult, ItemDetails]:
        """Переименовать, сменить описание или вес, перенести папку или задачу.

        Не переданные поля не меняются. Перенос выполняется после остальных изменений:
        если он не удался, остальные уже сохранены. Статус меняет set_status.
        """
        fields_changed = title is not None or description is not None or weight is not None
        info: FolderInfo | TaskInfo
        async with runtime.call() as (identity, rc):
            if kind == "folder":
                folders = await rc.get(FolderService)
                info = await folders.get(identity, id)
                if fields_changed:
                    info = await folders.update(
                        identity, id, title=title, description=description, weight=weight
                    )
                if parent_id is not None:
                    info = await folders.move(identity, id, new_parent_id=parent_id)
            else:
                tasks = await rc.get(TaskService)
                info = await tasks.get(identity, id)
                if fields_changed:
                    info = await tasks.update(
                        identity, id, title=title, description=description, weight=weight
                    )
                if parent_id is not None:
                    info = await tasks.move(identity, id, new_folder_id=parent_id)
        return compact(ItemDetails.of(info))

    @server.tool(annotations=DELETE)
    async def delete_item(
        kind: Kind,
        id: UUID,
        recursive: Annotated[
            bool, Field(description="Только для папки: удалить вместе со всем содержимым.")
        ] = False,
    ) -> Annotated[CallToolResult, Deleted]:
        """Удалить папку или задачу навсегда, без восстановления.

        Удаляй, только если пользователь прямо попросил удалить; отказ от задачи — это
        set_status cancelled. Непустую папку без recursive удалить нельзя.
        """
        async with runtime.call() as (identity, rc):
            if kind == "folder":
                await (await rc.get(FolderService)).delete(identity, id, recursive=recursive)
            else:
                await (await rc.get(TaskService)).delete(identity, id)
        return compact(Deleted(id=id, kind=kind))
