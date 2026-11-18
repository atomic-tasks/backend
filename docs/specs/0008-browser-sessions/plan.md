# План

Два PR. Первый — спека, ADR 0013, roadmap, этот план и хосты в Traefik; после мёржа — отдельный релиз
с переездом бэкенда на `api.atomic.<domain>`. Второй — реализация входа.

## Затронутые слои и файлы

**Хосты (PR 1)** — кода приложения не касается
- `deploy/compose.yaml` — у сервиса `api` второй роутер `atomic-web-api`:
  ``Host(`${WEB_HOST:?}`) && PathPrefix(`/api/`)``, тот же entrypoint, certresolver, middleware
  `atomic-api-body-limit` и сервис `atomic-api`. Префикс со слешем: `PathPrefix(/api)` поймал бы и `/apix`
  сайта. Правило длиннее, чем `Host(WEB_HOST)` сайта, — Traefik отдаст ему приоритет и без `priority`.
  Роутер `atomic-api` (``Host(`${API_HOST}`)``) не меняется — меняется значение `API_HOST`.
- `deploy/.env.example` — `WEB_HOST=<atomic.example.com>`, `API_HOST=<api.atomic.example.com>`.
- `docs/deploy.md` — runbook переезда, порядок важен:
  1. DNS `api.atomic.<domain>` → сервер (сертификат Traefik выпустит сам).
  2. `.env` на сервере: `API_HOST` — новый, `WEB_HOST` — старый `atomic.<domain>`.
  3. Rauthy: redirect URI клиента `atomic-tasks-swagger` → `https://<API_HOST>/docs/oauth2-redirect`;
     у вручную заведённых MCP-клиентов (`MCP__EXTRA_TRUSTED_CLIENTS`) — разрешённый ресурс на новый `/mcp`.
     Ресурс CIMD-клиентов (`EPHEMERAL_CLIENTS_ALLOWED_RESOURCES`) идёт из `API_HOST` сам.
  4. GitHub: переменная `API_HOST` (её читает проверка версии в `release.yml`) и URL environment `production`.
  5. Выкатка релиза. Проверка: `https://<API_HOST>/health`, `/docs`, `/openapi.json`, `/mcp`;
     `https://<WEB_HOST>/api/v1/me` → `401`, `https://<WEB_HOST>/` → `404`.
  6. Переподключить коннекторы MCP на `https://<API_HOST>/mcp`.
  Откат — вернуть `API_HOST` в `.env` и `docker compose up -d`; Rauthy-правки обратимы.
- `docs/architecture.md` — раздел о хостах.

**Вход (PR 2)**
- `domain/entities/browser_session.py` (новый) — `BrowserSession`, `LoginAttempt`, генерация секрета,
  проверка `return_to`, сроки (`IDLE_TTL = 30 дней`, `MAX_TTL = 90 дней`, `LOGIN_TTL = 10 минут`).
  Хеш — `hash_token` из `api_token.py` (вынести в общий `domain/secrets.py`, если импорт между сущностями
  выглядит странно).
- `application/dto.py` — `AuthMethod.COOKIE`; `Identity.require_session()` пускает `SESSION` и `COOKIE`
  (переименовать в `require_interactive` — по месту, если затронет мало вызовов). DTO `LoginStart`
  (`redirect_url`, `state`), `LoginResult` (`session_secret`, `return_to`), `LoginFailure` (код ошибки).
- `application/ports/browser_sessions.py` (новый) — репозитории сессий и попыток входа.
- `application/ports/oidc.py` — порт `OidcClient` (authorize URL, обмен кода на проверенные claims).
- `application/services/browser_login_service.py` (новый) — `BrowserLoginService`: `start`, `finish`, `logout`.
- `application/services/browser_session_service.py` (новый) — `BrowserSessionService.authenticate(secret)`.
- `application/services/auth_service.py` — `authenticate(authorization, *, target, session_cookie=None)`:
  Bearer → как раньше; иначе cookie при `target=API` → `BrowserSessionService`.
- `infrastructure/auth/oidc.py` — вынести discovery и JWKS из `OidcTokenVerifier` в общий `OidcProvider`,
  чтобы верификатор и клиент не ходили за ними дважды.
- `infrastructure/auth/oidc_client.py` (новый) — `OidcCodeFlowClient`: стандартный authorization code + PKCE
  по discovery, без Rauthy-специфики (смена IdP по ADR 0009 — только настройки). Token endpoint — серверный запрос через `internal_url`,
  authorize URL — публичный issuer. Аутентификация клиента — `client_secret_basic`.
- `infrastructure/postgres/tables/`, `repositories/` — таблицы и репозитории; миграция `0003_browser_sessions`.
- `presentation/fastapi/auth.py` — cookie как вторая схема (`APIKeyCookie`), CSRF-проверка `Origin`.
- `presentation/fastapi/routers/auth.py` (новый) — `login`, `callback`, `logout`, вне зависимости
  аутентификации `/api/v1`.
- `presentation/fastapi/app.py` — подключить роутер, передать origin.
- `config/settings.py` — `WebSettings` (`WEB__`): `origin: str | None`, `client_id: str`,
  `client_secret: SecretStr`. Сроки — константы домена, не настройки.
- `config/dishka/providers.py`, `config/app.py` — провайдеры новых сервисов, репозиториев и `OidcClient`.
- `compose.yaml`, `.env.example`, `deploy/compose.yaml`, `deploy/.env.example` — `WEB__*` для API
  (на проде `WEB__ORIGIN: https://${WEB_HOST}`, секрет клиента — из `.env`).
- `docs/dev/rauthy.md`, `docs/deploy.md` — клиент `atomic-tasks-web` в Rauthy; `docs/architecture.md` —
  раздел аутентификации.

Зависимостей не добавляем: PKCE — `secrets` + `hashlib`, `id_token` проверяет уже имеющийся `pyjwt`, запрос
к token endpoint — `urllib`, как discovery и userinfo сейчас. Authlib умеет то же, но тянет
`SessionMiddleware` с подписанной cookie, а её мы отвергли.

## Модель данных и миграции

`0003_browser_sessions`:

- `browser_sessions`: `id uuid pk`, `user_id uuid fk users on delete cascade`, `token_hash text unique`,
  `created_at`, `last_seen_at`, `expires_at timestamptz` (абсолютный предел). Индекс по `user_id`.
  Активна, если `now < expires_at` и `now < last_seen_at + 30 дней`.
- `login_attempts`: `id uuid pk`, `state_hash text unique`, `code_verifier text`, `nonce text`, `return_to text`,
  `expires_at timestamptz`. Без пользователя: он появляется только на callback.

Очистка — `DELETE … WHERE expires_at < now` (для сессий ещё и по `last_seen_at`) в `finish` при каждом входе.

## Порты и сервисы

- `BrowserSessionRepository`: `add`, `get_by_hash`, `delete(id)`, `delete_expired(now)`.
- `LoginAttemptRepository`: `add`, `pop_by_state_hash(hash) -> LoginAttempt | None` (`DELETE … RETURNING`),
  `delete_expired(now)`.
- `OidcClient`: `authorization_url(*, state, code_challenge, nonce, redirect_uri) -> str`;
  `exchange_code(*, code, code_verifier, nonce, redirect_uri) -> VerifiedClaims` — проверяет `id_token`
  (подпись, `iss`, `aud = client_id`, `exp`, `nonce`), токены наружу не отдаёт.
- `BrowserLoginService` (attempts, sessions, oidc client, `IdentityService`, tx, clock, `WebLoginConfig`):
  - `start(return_to)` — нормализует `return_to`, создаёт попытку, отдаёт URL Rauthy и `state` для cookie.
  - `finish(state_cookie, state_param, code)` — сравнение `state` через `secrets.compare_digest`, `pop`,
    обмен кода, `IdentityService.resolve` (allowlist и `email_verified` — там же, где для JWT), сессия,
    очистка просроченного. Ошибки — `LoginFailure` с кодом, без деталей наружу.
  - `logout(secret)` — удалить сессию, если есть.
- `BrowserSessionService.authenticate(secret)` — сессия по хешу, срок, пользователь `ensure_active()`,
  `touch` не чаще раза в минуту → `Identity(scope=WRITE, method=COOKIE)`.
- `WebLoginConfig` — dataclass в application (`redirect_uri`, `client_id`), собирается из `Settings` в провайдере.

## FastAPI

- `GET /api/v1/auth/login?return_to=` → `302` в Rauthy + `Set-Cookie: __Host-at_login` (`Max-Age=600`).
- `GET /api/v1/auth/callback?code=&state=` (или `error=` от Rauthy) → `302` на `return_to` +
  `Set-Cookie: __Host-at_session` (`Max-Age` = 90 дней; реальный срок держит сервер) и удаление `__Host-at_login`.
  Ошибка → `302` на `/?login_error=access_denied|expired|failed`.
- `POST /api/v1/auth/logout` → `204`, удаление cookie, `Clear-Site-Data: "cache", "storage"`. Директиву
  `"cookies"` не шлём: она стирает cookie всего регистрируемого домена, включая сессию Rauthy на `AUTH_HOST`
  и чужие поддомены. CSRF-проверка — как у остальных небезопасных методов с cookie.
- Аутентификация `/api/v1`: Bearer есть → как раньше; иначе cookie `__Host-at_session` → сессия; для
  небезопасного метода `Origin` должен совпасть с `WEB__ORIGIN`, иначе `403`. Проверка `Origin` — в
  presentation: это свойство HTTP-транспорта, а не сценария.
- OpenAPI: третья схема безопасности `APIKeyCookie` (`__Host-at_session`); три новых `operation_id`.
  Эндпоинты `/auth/*` при выключенном входе (`WEB__ORIGIN` пуст) → `404`.

## MCP-тулы

Не меняются. `McpAuthMiddleware` cookie не читает — передаёт только заголовок `Authorization`.

## Риски

- Переезд `API_HOST` трогает четыре места вне репозитория (DNS, Rauthy, GitHub, коннекторы). Пропуск одного
  ломает Swagger, проверку релиза или MCP. Смягчение — пошаговый runbook и проверка после выкатки.
- `WEB_HOST` обязателен в compose (`:?`): `.env` на сервере правится до выкатки, иначе deploy упадёт на
  `compose pull` — до миграций, API не тронут.
- Пути сайта не должны начинаться с `/api/` — контракт для веба.
- Вход, начатый на `API_HOST` (`/api/v1/auth/login` там тоже доступен), закончится на `WEB_HOST` без
  login-cookie → `login_error=expired`. Безопасно, но непонятно — отметить в документации.
- `Secure`-cookie на `http://localhost` не работает в Safari — локальная разработка в Chrome/Firefox.
- `Origin` у небезопасных запросов: браузеры шлют его на same-origin `POST/PUT/PATCH/DELETE`, но прокси Vite
  может переписать `Host` (`changeOrigin`) — сравниваем только `Origin` с настройкой, `Host` не трогаем.
- Ошибка в разборе `return_to` — open redirect после входа. Отдельный unit-тест на набор злых значений.
- Клиент `atomic-tasks-web` в Rauthy и его секрет заводятся вручную (как Swagger) — шаг в runbook.
- Смена `AuthService.authenticate` и `AuthMethod` затрагивает фейки в `tests/fakes.py`.
