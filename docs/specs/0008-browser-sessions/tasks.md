# Задачи

**PR 1 — спека и хосты** (отдельный релиз)

- [x] Роутер `atomic-web-api` (`Host(WEB_HOST) && PathPrefix(/api/)`) в `deploy/compose.yaml`, `WEB_HOST`
      и новый пример `API_HOST` в `deploy/.env.example` — `docker compose -f deploy/compose.yaml config`
      с тестовым `.env` проходит, оба правила в выводе верные; без `WEB_HOST` — ошибка
- [x] Runbook переезда в `docs/deploy.md` (DNS, `.env`, Rauthy, GitHub, проверка, коннекторы, откат),
      хосты в `docs/architecture.md` — каждый шаг проверяем командой или ссылкой на экран админки
- [x] PR 1: спека, ADR 0013, roadmap, plan.md, tasks.md, compose и runbook; после мёржа — переезд по runbook,
      тег и выкатка — на `API_HOST` отвечают `/health`, `/docs` (вход в Swagger работает), `/openapi.json`,
      `/.well-known/oauth-protected-resource/mcp`; коннектор Claude на новом `/mcp` видит дерево;
      `https://WEB_HOST/api/v1/me` → 401, `https://WEB_HOST/` → 404 от Traefik; релизный job зелёный

**PR 2 — вход через браузер**

- [x] Домен: `BrowserSession`, `LoginAttempt`, генерация секретов и PKCE, сроки, `safe_return_to` —
      unit-тест на `return_to` (`//evil`, `/\evil`, `https://evil`, `/%2F/evil`, управляющие символы,
      пустое значение → `/`); mypy чистый
- [x] Таблицы, репозитории, миграция `0003_browser_sessions` — `alembic upgrade head` и `downgrade -1`
      на чистом Postgres проходят
- [x] `OidcProvider` (общие discovery и JWKS) и `OidcCodeFlowClient`: authorize URL, обмен кода, проверка
      `id_token` с `nonce` — существующие тесты `test_oidc_verifier.py` зелёные; integration-тест: `id_token`
      с чужим `aud` или неверным `nonce` отклоняется
- [x] `BrowserLoginService` и `BrowserSessionService`, `AuthMethod.COOKIE`, cookie в `AuthService` —
      integration-тест: повторный callback с тем же `state` отклоняется; сессия старше 30 дней простоя или
      90 дней со входа не принимается; отключённый пользователь — `PermissionDeniedError`
- [x] `WebSettings`, провайдеры dishka, роутер `/api/v1/auth/*`, cookie-схема и CSRF в `fastapi/auth.py` —
      e2e: юзер A с cookie не видит и не меняет данные юзера B; `POST` с cookie без `Origin` или с чужим — 403,
      с правильным — проходит; Bearer важнее cookie; `/mcp` с одной cookie — 401; `WEB__ORIGIN` пуст — `/auth/*` 404
- [ ] Rauthy локально: клиент `atomic-tasks-web` (confidential, PKCE S256, redirect URI
      `http://localhost:8000/…/callback` и `http://localhost:5173/…/callback`); `compose.yaml`, `.env.example`,
      `docs/dev/rauthy.md` — сквозной вход в браузере с `WEB__ORIGIN=http://localhost:8000`
      на `localhost:8000/api/v1/auth/login`: cookie
      httpOnly, `/api/v1/me` отвечает, создание PAT работает, logout → `/me` 401
- [x] Прод-конфиг: `WEB__*` в `deploy/compose.yaml` и `deploy/.env.example`, заведение клиента в
      `docs/deploy.md`; `docs/architecture.md` — аутентификация через cookie; openapi.json содержит три
      новых `operation_id` и cookie-схему; ruff, mypy, lint-imports, pytest чистые; `/security-review` пройден
- [ ] После выкатки: вход с сайта на проде (когда веб выкачен) или напрямую через
      `https://WEB_HOST/api/v1/auth/login`,
      повторный вход через сутки не нужен; результаты — в спеку, статус спеки и roadmap — «реализована»
