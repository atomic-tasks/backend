# AtomicTasks — backend

Трекер задач, в котором агент раскладывает цели на атомарные задачи в дереве папок,
а вы смотрите, что делать дальше, через веб, Flutter-приложение или Telegram-бота.

Этот репозиторий — бэкенд: REST API (FastAPI) и MCP-сервер для агентов.

> Статус: ранняя стадия, функционала пока нет.

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

Пока вход через Rauthy не подключён, пользователи и токены создаются командой:

```bash
docker compose exec api python -m atomic_tasks users create --name "Имя" --email you@example.com
docker compose exec api python -m atomic_tasks tokens create --user <id> --name "Claude Code"
claude mcp add --transport http atomic-tasks http://localhost:8000/mcp \
  --header "Authorization: Bearer at_..."
```

Токен показывается один раз. Список и отзыв: `tokens list --user <id>`, `tokens revoke --user <id> <token_id>`.

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
