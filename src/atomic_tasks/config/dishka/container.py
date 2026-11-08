from dishka import AsyncContainer, make_async_container

from atomic_tasks.config.dishka.providers import PostgresProvider, SettingsProvider


def create_container() -> AsyncContainer:
    return make_async_container(
        SettingsProvider(),
        PostgresProvider(),
    )
