from sqlalchemy import Column, ForeignKey, Index, String, Table, Text, Uuid

from atomic_tasks.domain.entities.task import TaskStatus
from atomic_tasks.infrastructure.postgres.tables.base import (
    TIMESTAMPTZ,
    StrEnumType,
    WeightType,
    metadata,
)

tasks = Table(
    "tasks",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("folder_id", Uuid, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=True),
    Column("weight", WeightType, nullable=False),
    Column("status", StrEnumType(TaskStatus, 16), nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    Index("ix_tasks_owner_id_folder_id", "owner_id", "folder_id"),
    Index("ix_tasks_folder_id", "folder_id"),
)
