import uuid
from decimal import Decimal
from uuid import UUID

from atomic_tasks.application.dto import FolderInfo, Identity
from atomic_tasks.application.ports.access import AccessPolicy
from atomic_tasks.application.ports.clock import Clock
from atomic_tasks.application.ports.folders import FolderRepository
from atomic_tasks.application.ports.transaction import TransactionManager
from atomic_tasks.application.services.nodes import folder_info, readable, writable
from atomic_tasks.application.services.status_rules import apply_folder_status
from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.domain.entities.folder import Folder, FolderStatus
from atomic_tasks.domain.values import Weight

FOLDER = "Папка"
PARENT = "Родительская папка"


class FolderService:
    """Запись папок. Чтение деревьев — TreeService (спека 0003).

    Порядок в каждом изменяющем методе: права токена → доступ к каждому узлу → правило домена.
    Так доменная ошибка никогда не выдаст, что чужой объект существует.
    """

    def __init__(
        self,
        folders: FolderRepository,
        access: AccessPolicy,
        tx: TransactionManager,
        clock: Clock,
    ) -> None:
        self._folders = folders
        self._access = access
        self._tx = tx
        self._clock = clock

    async def get(self, identity: Identity, folder_id: UUID) -> FolderInfo:
        """Одна папка, если её можно читать."""
        folder = await readable(self._access, identity, await self._folders.get(folder_id), FOLDER)
        return folder_info(folder)

    async def get_root(self, identity: Identity) -> FolderInfo:
        """Корень текущего пользователя — точка входа в дерево для клиентов."""
        root = await self._folders.get_root(identity.user_id)
        return folder_info(await readable(self._access, identity, root, FOLDER))

    async def create(
        self,
        identity: Identity,
        *,
        parent_id: UUID,
        title: str,
        description: str | None = None,
        weight: Decimal | None = None,
    ) -> FolderInfo:
        """Создаёт папку в parent_id; без веса — 1.0."""
        identity.require_scope(TokenScope.WRITE)
        parent = await writable(self._access, identity, await self._folders.get(parent_id), PARENT)
        folder = Folder.create(
            id=uuid.uuid7(),
            parent=parent,
            title=title,
            description=description,
            weight=Weight(weight) if weight is not None else Weight.default(),
            now=self._clock.now(),
        )
        self._folders.add(folder)
        await self._tx.commit()
        return folder_info(folder)

    async def update(
        self,
        identity: Identity,
        folder_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        weight: Decimal | None = None,
    ) -> FolderInfo:
        """Меняет переданные поля. None — поле не меняется; пустое описание "" — очистить."""
        identity.require_scope(TokenScope.WRITE)
        folder = await self._writable(identity, folder_id)
        now = self._clock.now()
        if title is not None:
            folder.rename(title, now)
        if description is not None:
            folder.describe(description, now)
        if weight is not None:
            folder.set_weight(Weight(weight), now)
        await self._tx.commit()
        return folder_info(folder)

    async def move(self, identity: Identity, folder_id: UUID, *, new_parent_id: UUID) -> FolderInfo:
        """Переносит папку; цикл проверяется по пути от новой родительской папки к корню."""
        identity.require_scope(TokenScope.WRITE)
        folder = await self._writable(identity, folder_id)
        new_parent = await writable(
            self._access, identity, await self._folders.get(new_parent_id), PARENT
        )
        path = await self._folders.path_to_root(new_parent)
        folder.move_to(new_parent, {ref.id for ref in path}, self._clock.now())
        await self._tx.commit()
        return folder_info(folder)

    async def change_status(
        self,
        identity: Identity,
        folder_id: UUID,
        status: FolderStatus,
    ) -> FolderInfo:
        """Меняет статус папки; правила — в Folder.change_status."""
        identity.require_scope(TokenScope.WRITE)
        folder = await self._writable(identity, folder_id)
        await apply_folder_status(self._folders, folder, status, self._clock.now())
        await self._tx.commit()
        return folder_info(folder)

    async def delete(self, identity: Identity, folder_id: UUID, *, recursive: bool = False) -> None:
        """Удаляет папку физически; непустую — только с recursive, вместе с поддеревом."""
        identity.require_scope(TokenScope.WRITE)
        folder = await self._writable(identity, folder_id)
        folder.ensure_deletable(await self._folders.count_children(folder), recursive=recursive)
        await self._folders.delete(folder)
        await self._tx.commit()

    async def _writable(self, identity: Identity, folder_id: UUID) -> Folder:
        """Загружает папку и проверяет право её менять."""
        return await writable(self._access, identity, await self._folders.get(folder_id), FOLDER)
