# Задачи

- [x] ADR 0010 «версия из git-тега» — принят, ссылка из спеки
- [x] `config/openapi.py` + команда `openapi` в `config/cli.py` — `python -m atomic_tasks openapi` печатает
  схему без `.env` и без Postgres; с `AUTH__ISSUER=...` вывод не меняется
- [x] `openapi.json` в корне сгенерирован и закоммичен
- [x] `pyproject.toml` → `0.0.0`, `uv.lock` обновлён; Dockerfile принимает `VERSION` — образ, собранный
  с `--build-arg VERSION=1.2.3`, отдаёт `info.version == "1.2.3"`
- [x] CI: проверка свежести `openapi.json` и джоба `api-breaking` (предупреждения, без падения)
- [x] `release.yml` по тегу `vX.Y.Z`: проверка тега и `main`, образ в ghcr, GitHub Release с `openapi.json`
- [x] README (как выпустить релиз, как обновить схему), `architecture.md`, roadmap — 0005 реализована
- [x] ruff, mypy, lint-imports, pytest — чистые
