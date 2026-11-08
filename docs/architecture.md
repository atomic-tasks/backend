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
| `application` | `FolderService`, `TaskService`, `TreeService`; порты | domain |
| `infrastructure` | `postgres/` (таблицы, репозитории, CTE-ридеры, миграции), `auth/` (JWT, PAT) | application, domain |
| `presentation` | `fastapi/` (роутеры, схемы), `mcp/` (тулы) | application, domain |
| `config` | настройки, провайдеры dishka, сборка приложения | всё |

Границы проверяет `lint-imports` в CI.

## Порты (application/ports)

- `FolderRepository`, `TaskRepository` — запись агрегатов.
- `FolderTreeReader` — чтение деревьев (рекурсивные CTE), отдаёт DTO, минуя сущности.
- `TransactionManager` — commit/rollback, вызывается сервисом.
- `IdentityProvider` — текущий пользователь; своя реализация для FastAPI и для MCP.
- `AccessPolicy` — может ли пользователь читать/менять узел. Сейчас «владелец == пользователь».

## Модель данных

- `users`
- `folders(id, owner_id, parent_id, title, description, weight, status, created_at, updated_at)`
- `tasks(id, owner_id, folder_id, title, description, weight, status, created_at, updated_at)`
- `api_tokens(id, owner_id, token_hash, name, scopes, created_at, last_used_at, revoked_at)`

Статусы папок: `active`, `paused`, `done`, `cancelled`.
Статусы задач: `todo`, `in_progress`, `paused`, `done`, `cancelled`.

## Чтение дерева

- Режим «проводник»: дочерние папки и задачи одной папки — два запроса по индексу, без рекурсии.
- Режим «всё вложенное»: рекурсивный CTE от выбранной папки, приоритет = произведение весов по пути,
  неактивные папки отсекаются внутри рекурсии.

## Авторизация

1. Personal access tokens — Claude Code (HTTP MCP с `Authorization: Bearer`), бот, скрипты.
2. Внешний IdP (OAuth 2.1) — веб, Flutter, MCP-коннектор в приложении Claude. API — resource server.

## Клиенты

Отдельные репозитории в организации `atomic-tasks`: `web`, `mobile` (Flutter), `telegram-bot`.
Источник правды — `openapi.json` бэкенда (стабильные `operation_id`), клиенты генерируют SDK у себя.
