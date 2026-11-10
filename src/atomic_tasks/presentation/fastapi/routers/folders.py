from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, status

from atomic_tasks.application.services.folder_service import FolderService
from atomic_tasks.application.services.tree_service import (
    DEFAULT_NESTED_LIMIT,
    DEFAULT_NESTED_STATUSES,
    TreeService,
)
from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.presentation.fastapi.auth import CurrentIdentity
from atomic_tasks.presentation.fastapi.schemas.tree import (
    CreateFolderRequest,
    FolderListingResponse,
    FolderResponse,
    FolderStatusRequest,
    MoveFolderRequest,
    NestedTaskResponse,
    UpdateNodeRequest,
)

router = APIRouter(prefix="/folders", tags=["folders"], route_class=DishkaRoute)


@router.get("/root")
async def get_root_folder(
    identity: CurrentIdentity, folders: FromDishka[FolderService]
) -> FolderResponse:
    """Корень текущего пользователя — точка входа в дерево."""
    return FolderResponse.from_info(await folders.get_root(identity))


@router.get("/{folder_id}")
async def get_folder(
    folder_id: UUID, identity: CurrentIdentity, folders: FromDishka[FolderService]
) -> FolderResponse:
    return FolderResponse.from_info(await folders.get(identity, folder_id))


@router.get("/{folder_id}/children")
async def browse_folder(
    folder_id: UUID,
    identity: CurrentIdentity,
    tree: FromDishka[TreeService],
    include_closed: bool = False,
) -> FolderListingResponse:
    """Проводник: папка, путь от корня и прямые дети с абсолютным приоритетом."""
    listing = await tree.browse(identity, folder_id, include_closed=include_closed)
    return FolderListingResponse.from_listing(listing)


@router.get("/{folder_id}/nested-tasks")
async def list_nested_tasks(
    folder_id: UUID,
    identity: CurrentIdentity,
    tree: FromDishka[TreeService],
    status_: Annotated[
        list[TaskStatus] | None,
        Query(
            alias="status",
            description=f"По умолчанию: {', '.join(sorted(DEFAULT_NESTED_STATUSES))}.",
        ),
    ] = None,
    limit: int = DEFAULT_NESTED_LIMIT,
) -> list[NestedTaskResponse]:
    """Всё вложенное: задачи активного поддерева, сверху — что делать сейчас."""
    tasks = await tree.nested_tasks(identity, folder_id, statuses=status_, limit=limit)
    return [NestedTaskResponse.from_nested(t) for t in tasks]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: CreateFolderRequest, identity: CurrentIdentity, folders: FromDishka[FolderService]
) -> FolderResponse:
    info = await folders.create(
        identity,
        parent_id=body.parent_id,
        title=body.title,
        description=body.description,
        weight=body.weight,
    )
    return FolderResponse.from_info(info)


@router.patch("/{folder_id}")
async def update_folder(
    folder_id: UUID,
    body: UpdateNodeRequest,
    identity: CurrentIdentity,
    folders: FromDishka[FolderService],
) -> FolderResponse:
    info = await folders.update(
        identity,
        folder_id,
        title=body.title,
        description=body.description_change(),
        weight=body.weight,
    )
    return FolderResponse.from_info(info)


@router.post("/{folder_id}/move")
async def move_folder(
    folder_id: UUID,
    body: MoveFolderRequest,
    identity: CurrentIdentity,
    folders: FromDishka[FolderService],
) -> FolderResponse:
    info = await folders.move(identity, folder_id, new_parent_id=body.parent_id)
    return FolderResponse.from_info(info)


@router.post("/{folder_id}/status")
async def change_folder_status(
    folder_id: UUID,
    body: FolderStatusRequest,
    identity: CurrentIdentity,
    folders: FromDishka[FolderService],
) -> FolderResponse:
    return FolderResponse.from_info(await folders.change_status(identity, folder_id, body.status))


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    identity: CurrentIdentity,
    folders: FromDishka[FolderService],
    recursive: bool = False,
) -> None:
    """Непустая папка удаляется только с recursive=true — вместе со всем содержимым."""
    await folders.delete(identity, folder_id, recursive=recursive)
