import asyncio
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import String
from sqlalchemy.ext.asyncio import create_async_engine

from atomic_tasks.config.settings import Settings
from atomic_tasks.infrastructure.postgres.tables import metadata
from atomic_tasks.infrastructure.postgres.tables.base import StrEnumType

target_metadata = metadata


def _dsn() -> str:
    # Тесты передают DSN через sqlalchemy.url; в остальных случаях — настройки приложения.
    return context.config.get_main_option("sqlalchemy.url") or Settings().postgres.dsn


def _render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    # Миграции не зависят от типов приложения: енам пишется как обычная строка (ADR 0004).
    if type_ == "type" and isinstance(obj, StrEnumType):
        return repr(String(length=obj.length)).replace("String", "sa.String")
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_dsn(),
        target_metadata=target_metadata,
        render_item=_render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_dsn())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
