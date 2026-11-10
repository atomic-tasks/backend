# План

## Затронутые слои и файлы

**domain** — без изменений. Новых правил нет: что считается открытым, берётся из `FolderStatus.is_open`
и `TaskStatus.is_open`.

**application**
- `dto.py` — новые DTO чтения:
  - `FolderCrumb(id, title, weight, status)` — элемент пути;
  - `FolderListing(folder: FolderInfo, path: list[FolderCrumb], active_branch: bool,
    folders: list[RankedFolder], tasks: list[RankedTask])` — ответ проводника;
  - `RankedFolder(info: FolderInfo, priority)`, `RankedTask(info: TaskInfo, priority)`;
  - `NestedTask(info: TaskInfo, priority, path: list[FolderCrumb])` — элемент «всего вложенного».
- `ports/tree.py` — `FolderTreeReader` (имя из `docs/architecture.md`), отдаёт DTO, минуя сущности:
  - `ancestors(folder) -> list[FolderCrumb]` — от корня до папки включительно, по порядку;
  - `children(folder, *, include_closed) -> tuple[list[FolderInfo], list[TaskInfo]]` — отсортированы;
  - `nested_tasks(folder, *, statuses, limit) -> list[NestedTask]` — рекурсивный CTE.
  Методы принимают папку (как `FolderRepository`): нужен её `owner_id`.
- `services/tree_service.py` — `TreeService`: `browse(identity, folder_id, *, include_closed)`,
  `nested_tasks(identity, folder_id, *, statuses, limit)`.
  Зависимости: `FolderRepository` (загрузить папку для `AccessPolicy`), `FolderTreeReader`, `AccessPolicy`.
  Приоритет в проводнике: множитель = произведение весов `ancestors`; элементу — множитель × свой вес.
  `limit` проверяется в сервисе (1–500), не в роутере.

**infrastructure**
- `postgres/readers/tree.py` — `SqlFolderTreeReader`. SQL через `text()` с bind-параметрами,
  открытые статусы — массивом из домена (как в `repositories/folders.py`).
  - `ancestors`: CTE вверх с `depth`, `ORDER BY depth DESC`.
  - `children`: два `SELECT` по индексам, сортировка в SQL.
  - `nested_tasks`: CTE вниз, в рекурсии несём `priority` (`numeric`) и массивы `path_ids`/`path_titles`;
    спускаемся только в `status = 'active'`; защита от цикла — `NOT f.id = ANY(path_ids)`
    (`UNION` здесь не поможет: строки с разными путями различаются). Затем `JOIN tasks`,
    `status = ANY(:statuses)`, `ORDER BY`, `LIMIT`.
  - Порядок при равном приоритете: `in_progress` раньше `todo` (начатое — доделать), затем
    `created_at`, затем `id` — детерминированно.

**presentation/fastapi**
- `schemas/tree.py` — pydantic-ответы и запросы. `weight` и `priority` — JSON-числа;
  на входе `weight: Decimal | None` без границ (их проверяет `Weight`).
- `routers/folders.py`, `routers/tasks.py` — тонкие обёртки над сервисами.
- `errors.py` — ошибки состояния дерева → 409, `InvalidFieldError` → 422.
- `app.py` — подключить роутеры.

**config**
- `dishka/providers.py` — `SqlFolderTreeReader` как `FolderTreeReader`, `TreeService`.

## Модель данных и миграции

Без миграций. Нужные индексы `(owner_id, parent_id)` и `(owner_id, folder_id)` созданы в 0002.

## Порты и сервисы

```python
class FolderTreeReader(Protocol):
    async def ancestors(self, folder: Folder) -> list[FolderCrumb]: ...
    async def children(self, folder: Folder, *, include_closed: bool
                       ) -> tuple[list[FolderInfo], list[TaskInfo]]: ...
    async def nested_tasks(self, folder: Folder, *, statuses: Collection[TaskStatus], limit: int
                           ) -> list[NestedTask]: ...

class TreeService:
    async def browse(self, identity, folder_id, *, include_closed=False) -> FolderListing
    async def nested_tasks(self, identity, folder_id, *, statuses=None, limit=50) -> list[NestedTask]
```

`browse` и `nested_tasks` требуют scope `read`; доступ — `readable(...)` из `services/nodes.py`.

## FastAPI

Всё под `/api/v1`. `operation_id` = имя функции.

| Метод | Путь | operation_id | Сервис |
|---|---|---|---|
| GET | `/folders/root` | `get_root_folder` | `FolderService.get_root` |
| GET | `/folders/{folder_id}` | `get_folder` | `FolderService.get` |
| GET | `/folders/{folder_id}/children?include_closed=` | `browse_folder` | `TreeService.browse` |
| GET | `/folders/{folder_id}/nested-tasks?status=&limit=` | `list_nested_tasks` | `TreeService.nested_tasks` |
| POST | `/folders` | `create_folder` | `FolderService.create` |
| PATCH | `/folders/{folder_id}` | `update_folder` | `FolderService.update` |
| POST | `/folders/{folder_id}/move` | `move_folder` | `FolderService.move` |
| POST | `/folders/{folder_id}/status` | `change_folder_status` | `FolderService.change_status` |
| DELETE | `/folders/{folder_id}?recursive=` | `delete_folder` | `FolderService.delete` |
| GET | `/tasks/{task_id}` | `get_task` | `TaskService.get` |
| POST | `/tasks` | `create_task` | `TaskService.create` |
| PATCH | `/tasks/{task_id}` | `update_task` | `TaskService.update` |
| POST | `/tasks/{task_id}/move` | `move_task` | `TaskService.move` |
| POST | `/tasks/{task_id}/status` | `change_task_status` | `TaskService.change_status` |
| DELETE | `/tasks/{task_id}` | `delete_task` | `TaskService.delete` |

Перенос и статус — отдельные действия, а не поля `PATCH`: у них свои правила и ошибки домена, и
один вызов = один метод сервиса.

## MCP-тулы

Нет в этой спеке (0004).

## Риски

- `numeric` × `numeric` по глубокой ветке растит число знаков; при личной глубине (< 20) безопасно.
  Наружу отдаём `float` — для отображения точности хватает.
- Время `nested_tasks` (порог ADR 0002 — 50 мс). Замер на случайном дереве из 611 папок
  (3 уровня, ~14% `paused`), сервис целиком на локальном Postgres 18:

  | Задач | limit=50 (медиана / p95) | limit=500 | SQL, `EXPLAIN ANALYZE` | проводник корня |
  |---|---|---|---|---|
  | 6 110 | 5.8 / 6.8 мс | 11.5 мс | 4.0 мс | 1.7 мс |
  | 30 550 | 15.3 / 16.9 мс | 20.2 мс | 14.5 мс | 1.9 мс |

  Запас большой — кэш приоритета не нужен. Время растёт с числом задач в активном поддереве:
  CTE собирает и сортирует их все до `LIMIT`.
- Pydantic по умолчанию сериализует `Decimal` строкой — в схемах явно `float`.
