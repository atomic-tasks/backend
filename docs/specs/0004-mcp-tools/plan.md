# План

## Затронутые слои и файлы

- `application/ports/transaction.py` — `flush()` у `TransactionManager`.
- `application/services/status_rules.py` (новый) — смена статуса папки и задачи без commit: загрузка
  фактов (открытые потомки, `done`-предки) и вызов правила домена. Сейчас этот код живёт внутри
  `FolderService.change_status` и `TaskService.change_status` — выносится, чтобы не дублировать.
- `application/services/bulk_service.py` (новый) — `BulkService`: `create_tree`, `set_statuses`.
- `application/dto.py` — входные DTO: `NewFolder` (рекурсивный), `NewTask`, `StatusChange`; `NodeKind`.
- `application/errors.py` — `BulkItemError`: оборачивает ошибку элемента, добавляя его адрес.
- `infrastructure/postgres/repositories/transaction.py` — реализация `flush()`.
- `presentation/mcp/tools/` — `read.py` (`browse_folder`, `list_next_tasks`, `get_item`),
  `write.py` (`create_tree`, `set_status`, `update_item`, `delete_item`), `schemas.py` (pydantic-модели
  входа и компактных ответов), `runtime.py` (request-scope, ошибки → `isError`, компактный ответ).
- `presentation/mcp/server.py` — регистрация тулов, `instructions` дополняются ссылкой на тулы.
- `config/app.py`, `config/dishka/providers.py` — контейнер передаётся в регистрацию тулов, `BulkService`.
- `skills/task-decomposition/SKILL.md` — финальная версия.
- `README.md` — подключение Claude Code к `/mcp` по PAT и установка скилла.
- `docs/architecture.md`, `docs/roadmap.md` — раздел MCP, статус.

## Модель данных и миграции

Без изменений.

## Порты и сервисы

- `TransactionManager.flush()` — отправить накопленные изменения в базу без commit. Нужен пачкам: правило
  смены статуса папки считает открытых потомков SQL-запросом и должно видеть статусы, изменённые раньше
  в той же пачке (`autoflush=False` у сессии).
- `BulkService(folders, tasks, access, tx, clock)` — 5 зависимостей.
  - `create_tree(identity, parent_id, folders, tasks)`: scope `write` → `writable(parent)` → лимиты
    (100 узлов, 5 уровней) → обход в глубину, `Folder.create`/`Task.create` от сущности родителя (правило
    «только в `active`» проверяет домен) → один `commit`. Возвращает созданные узлы в порядке обхода.
  - `set_statuses(identity, changes)`: scope `write` → для каждого элемента по порядку: `writable` →
    `status_rules.apply_*` → `flush` → один `commit` в конце.
  - Ошибка элемента — `BulkItemError(address, cause)`; commit не вызывается, сессия закрывается
    с rollback при выходе из request-scope dishka.
- `FolderService.change_status`, `TaskService.change_status` переходят на `status_rules` — поведение REST
  не меняется.
- Одиночные `update_item`/`delete_item` вызывают существующие методы `FolderService`/`TaskService`;
  перенос в `update_item` — `move` после изменения полей, в одном вызове тула (две транзакции; если перенос
  не удался, переименование уже сохранено — ответ это говорит). Альтернатива — отдельный метод с одним
  commit; решим на реализации, если двухшаговость окажется заметной.

## FastAPI

Без изменений. `BulkService` в REST пока не выставляется — вне рамок.

## MCP-тулы

- Регистрация: `register_tools(server, container)`; каждый тул открывает request-scope
  `async with container() as rc` и берёт сервис из него — так у вызова своя сессия БД, как у HTTP-запроса.
- `Identity` — из `current_identity` (уже ставит `McpAuthMiddleware`).
- Вход и выход — pydantic-модели: SDK строит `inputSchema`/`outputSchema`. Приоритет — `float`,
  округлённый до 3 знаков, только на выходе; веса на входе — `Decimal`, валидирует домен.
- Ошибки: `ApplicationError`/`DomainError` → `ToolError` (результат с `isError`) с текстом сообщения.
  Прочие исключения — общий текст «Внутренняя ошибка», детали только в лог без данных пользователя.
- Описания тулов — в докстрингах, по-русски, 2–5 строк: когда звать, что вернёт, частая ошибка.

## Риски

- ~~**ContextVar и stateless-транспорт.**~~ Не подтвердился: `Identity` из middleware доходит до тула
  (e2e-тесты идут через настоящий HTTP-стек).
- ~~**Порядок вставок в `create_tree`.**~~ Не подтвердился: unit of work вставляет строки одной таблицы
  в порядке `add`, а родитель добавляется раньше детей. Проверено integration-тестом без `flush`.
- **Правило «закрыть папку» в пачке** видит только сброшенные изменения — отсюда `flush` после элемента.
  Без интеграционного теста легко сломать незаметно.
- **Контекст агента.** Ответы — компактные, но UUID длинные. Меряем на живом дереве (открытый вопрос спеки).
