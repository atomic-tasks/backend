"""Описания таблиц.

Каждый модуль с таблицами импортируется здесь, чтобы alembic видел полный metadata.
"""

from atomic_tasks.infrastructure.postgres.tables.api_tokens import api_tokens
from atomic_tasks.infrastructure.postgres.tables.base import mapper_registry, metadata
from atomic_tasks.infrastructure.postgres.tables.folders import folders
from atomic_tasks.infrastructure.postgres.tables.tasks import tasks
from atomic_tasks.infrastructure.postgres.tables.users import user_identities, users

__all__ = [
    "api_tokens",
    "folders",
    "mapper_registry",
    "metadata",
    "tasks",
    "user_identities",
    "users",
]
