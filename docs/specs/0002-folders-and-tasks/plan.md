# План

## Затронутые слои и файлы

**domain**
- `values.py` — `Weight` (frozen, 0.5–2.0, `Weight.default()` = 1.0).
- `entities/folder.py` — `FolderStatus` (`is_open`), `Folder`: `is_root`, `ensure_accepts_children()`,
  `rename/describe/set_weight` (запрещены для корня), `move_to(parent, parent_path)` — проверка цикла,
  `change_status(new, *, open_descendants, has_done_ancestor)`, `ensure_deletable(children_count, recursive)`.
  Фабрика `Folder.new_root(owner_id, now)`.
- `entities/task.py` — `TaskStatus`, `Task`: `rename/describe/set_weight`, `move_to(folder)`,
  `change_status(new, *, has_done_ancestor)`.
- `values.py` также — `ItemCount(folders, tasks)`, нормализация названия и описания.
- `exceptions.py` — `InvalidFieldError`, `RootFolderProtectedError`, `FolderCycleError`, `FolderNotActiveError`,
  `FolderHasOpenItemsError`, `FolderNotEmptyError`, `DoneAncestorError`.

Решение «можно ли» формулирует сущность; данные для него (потомки, предки) собирает сервис через порты.

**application**
- `ports/folders.py` — `FolderRepository`:
  `add`, `get(id)`, `get_root(owner_id)`, `delete(folder)`,
  `path_to_root(folder) -> list[FolderRef(id, status)]` — сама папка и предки (рекурсивный CTE вверх),
  `count_open_descendants(folder) -> ItemCount` (CTE вниз), `count_children(folder) -> ItemCount`.
  Методы принимают папку, а не id: CTE фильтруются по её `owner_id`.
- `ports/tasks.py` — `TaskRepository`: `add`, `get(id)`, `delete(task)`.
- `ports/access.py` — `AccessPolicy`: `async can_read(identity, node)`, `async can_write(identity, node)`;
  узел целиком, чтобы будущая реализация с шарингом могла смотреть на папку.
- `services/nodes.py` — общие шаги: `readable`/`writable` (нет доступа → `NotFoundError`), DTO.
- `services/folder_service.py` — `FolderService`: `get`, `get_root`, `create`, `update`, `move`,
  `change_status`, `delete`.
  Зависимости: `FolderRepository`, `AccessPolicy`, `TransactionManager`, `Clock`.
- `services/task_service.py` — `TaskService`: `get`, `create`, `update`, `move`, `change_status`, `delete`.
  Зависимости: `TaskRepository`, `FolderRepository`, `AccessPolicy`, `TransactionManager`, `Clock`.
- `services/user_service.py`, `services/identity_service.py` — при создании пользователя добавить корень
  (`FolderRepository.add(Folder.new_root(...))`) в той же транзакции.
- `dto.py` — `FolderInfo`, `TaskInfo`. Сервисы возвращают DTO, не сущности.

Общий шаг сервисов: загрузить объект → `AccessPolicy` → нет доступа или нет объекта → `NotFoundError`;
изменение → `identity.require_scope(WRITE)` до любой работы.

**infrastructure**
- `postgres/tables/folders.py`, `postgres/tables/tasks.py`; `WeightType` (`TypeDecorator` над `Numeric(3, 2)`)
  в `tables/base.py`.
- `postgres/mapping.py` — маппинг `Folder`, `Task` и служебные `relationship(lazy="raise")` к `User`/`Folder`:
  без них unit of work вставляет строки одного flush в случайном порядке (корень раньше пользователя).
- `postgres/repositories/folders.py`, `postgres/repositories/tasks.py` — CTE через `text()` с bind-параметрами;
  `UNION` вместо `UNION ALL`, чтобы рекурсия завершалась и на цикле.
- `postgres/migrations/versions/0002_folders_and_tasks.py` — таблицы + корни существующим пользователям.
- `auth/access_policy.py` — `OwnerAccessPolicy`.

**config**
- `dishka/providers.py` — репозитории, `AccessPolicy`, `FolderService`, `TaskService`.

## Модель данных и миграции

```
folders
  id           uuid PK                      -- uuid7
  owner_id     uuid FK → users ON DELETE CASCADE
  parent_id    uuid NULL FK → folders ON DELETE CASCADE   -- NULL только у корня
  title        varchar(200)
  description  text NULL
  weight       numeric(3,2)                 -- 0.50–2.00
  status       varchar(16)                  -- строка без CHECK (ADR 0004)
  created_at, updated_at  timestamptz
  INDEX (owner_id, parent_id)
  UNIQUE (owner_id) WHERE parent_id IS NULL -- один корень

tasks
  id           uuid PK
  owner_id     uuid FK → users ON DELETE CASCADE
  folder_id    uuid FK → folders ON DELETE CASCADE
  title        varchar(200)
  description  text NULL
  weight       numeric(3,2)
  status       varchar(16)
  created_at, updated_at  timestamptz
  INDEX (owner_id, folder_id)
```

`ON DELETE CASCADE` на `parent_id` и `folder_id` реализует `recursive`-удаление одним `DELETE`;
нерекурсивное удаление сначала проверяет `count_children`.

Миграция: создание таблиц, затем `INSERT INTO folders ... SELECT ... FROM users` — корень каждому
(id — встроенный `uuidv7()` Postgres 18, версия та же в compose и testcontainers).
`downgrade` — удаление таблиц.

## Порты и сервисы

- `FolderService.create(identity, *, parent_id, title, description, weight) -> FolderInfo`
- `FolderService.update(identity, folder_id, *, title?, description?, weight?) -> FolderInfo`
- `FolderService.move(identity, folder_id, *, new_parent_id) -> FolderInfo` — цикл: папка есть
  в `path_to_root(new_parent)`.
- `FolderService.change_status(identity, folder_id, status) -> FolderInfo` — всегда считает и
  `count_open_descendants`, и `path_to_root(parent)`; какой факт важен для статуса, решает домен.
- `FolderService.delete(identity, folder_id, *, recursive=False) -> None`
- `TaskService` — те же операции для задач; папка-цель проверяется через `AccessPolicy` и `ensure_accepts_children`.

## FastAPI

Нет в этой спеке.

## MCP-тулы

Нет в этой спеке.

## Риски

- Гонки: два параллельных запроса могут нарушить «нет открытого под `done`» (один закрывает папку,
  другой открывает задачу внутри). При личных объёмах приемлемо; если станет проблемой — `SELECT ... FOR UPDATE`
  на папке или уровень изоляции `SERIALIZABLE` для смены статусов.
- Перенос папки при параллельном переносе другой может создать цикл в обход проверки — тот же риск
  и то же лечение. Ридер дерева (0003) всё равно должен защищаться от циклов.
- `Numeric` ↔ `float`: вес хранится как `Decimal`, чтобы 1.10 не превращался в 1.1000000001.
