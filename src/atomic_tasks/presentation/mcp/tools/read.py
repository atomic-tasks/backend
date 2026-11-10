from typing import Annotated
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import Field

from atomic_tasks.application.dto import FolderCrumb, FolderInfo, RankedFolder, RankedTask, TaskInfo
from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.task_service import TaskService
from atomic_tasks.application.services.tree_service import TreeService
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.presentation.mcp.tools.runtime import ToolRuntime, compact
from atomic_tasks.presentation.mcp.tools.schemas import (
    FolderView,
    ItemDetails,
    Kind,
    ListedNode,
    NextTask,
    NextTasks,
    TaskStatusName,
    priority,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
DEFAULT_NEXT_LIMIT = 20


def _path(crumbs: list[FolderCrumb]) -> str:
    return " / ".join(crumb.title for crumb in crumbs)


def _listed(node: RankedFolder | RankedTask) -> ListedNode:
    return ListedNode(
        id=node.info.id,
        title=node.info.title,
        status=node.info.status,
        priority=priority(node.priority),
    )


def register_read_tools(server: MCPServer, runtime: ToolRuntime) -> None:
    @server.tool(annotations=READ_ONLY)
    async def browse_folder(
        folder_id: Annotated[UUID | None, Field(description="Без id — корень.")] = None,
        include_closed: Annotated[
            bool, Field(description="Показать и done/cancelled; по умолчанию скрыты.")
        ] = False,
    ) -> Annotated[CallToolResult, FolderView]:
        """Открыть папку: путь от корня, подпапки и задачи с приоритетом (больше — важнее).

        Начинай с этого тула без id, прежде чем создавать что-то: найди подходящую папку
        и проверь, нет ли уже похожих задач. Описания тут нет — их отдаёт get_item.
        """
        async with runtime.call() as (identity, rc):
            if folder_id is None:
                folder_id = (await (await rc.get(FolderService)).get_root(identity)).id
            listing = await (await rc.get(TreeService)).browse(
                identity, folder_id, include_closed=include_closed
            )
        return compact(
            FolderView(
                id=listing.folder.id,
                title=listing.folder.title,
                status=listing.folder.status,
                path=_path(listing.path),
                active_branch=listing.active_branch,
                folders=[_listed(f) for f in listing.folders],
                tasks=[_listed(t) for t in listing.tasks],
            )
        )

    @server.tool(annotations=READ_ONLY)
    async def list_next_tasks(
        folder_id: Annotated[UUID | None, Field(description="Без id — от корня.")] = None,
        statuses: Annotated[
            list[TaskStatusName] | None,
            Field(description="По умолчанию todo и in_progress."),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=500)] = DEFAULT_NEXT_LIMIT,
    ) -> Annotated[CallToolResult, NextTasks]:
        """Что делать сейчас: задачи всего поддерева, сверху — с наибольшим приоритетом.

        Приоритет — произведение весов по пути от выбранной папки. Ветки в paused/cancelled/done
        папках пропускаются. Вызывай, когда пользователь спрашивает, за что взяться.
        """
        async with runtime.call() as (identity, rc):
            if folder_id is None:
                folder_id = (await (await rc.get(FolderService)).get_root(identity)).id
            tasks = await (await rc.get(TreeService)).nested_tasks(
                identity,
                folder_id,
                statuses=None if statuses is None else {TaskStatus(s) for s in statuses},
                limit=limit,
            )
        return compact(
            NextTasks(
                tasks=[
                    NextTask(
                        id=t.info.id,
                        title=t.info.title,
                        status=t.info.status,
                        priority=priority(t.priority),
                        path=_path(t.path),
                    )
                    for t in tasks
                ],
            )
        )

    @server.tool(annotations=READ_ONLY)
    async def get_item(kind: Kind, id: UUID) -> Annotated[CallToolResult, ItemDetails]:
        """Папка или задача целиком: с описанием, весом и родителем."""
        info: FolderInfo | TaskInfo
        async with runtime.call() as (identity, rc):
            if kind == "folder":
                info = await (await rc.get(FolderService)).get(identity, id)
            else:
                info = await (await rc.get(TaskService)).get(identity, id)
        return compact(ItemDetails.of(info))
