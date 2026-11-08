from collections.abc import AsyncIterator

from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from atomic_tasks.application.ports.api_tokens import ApiTokenRepository
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.ports.users import UserRepository
from atomic_tasks.application.services.auth_service import AuthService
from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.config.settings import PostgresSettings, Settings
from atomic_tasks.infrastructure.clock import SystemClock
from atomic_tasks.infrastructure.postgres.repositories.api_tokens import SqlApiTokenRepository
from atomic_tasks.infrastructure.postgres.repositories.transaction import SqlTransactionManager
from atomic_tasks.infrastructure.postgres.repositories.users import SqlUserRepository


class SettingsProvider(Provider):
    scope = Scope.APP

    settings = from_context(provides=Settings)

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

    users = provide(SqlUserRepository, scope=Scope.REQUEST, provides=UserRepository)
    api_tokens = provide(SqlApiTokenRepository, scope=Scope.REQUEST, provides=ApiTokenRepository)
    transaction = provide(
        SqlTransactionManager,
        scope=Scope.REQUEST,
        provides=TransactionManager,
    )


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    clock = provide(SystemClock, scope=Scope.APP, provides=Clock)
    user_service = provide(UserService)
    token_service = provide(TokenService)
    auth_service = provide(AuthService)
