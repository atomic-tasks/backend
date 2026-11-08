from dishka import AsyncContainer, Provider, make_async_container

from atomic_tasks.config.dishka.providers import (
    AuthProvider,
    PostgresProvider,
    ServicesProvider,
    SettingsProvider,
)
from atomic_tasks.config.settings import Settings


def create_container(settings: Settings, *overrides: Provider) -> AsyncContainer:
    return make_async_container(
        SettingsProvider(),
        PostgresProvider(),
        ServicesProvider(),
        AuthProvider(),
        *overrides,
        context={Settings: settings},
    )
