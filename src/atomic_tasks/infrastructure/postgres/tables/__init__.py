"""Описания таблиц.

Каждый модуль с таблицами импортируется здесь, чтобы alembic видел полный metadata.
"""

from atomic_tasks.infrastructure.postgres.tables.base import mapper_registry, metadata

__all__ = ["mapper_registry", "metadata"]
