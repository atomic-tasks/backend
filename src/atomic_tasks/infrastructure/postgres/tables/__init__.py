"""Описания таблиц.

Каждый модуль с таблицами импортируется здесь, чтобы alembic видел полный metadata.
"""

from atomic_tasks.infrastructure.postgres.tables.api_tokens import api_tokens
from atomic_tasks.infrastructure.postgres.tables.base import mapper_registry, metadata
from atomic_tasks.infrastructure.postgres.tables.users import user_identities, users

__all__ = ["api_tokens", "mapper_registry", "metadata", "user_identities", "users"]
