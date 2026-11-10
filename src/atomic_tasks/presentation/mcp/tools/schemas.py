"""Вход и компактные ответы MCP-тулов. Лишнее поле в ответе — лишние токены в контексте агента."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from atomic_tasks.application.dto import FolderInfo, TaskInfo

Kind = Literal["folder", "task"]
StatusName = Literal["active", "todo", "in_progress", "paused", "done", "cancelled"]
TaskStatusName = Literal["todo", "in_progress", "paused", "done", "cancelled"]

PRIORITY_DIGITS = 3

Weight = Annotated[
    Decimal | None,
    Field(description="0.5–2.0, шаг 0.01; по умолчанию 1.0. Больше — важнее."),
]
Description = Annotated[str | None, Field(description="Необязательные детали, до 10 000 символов.")]


def priority(value: Decimal) -> float:
    return round(float(value), PRIORITY_DIGITS)


# --- Вход ---


class TaskInput(BaseModel):
    title: str
    description: Description = None
    weight: Weight = None


class FolderInput(BaseModel):
    title: str
    description: Description = None
    weight: Weight = None
    folders: list[FolderInput] = []
    tasks: list[TaskInput] = []


class StatusChangeInput(BaseModel):
    kind: Kind
    id: UUID
    status: Annotated[
        StatusName,
        Field(
            description="Папка: active, paused, done, cancelled. "
            "Задача: todo, in_progress, paused, done, cancelled."
        ),
    ]


# --- Ответы ---


class ListedNode(BaseModel):
    """Подпапка или задача в проводнике; тип понятен из списка, в котором узел лежит."""

    id: UUID
    title: str
    status: str
    priority: float


class FolderView(BaseModel):
    id: UUID
    title: str
    status: str
    path: str = Field(description="Путь от корня, включая саму папку.")
    active_branch: bool = Field(
        description="Папка и все предки active — её задачи видны в list_next_tasks от корня."
    )
    folders: list[ListedNode]
    tasks: list[ListedNode]


class NextTask(BaseModel):
    id: UUID
    title: str
    status: str
    priority: float
    path: str = Field(description="Папки от выбранной до папки задачи; пусто — прямо в выбранной.")


class NextTasks(BaseModel):
    tasks: list[NextTask]


class ItemDetails(BaseModel):
    id: UUID
    kind: Kind
    parent_id: UUID | None = Field(description="Папка-родитель; у корня — null.")
    title: str
    description: str | None
    status: str
    weight: float

    @classmethod
    def of(cls, info: FolderInfo | TaskInfo) -> ItemDetails:
        if isinstance(info, FolderInfo):
            return cls(
                id=info.id,
                kind="folder",
                parent_id=info.parent_id,
                title=info.title,
                description=info.description,
                status=info.status,
                weight=float(info.weight),
            )
        return cls(
            id=info.id,
            kind="task",
            parent_id=info.folder_id,
            title=info.title,
            description=info.description,
            status=info.status,
            weight=float(info.weight),
        )


class ChangedNode(BaseModel):
    id: UUID
    kind: Kind
    parent_id: UUID | None
    title: str
    status: str

    @classmethod
    def of(cls, info: FolderInfo | TaskInfo) -> ChangedNode:
        kind: Kind
        if isinstance(info, FolderInfo):
            parent_id, kind = info.parent_id, "folder"
        else:
            parent_id, kind = info.folder_id, "task"
        return cls(id=info.id, kind=kind, parent_id=parent_id, title=info.title, status=info.status)


class ChangedNodes(BaseModel):
    items: list[ChangedNode]


class Deleted(BaseModel):
    id: UUID
    kind: Kind
