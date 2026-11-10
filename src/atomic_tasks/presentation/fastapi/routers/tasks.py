from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, status

from atomic_tasks.application.services.task_service import TaskService
from atomic_tasks.presentation.fastapi.auth import CurrentIdentity
from atomic_tasks.presentation.fastapi.schemas.tree import (
    CreateTaskRequest,
    MoveTaskRequest,
    TaskResponse,
    TaskStatusRequest,
    UpdateNodeRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], route_class=DishkaRoute)


@router.get("/{task_id}")
async def get_task(
    task_id: UUID, identity: CurrentIdentity, tasks: FromDishka[TaskService]
) -> TaskResponse:
    return TaskResponse.from_info(await tasks.get(identity, task_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest, identity: CurrentIdentity, tasks: FromDishka[TaskService]
) -> TaskResponse:
    info = await tasks.create(
        identity,
        folder_id=body.folder_id,
        title=body.title,
        description=body.description,
        weight=body.weight,
    )
    return TaskResponse.from_info(info)


@router.patch("/{task_id}")
async def update_task(
    task_id: UUID,
    body: UpdateNodeRequest,
    identity: CurrentIdentity,
    tasks: FromDishka[TaskService],
) -> TaskResponse:
    info = await tasks.update(
        identity,
        task_id,
        title=body.title,
        description=body.description_change(),
        weight=body.weight,
    )
    return TaskResponse.from_info(info)


@router.post("/{task_id}/move")
async def move_task(
    task_id: UUID,
    body: MoveTaskRequest,
    identity: CurrentIdentity,
    tasks: FromDishka[TaskService],
) -> TaskResponse:
    return TaskResponse.from_info(await tasks.move(identity, task_id, new_folder_id=body.folder_id))


@router.post("/{task_id}/status")
async def change_task_status(
    task_id: UUID,
    body: TaskStatusRequest,
    identity: CurrentIdentity,
    tasks: FromDishka[TaskService],
) -> TaskResponse:
    return TaskResponse.from_info(await tasks.change_status(identity, task_id, body.status))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID, identity: CurrentIdentity, tasks: FromDishka[TaskService]
) -> None:
    await tasks.delete(identity, task_id)
