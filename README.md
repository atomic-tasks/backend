# AtomicTasks — backend

Трекер задач, в котором агент раскладывает цели на атомарные задачи в дереве папок,
а вы смотрите, что делать дальше, через веб, Flutter-приложение или Telegram-бота.

Этот репозиторий — бэкенд: REST API (FastAPI) и MCP-сервер для агентов.

> Статус: ранняя стадия. Работают REST API и MCP-тулы для дерева папок и задач.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/docs
- MCP: http://localhost:8000/mcp

Локально без Docker для API:

```bash
uv sync
docker compose up -d postgres
uv run alembic upgrade head
uv run python -m atomic_tasks
```

## Токен и подключение Claude Code

Обычный путь: http://localhost:8000/docs → Authorize → вход через Rauthy (настройка — `docs/dev/rauthy.md`) →
`POST /api/v1/tokens`. Без IdP пользователя и токен можно создать командой:

```bash
docker compose exec api python -m atomic_tasks users create --name "Имя" --email you@example.com
docker compose exec api python -m atomic_tasks tokens create --user <id> --name "Claude Code"
claude mcp add -s user --transport http atomic-tasks http://localhost:8000/mcp \
  --header "Authorization: Bearer at_..."
```

Токен показывается один раз. Список и отзыв: `tokens list --user <id>`, `tokens revoke --user <id> <token_id>`.
Токен с `read` может только смотреть дерево; для создания и отметок нужен `write`.

Скилл декомпозиции — правила, по которым агент раскладывает цели на задачи. Установить для Claude Code:

```bash
mkdir -p ~/.claude/skills && cp -r skills/task-decomposition ~/.claude/skills/
```

Дальше в Claude Code: «разложи цель „подтянуть Go“» или «за что мне взяться?».

### MCP-тулы

| Тул | Что делает |
|---|---|
| `browse_folder` | Папка: путь, подпапки и задачи с приоритетом. Без id — корень |
| `list_next_tasks` | Задачи поддерева по приоритету — «что делать сейчас» |
| `get_item` | Папка или задача целиком, с описанием |
| `create_tree` | Вложенные папки и задачи одной пачкой, всё или ничего |
| `set_status` | Статусы списка папок и задач по порядку, всё или ничего |
| `update_item` | Название, описание, вес, перенос |
| `delete_item` | Удаление (непустой папки — с `recursive`) |

## Разработка

```bash
uvx pre-commit install   # один раз: ruff и gitleaks перед коммитом
uv run ruff format && uv run ruff check
uv run mypy
uv run lint-imports
uv run pytest
```

Документация: [`docs/`](docs/). Правила для AI-агентов: [`AGENTS.md`](AGENTS.md).

## Безопасность

Об уязвимостях — приватно, см. [`SECURITY.md`](SECURITY.md).

## Лицензия

[AGPL-3.0](LICENSE)
