from functools import cache


@cache
def map_entities() -> None:
    """Imperative-маппинг доменных сущностей на таблицы. Повторные вызовы ничего не делают.

    Сюда добавляется mapper_registry.map_imperatively(...) для каждой сущности.
    """
