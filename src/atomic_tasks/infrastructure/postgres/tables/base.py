from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Dialect, MetaData, String, TypeDecorator
from sqlalchemy.orm import registry

# Единые имена constraint'ов, чтобы alembic autogenerate давал стабильные миграции.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
mapper_registry = registry(metadata=metadata)

TIMESTAMPTZ = DateTime(timezone=True)


class StrEnumType[E: StrEnum](TypeDecorator[E]):
    """Енам как обычная строка без CHECK-constraint (ADR 0004); значения валидирует домен."""

    impl = String
    cache_ok = True

    def __init__(self, enum: type[E], length: int = 32) -> None:
        super().__init__(length)
        self.length = length
        self._enum = enum

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else str(self._enum(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> E | None:
        return None if value is None else self._enum(value)
