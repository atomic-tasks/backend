from sqlalchemy import Column, ForeignKey, Index, String, Table, Text, Uuid, text

from atomic_tasks.domain.entities.folder import FolderStatus
from atomic_tasks.infrastructure.postgres.tables.base import (
    TIMESTAMPTZ,
    StrEnumType,
    WeightType,
    metadata,
)

folders = Table(
    "folders",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    # CASCADE реализует recursive-удаление одним DELETE;
    # без recursive сервис сначала проверяет, что детей нет
    Column("parent_id", Uuid, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=True),
    Column("weight", WeightType, nullable=False),
    Column("status", StrEnumType(FolderStatus, 16), nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    Index("ix_folders_owner_id_parent_id", "owner_id", "parent_id"),
    Index("ix_folders_parent_id", "parent_id"),  # CTE вниз по дереву и каскад
    # Ровно один корень на пользователя — гарантия базы, а не сервиса
    Index(
        "uq_folders_owner_id_root",
        "owner_id",
        unique=True,
        postgresql_where=text("parent_id IS NULL"),
    ),
)
