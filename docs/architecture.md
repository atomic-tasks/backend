# Architecture

## Обзор

```
Агент + скилл     Telegram-бот     Веб / Flutter
      │                 │                │
      ▼                 └───────┬────────┘
  MCP (/mcp)                REST API
      │                         │
      └──────────┬──────────────┘
                 ▼
     application: сервисы и порты
                 ▼
          domain: сущности
                 ▲
 infrastructure: postgres, auth (реализует порты)
```

Одно ASGI-приложение: FastAPI с примонтированным MCP (Streamable HTTP, stateless).
Сборка — `config/app.py`, зависимости — dishka (`config/dishka/`).

## Слои

| Слой | Содержит | Зависит от |
|---|---|---|
| `domain` | сущности `User`, `Folder`, `Task`; `Weight`, статусы, инварианты | ничего (stdlib) |
| `application` | `FolderService`, `TaskService`, `TreeService`, `BulkService`; порты | domain |
| `infrastructure` | `postgres/` (таблицы, репозитории, CTE-ридеры, миграции), `auth/` (JWT, PAT) | application, domain |
| `presentation` | `fastapi/` (роутеры, схемы), `mcp/` (тулы) | application, domain |
| `config` | настройки, провайдеры dishka, сборка приложения | всё |

Границы проверяет `lint-imports` в CI.

## Порты (application/ports)

- `FolderRepository`, `TaskRepository` — запись агрегатов.
- `FolderTreeReader` — чтение деревьев (рекурсивные CTE), отдаёт DTO, минуя сущности.
- `TransactionManager` — `commit` и `flush`, вызывается сервисом; отката нет — незакоммиченное
  откатывается при закрытии request-scope.
- `IdentityProvider` — текущий пользователь; своя реализация для FastAPI и для MCP.
- `AccessPolicy` — может ли пользователь читать/менять узел. Сейчас «владелец == пользователь»
  (`OwnerAccessPolicy`). Нет доступа — «не найден», как и для несуществующего id.

## Модель данных

- `users`, `user_identities(user_id, issuer, subject)`, `api_tokens(user_id, prefix, token_hash, scope, ...)` —
  реализованы в спеке 0001
- `folders(id, owner_id, parent_id, title, description, weight, status, created_at, updated_at)` — спека 0002
- `tasks(id, owner_id, folder_id, title, description, weight, status, created_at, updated_at)` — спека 0002

Статусы папок: `active`, `paused`, `done`, `cancelled`.
Статусы задач: `todo`, `in_progress`, `paused`, `done`, `cancelled`.

- У каждого пользователя одна корневая папка (`parent_id IS NULL`, частичный уникальный индекс),
  создаётся вместе с пользователем; её нельзя удалить, перенести, переименовать или закрыть.
  Задача всегда в папке.
- `paused`/`cancelled` у папки ставятся всегда и прячут ветку; `done` — только когда в поддереве
  нет открытого. Под `done` открытого не бывает. Создавать и переносить можно только в `active`.
- Удаление физическое; непустая папка — только с `recursive`, поддерево уходит по `ON DELETE CASCADE`.

Спека: `docs/specs/0002-folders-and-tasks/`.

## Чтение дерева

`TreeService` + порт `FolderTreeReader` (`infrastructure/postgres/readers/tree.py`).

- Режим «проводник»: дочерние папки и задачи одной папки — два запроса по индексу, без рекурсии.
  Абсолютный приоритет — множитель предков (подъём к корню) × вес элемента; `active_branch` — вся
  цепочка в `active`. Закрытые скрыты без `include_closed`.
- Режим «всё вложенное»: рекурсивный CTE от выбранной папки, плоский список задач,
  приоритет = произведение весов по пути (вес выбранной папки не входит), неактивные подпапки
  отсекаются внутри рекурсии, выбранная обходится всегда. По умолчанию `todo` и `in_progress`, `limit` ≤ 500.
- Циклы в данных не зацикливают чтение: `CYCLE` вверх, проверка по пути вниз.

## REST

`/api/v1/folders`, `/api/v1/tasks` — тонкие роутеры над `FolderService`, `TaskService`, `TreeService`.
Перенос и статус — отдельные `POST .../move` и `POST .../status`. Ошибки — problem details:
состояние дерева → 409, неверное поле → 422, нет прав токена → 403, чужое или нет — 404.

Спека: `docs/specs/0003-tree-reading-and-rest/`.

## MCP

`presentation/mcp/`: `MCPServer` из SDK `mcp`, Streamable HTTP, stateless, на `/mcp` (ADR 0006).
`McpAuthMiddleware` аутентифицирует запрос тем же `AuthService` и кладёт `Identity` в ContextVar;
тул открывает свой request-scope dishka (`ToolRuntime.call`) и вызывает те же сервисы, что REST.

- Тулы: `browse_folder`, `list_next_tasks`, `get_item` (чтение), `create_tree`, `set_status`, `update_item`,
  `delete_item` (запись). Тип узла агент передаёт явно: `kind: folder | task`.
- Пачки — `BulkService`: один commit в конце, при ошибке — откат и адрес элемента (`folders[1].tasks[0]`,
  `changes[2]`). `set_status` делает `flush` после каждого элемента: правило закрытия папки считает
  открытых потомков SQL-запросом и должно видеть предыдущие изменения пачки.
- Смена статуса без commit — `application/services/status_rules.py`, общая для одиночных сервисов и пачек.
- Ответы компактные: JSON без отступов в тексте и тот же JSON в `structuredContent`; описания — только в `get_item`.
- Ошибки сервисов и домена → результат тула с `isError` и текстом; прочие исключения SDK скрывает.
- Скилл декомпозиции для агента — `skills/task-decomposition/SKILL.md`.

Спека: `docs/specs/0004-mcp-tools/`.

## Авторизация

IdP — Rauthy в том же compose (ADR 0009). Бэкенд только проверяет токены.

- **JWT от Rauthy** — web, mobile, Swagger `/docs`. Пользователь — по `(issuer, sub)`, создаётся при первом входе
  (если email в allowlist).
- **Personal access tokens** `at_...` — Claude Code (HTTP MCP с `Authorization: Bearer`), бот, скрипты.
- **OAuth для коннектора в приложении Claude** — отдельной спекой: DCR в Rauthy + protected resource metadata на `/mcp`.

Спека: `docs/specs/0001-users-and-auth/`.

## Клиенты

Отдельные репозитории в организации `atomic-tasks`: `web`, `mobile` (Flutter), `telegram-bot`.
Источник правды — `openapi.json` бэкенда (стабильные `operation_id`), клиенты генерируют SDK у себя.
