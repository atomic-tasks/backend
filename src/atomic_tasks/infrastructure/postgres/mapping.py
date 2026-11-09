from functools import cache

from sqlalchemy.orm import relationship

from atomic_tasks.domain.entities.api_token import ApiToken
from atomic_tasks.domain.entities.user import User, UserIdentity
from atomic_tasks.infrastructure.postgres.tables import (
    api_tokens,
    mapper_registry,
    user_identities,
    users,
)


def _depends_on(target: type) -> object:
    """Связь только для порядка INSERT в unit of work, не для чтения.

    Без relationship SQLAlchemy не знает, что пользователь вставляется раньше его токенов,
    и порядок INSERT в одном flush случайный. lazy="raise" — чтобы никто не начал
    ходить по связи и не получил скрытых запросов. Домен об этих атрибутах не знает.
    """
    return relationship(target, lazy="raise")


@cache
def map_entities() -> None:
    """Imperative-маппинг доменных сущностей на таблицы. Повторные вызовы ничего не делают."""
    mapper_registry.map_imperatively(User, users)
    mapper_registry.map_imperatively(
        UserIdentity,
        user_identities,
        properties={"_user": _depends_on(User)},
    )
    mapper_registry.map_imperatively(
        ApiToken,
        api_tokens,
        properties={"_user": _depends_on(User)},
    )
