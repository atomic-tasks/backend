from functools import cache

from atomic_tasks.domain.entities.api_token import ApiToken
from atomic_tasks.domain.entities.user import User, UserIdentity
from atomic_tasks.infrastructure.postgres.tables import (
    api_tokens,
    mapper_registry,
    user_identities,
    users,
)


@cache
def map_entities() -> None:
    """Imperative-маппинг доменных сущностей на таблицы. Повторные вызовы ничего не делают."""
    mapper_registry.map_imperatively(User, users)
    mapper_registry.map_imperatively(UserIdentity, user_identities)
    mapper_registry.map_imperatively(ApiToken, api_tokens)
