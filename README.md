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
