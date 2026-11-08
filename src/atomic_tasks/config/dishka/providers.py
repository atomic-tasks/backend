from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from atomic_tasks.config.settings import PostgresSettings, Settings


class SettingsProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return Settings()

    @provide
    def postgres_settings(self, settings: Settings) -> PostgresSettings:
        return settings.postgres


class PostgresProvider(Provider):
    @provide(scope=Scope.APP)
    async def engine(self, settings: PostgresSettings) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(settings.dsn, echo=settings.echo, pool_pre_ping=True)
        yield engine
        await engine.dispose()

    @provide(scope=Scope.APP)
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    @provide(scope=Scope.REQUEST)
    async def session(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session


# Сюда по мере реализации добавляются провайдеры репозиториев, ридеров, сервисов
# и IdentityProvider (свой для FastAPI и для MCP).
