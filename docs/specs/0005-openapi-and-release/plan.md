# План

## Затронутые слои и файлы

- `config/openapi.py` — `export_openapi() -> str`: собирает приложение через `create_app` с настройками
  по умолчанию (`Settings.model_construct()` — без `.env` и env) и сериализует `app.openapi()`:
  `indent=2`, `ensure_ascii=False`, перевод строки в конце. Через `create_app`, а не только FastAPI-часть, —
  чтобы схема совпадала с той, что отдаёт сервер. Контейнер dishka создаётся, но к БД ничего не подключается.
- `config/cli.py` — команда `openapi [--output PATH]` (по умолчанию stdout) разбирается до создания
  контейнера: ей не нужны БД и настройки.
- `openapi.json` в корне — сгенерированный файл.
- `pyproject.toml` — `version = "0.0.0"`; `uv.lock` обновить.
- `Dockerfile` — `ARG VERSION=0.0.0`, перед установкой проекта `uv version --frozen "$VERSION"`.
  Слой зависимостей от версии не зависит и продолжает кэшироваться.
- `.github/workflows/ci.yml`:
  - в `checks` — экспорт и `git diff --exit-code openapi.json` с понятным сообщением;
  - новая джоба `api-breaking` (только `pull_request`): базовая схема из `origin/$GITHUB_BASE_REF`,
    `oasdiff breaking` (образ `tufin/oasdiff`, версия закреплена) с `--format githubactions` — аннотации,
    и текстовый отчёт в `$GITHUB_STEP_SUMMARY`. Без `--fail-on`, поэтому не валит. Если в базе файла
    ещё нет — пропуск.
- `.github/workflows/release.yml` — по тегу `v*.*.*`:
  1. проверка формата тега и что коммит входит в `origin/main`;
  2. `docker/metadata-action` → теги `X.Y.Z`, `X.Y`, `latest` и OCI-лейблы (связывают пакет с репозиторием);
  3. `docker/login-action` в ghcr с `GITHUB_TOKEN`, `docker/build-push-action` с `VERSION`, `linux/amd64`;
  4. `docker run <образ> python -m atomic_tasks openapi > openapi.json`, сверка с закоммиченной без `info.version`;
  5. `gh release create --verify-tag --generate-notes` с `openapi.json`.
- Документация: ADR 0010, `docs/architecture.md` (раздел «Релизы»), `README.md`, `docs/roadmap.md`.

## Модель данных и миграции

Нет.

## Порты и сервисы

Нет.

## FastAPI

Без изменений эндпоинтов. `/openapi.json` сервера и экспорт — одна и та же схема.

## MCP-тулы

Нет.

## Риски

- `Settings.model_construct()` пропускает валидацию — допустимо, потому что берутся только значения
  по умолчанию, которые и так валидны. Альтернатива (`_env_file=None`) всё равно читает переменные окружения.
- `uv version --frozen` в Dockerfile не трогает `uv.lock`: в lock корневой пакет остаётся `0.0.0`,
  версия установленного пакета — из `pyproject.toml`. Проверить сборкой с `--build-arg`.
- Тег пушится вручную: ошибиться с номером можно, но релиз всё равно требует коммита из `main`.
