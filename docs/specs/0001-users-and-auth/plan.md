# План

## Затронутые слои и файлы

**domain**
- `entities/user.py` — `User`, `UserIdentity`.
- `entities/api_token.py` — `ApiToken`, `TokenScope` (`read`, `write`): проверки срока, отзыва, достаточности прав.
- `exceptions.py` — `DomainError` и потомки: `UserDisabledError`, `RegistrationClosedError`,
  `TokenLimitExceededError`, `InsufficientScopeError`.

**application**
- `ports/`: `UserRepository`, `ApiTokenRepository`, `TransactionManager`, `IdentityProvider`
  (текущий пользователь и права запроса), `Clock`.
- `services/user_service.py` — найти или создать пользователя по `(issuer, sub)` с проверкой allowlist.
- `services/token_service.py` — создание, список, отзыв, аутентификация по PAT. Генерация и хеширование — stdlib
  (`secrets`, `hashlib`).
- `dto.py` — `AuthenticatedUser(user_id, scopes, via: jwt | pat)`, `CreatedToken`, `TokenInfo`.

**infrastructure**
- `postgres/tables/` — пакет: `base.py` (metadata, registry), `users.py` (`users`, `user_identities`),
  `api_tokens.py`. `postgres/mapping.py` — все `map_imperatively` в одном месте, вызываются один раз при старте.
- `postgres/repositories/` — `users.py`, `api_tokens.py`, `transaction.py`.
- `postgres/migrations/versions/` — первая миграция.
- `auth/jwt.py` — `JwtVerifier`: OIDC discovery, `PyJWKClient` с кэшем, проверка `iss`/`aud`/`exp`,
  алгоритмы EdDSA и RS256.

**presentation**
- `fastapi/auth.py` — зависимость: `Authorization: Bearer` → `at_...` в `TokenService`, иначе в `JwtVerifier`
  и `UserService`. Схема безопасности OAuth2 (Authorization Code + PKCE) для Swagger.
- `fastapi/routers/me.py`, `fastapi/routers/tokens.py` под префиксом `/api/v1`.
- `fastapi/errors.py` — доменные ошибки → 401/403/404/409 в формате problem details.
- `mcp/auth.py` — ASGI-обёртка над MCP-приложением: та же аутентификация, результат в request state;
  `IdentityProvider` для MCP читает его оттуда.

**config**
- `settings.py` — `AuthSettings`: `issuer`, `audience`, `allowed_emails`, `swagger_client_id`.
- `dishka/providers.py` — провайдеры репозиториев, сервисов, `JwtVerifier`, `IdentityProvider` для каждого входа.

**Окружение**
- `compose.yaml` — сервис `rauthy`, база `rauthy` в нашем Postgres (init-скрипт), ключи шифрования из `.env`.
- `docs/dev/rauthy.md` — как локально создать клиента для Swagger, подключить Google и GitHub.

## Модель данных и миграции

```
users
  id            uuid PK            -- uuid7
  display_name  varchar(200)
  email         varchar(320) NULL  -- только для отображения
  created_at, updated_at  timestamptz
  disabled_at   timestamptz NULL

user_identities
  id            uuid PK
  user_id       uuid FK → users ON DELETE CASCADE
  issuer        varchar(500)
  subject       varchar(255)
  created_at, last_login_at  timestamptz
  UNIQUE (issuer, subject)
  INDEX (user_id)

api_tokens
  id            uuid PK
  user_id       uuid FK → users ON DELETE CASCADE
  name          varchar(100)
  prefix        varchar(8)
  token_hash    varchar(64) UNIQUE   -- hex SHA-256
  scope         varchar(16)          -- строка без CHECK (ADR 0004)
  created_at    timestamptz
  last_used_at, expires_at, revoked_at  timestamptz NULL
  INDEX (user_id, revoked_at)
```

## Порты и сервисы

- `UserService.resolve(issuer, subject, email, email_verified, name) -> User` — находит по identity,
  обновляет email и имя; если не найден — проверяет allowlist и создаёт в одной транзакции.
- `TokenService.create(user, name, scope, ttl_days | None) -> CreatedToken` — лимит 10, секрет только в ответе.
- `TokenService.list(user)`, `TokenService.revoke(user, token_id)` — чужой или несуществующий id → «не найден».
- `TokenService.authenticate(raw) -> AuthenticatedUser` — хеш, поиск, проверка срока, отзыва и `disabled_at`,
  троттлинг `last_used_at`.

## FastAPI

| Метод | Путь | Доступ |
|---|---|---|
| GET | `/api/v1/me` | JWT или PAT (`read`) |
| POST | `/api/v1/tokens` | только JWT |
| GET | `/api/v1/tokens` | только JWT |
| DELETE | `/api/v1/tokens/{id}` | только JWT |

Swagger: `swagger_ui_init_oauth={"clientId": ..., "usePkceWithAuthorizationCodeGrant": True}`.

## MCP-тулы

Тулов в этой спеке нет. Готовится механизм: аутентификация на `/mcp` и проверка прав (`read`/`write`),
которую тулы из спеки 0004 будут объявлять.

## Риски

- Rauthy — проект с небольшим сообществом. Первым шагом проверяем всё, что нам от него нужно (ADR 0009).
- Настройка IdP локально — ручные шаги. Снижаем подробной инструкцией в `docs/dev/rauthy.md`.
- Недоступность JWKS — запросы с JWT падают. Кэш ключей и понятная 503 вместо 500.
- Обновление `last_used_at` на каждый запрос — лишняя запись. Троттлинг раз в минуту.
