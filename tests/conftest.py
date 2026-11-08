import asyncio
import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from atomic_tasks.config.settings import PostgresSettings, Settings
from atomic_tasks.infrastructure.postgres.mapping import map_entities

map_entities()


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Postgres для тестов: TEST_POSTGRES_DSN, иначе контейнер (testcontainers, нужен Docker)."""
    if dsn := os.environ.get("TEST_POSTGRES_DSN"):
        yield dsn
        return
    from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(postgres_dsn: str) -> Settings:
    """Тестовая база; схема накатывается настоящими миграциями — заодно проверяем их."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_dsn)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    url = make_url(postgres_dsn)
    return Settings(
        postgres=PostgresSettings(
            host=url.host or "localhost",
            port=url.port or 5432,
            user=url.username or "",
            password=url.password or "",
            db=url.database or "",
        ),
    )


@pytest.fixture
def empty_db(settings: Settings) -> Settings:
    """Пустые таблицы перед тестом. Работает и в синхронных тестах: своё событийное кольцо."""

    async def truncate() -> None:
        engine = create_async_engine(settings.postgres.dsn)
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
        await engine.dispose()

    asyncio.run(truncate())
    return settings


@pytest.fixture(scope="session")
def settings_with_allowlist(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "auth": settings.auth.model_copy(
                update={"allowed_emails": ["alice@example.com", "bob@example.com"]},
            ),
        },
    )
