from typing import Protocol

from atomic_tasks.application.dto import Identity
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.task import Task


class AccessPolicy(Protocol):
    """Единственное место, где решается доступ к узлу дерева (ADR 0005).

    Права токена (read/write) — отдельная проверка: Identity.require_scope.
    Методы асинхронные и получают узел целиком: реализации с шарингом понадобится
    сходить в базу и посмотреть, в какой папке лежит узел.
    """

    async def can_read(self, identity: Identity, node: Folder | Task) -> bool:
        """Может ли пользователь видеть узел."""
        ...

    async def can_write(self, identity: Identity, node: Folder | Task) -> bool:
        """Может ли пользователь менять узел и класть что-то внутрь папки."""
        ...
