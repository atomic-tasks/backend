"""Схемы папок и задач (spec 0003).

Вес и приоритет наружу — JSON-числа: pydantic сериализует Decimal строкой, клиентам это неудобно.
На входе вес — Decimal без границ: диапазон и точность проверяет доменный Weight.
"""

from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from atomic_tasks.application.dto import (
    FolderCrumb,
    FolderInfo,
    FolderListing,
    NestedTask,
    RankedFolder,
    RankedTask,
    TaskInfo,
)
from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.domain.entities.task import TaskStatus

_WEIGHT_DOC = "От 0.5 до 2.0 с шагом 0.01; по умолчанию 1.0."


class FolderResponse(BaseModel):
    id: UUID
    parent_id: UUID | None = Field(description="null — корень.")
    title: str
    description: str | None
    weight: float
    status: FolderStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_info(cls, info: FolderInfo) -> Self:
        return cls(**{**info.__dict__, "weight": float(info.weight)})


class TaskResponse(BaseModel):
    id: UUID
    folder_id: UUID
    title: str
    description: str | None
    weight: float
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_info(cls, info: TaskInfo) -> Self:
        return cls(**{**info.__dict__, "weight": float(info.weight)})


class FolderCrumbResponse(BaseModel):
    id: UUID
    title: str
    weight: float
    status: FolderStatus

    @classmethod
    def from_crumb(cls, crumb: FolderCrumb) -> Self:
        return cls(id=crumb.id, title=crumb.title, weight=float(crumb.weight), status=crumb.status)


class RankedFolderResponse(FolderResponse):
    priority: float = Field(description="Абсолютный: произведение весов от корня.")

    @classmethod
    def from_ranked(cls, ranked: RankedFolder) -> Self:
        base = FolderResponse.from_info(ranked.info).model_dump()
        return cls(**base, priority=float(ranked.priority))


class RankedTaskResponse(TaskResponse):
    priority: float = Field(description="Абсолютный: произведение весов от корня.")

    @classmethod
    def from_ranked(cls, ranked: RankedTask) -> Self:
        base = TaskResponse.from_info(ranked.info).model_dump()
        return cls(**base, priority=float(ranked.priority))


class FolderListingResponse(BaseModel):
    folder: FolderResponse
    path: list[FolderCrumbResponse] = Field(description="От корня до папки включительно.")
    active_branch: bool = Field(description="Папка и все её предки в статусе active.")
    folders: list[RankedFolderResponse]
    tasks: list[RankedTaskResponse]

    @classmethod
    def from_listing(cls, listing: FolderListing) -> Self:
        return cls(
            folder=FolderResponse.from_info(listing.folder),
            path=[FolderCrumbResponse.from_crumb(c) for c in listing.path],
            active_branch=listing.active_branch,
            folders=[RankedFolderResponse.from_ranked(f) for f in listing.folders],
            tasks=[RankedTaskResponse.from_ranked(t) for t in listing.tasks],
        )


class NestedTaskResponse(TaskResponse):
    priority: float = Field(description="Относительно выбранной папки.")
    path: list[FolderCrumbResponse] = Field(
        description="Папки от выбранной (не включая) до папки задачи; пусто — задача прямо в ней.",
    )

    @classmethod
    def from_nested(cls, nested: NestedTask) -> Self:
        base = TaskResponse.from_info(nested.info).model_dump()
        return cls(
            **base,
            priority=float(nested.priority),
            path=[FolderCrumbResponse.from_crumb(c) for c in nested.path],
        )


class CreateFolderRequest(BaseModel):
    parent_id: UUID
    title: str
    description: str | None = None
    weight: Decimal | None = Field(default=None, description=_WEIGHT_DOC)


class CreateTaskRequest(BaseModel):
    folder_id: UUID
    title: str
    description: str | None = None
    weight: Decimal | None = Field(default=None, description=_WEIGHT_DOC)


class UpdateNodeRequest(BaseModel):
    """Отсутствующее поле не меняется; description: null или "" очищает описание."""

    title: str | None = None
    description: str | None = None
    weight: Decimal | None = Field(default=None, description=_WEIGHT_DOC)

    def description_change(self) -> str | None:
        """Сервис понимает None как «не менять», а "" как «очистить» — переводим явный null."""
        if "description" not in self.model_fields_set:
            return None
        return self.description or ""


class MoveFolderRequest(BaseModel):
    parent_id: UUID


class MoveTaskRequest(BaseModel):
    folder_id: UUID


class FolderStatusRequest(BaseModel):
    status: FolderStatus


class TaskStatusRequest(BaseModel):
    status: TaskStatus
