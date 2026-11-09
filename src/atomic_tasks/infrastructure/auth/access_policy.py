from atomic_tasks.application.dto import Identity
from atomic_tasks.domain.entities.folder import Folder
from atomic_tasks.domain.entities.task import Task


class OwnerAccessPolicy:
    """Пока шаринга нет: читать и менять узел может только его владелец."""

    async def can_read(self, identity: Identity, node: Folder | Task) -> bool:
        """Читать может только владелец."""
        return node.owner_id == identity.user_id

    async def can_write(self, identity: Identity, node: Folder | Task) -> bool:
        """Менять может только владелец."""
        return node.owner_id == identity.user_id
