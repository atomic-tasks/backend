# План

## Затронутые слои и файлы

- `config/settings.py` — `McpSettings.resource_url: str | None` (публичный адрес `/mcp`).
- `application/dto.py` — `AuthTarget` (`API`, `MCP`): куда пришёл запрос.
- `application/ports/oidc.py` — `TokenVerifier.verify(raw, *, target)`.
- `application/services/auth_service.py` — `authenticate(authorization, *, target)`, пробрасывает `target`
  в верификатор; PAT от `target` не зависит.
- `infrastructure/auth/oidc.py` — `OidcConfig.mcp_resource: str | None`; допустимые `aud`:
  `API` → `audience`, `MCP` → `audience + [mcp_resource]`.
- `presentation/fastapi/auth.py` — `target=AuthTarget.API`.
- `presentation/mcp/auth.py` — `target=AuthTarget.MCP`; при `401` добавить
  `WWW-Authenticate: Bearer resource_metadata="…"`, если ресурс настроен.
- `presentation/mcp/metadata.py` (новый) — Starlette-маршрут
  `GET /.well-known/oauth-protected-resource/mcp` → JSON (RFC 9728):
  `resource`, `authorization_servers: [issuer]`, `scopes_supported: ["openid", "email", "profile"]`,
  `bearer_methods_supported: ["header"]`. Вне `McpAuthMiddleware` (путь не начинается с `/mcp`).
- `presentation/mcp/server.py` — подключить маршрут к Starlette-приложению MCP.
- `config/app.py`, `config/dishka/providers.py` — прокинуть `resource_url` и issuer.
- `docker/rauthy/config.toml`, `deploy/rauthy/config.toml`, `compose.yaml`, `deploy/compose.yaml`,
  `.env.example`, `deploy/.env.example` — ephemeral clients (CIMD) или dynamic clients с
  `allowed_resources` = адрес ресурса (через env), `MCP__RESOURCE_URL` для API.
- Возможно: версия образа Rauthy (см. открытые вопросы спеки).
- Документация: `docs/dev/rauthy.md` (локальная проверка коннектора через MCP Inspector),
  `docs/deploy.md` (подключение коннектора в проде), `docs/architecture.md` (раздел аутентификации).
- ADR 0012 «OAuth для MCP: ресурс-привязанные токены Rauthy, CIMD/DCR» — фиксирует выбор регистрации
  и правило «токен MCP не принимается в REST».

Зависимостей не добавляем: `pyjwt` уже есть, метаданные — простой JSON.
Встроенную OAuth-поддержку SDK `mcp` (`AuthSettings`, `BearerAuthBackend`) не используем: у нас уже
единый `AuthService` для REST и MCP; из SDK берём только формат URL метаданных.

## Модель данных и миграции

Нет. Пользователь коннектора — тот же `(issuer, sub)` в `user_identities`.

## Порты и сервисы

- `TokenVerifier.verify(raw, *, target: AuthTarget)` — меняется сигнатура.
- `AuthService.authenticate(authorization, *, target: AuthTarget)`.

## FastAPI

Новых эндпоинтов нет. `openapi.json` не меняется (метаданные — маршрут MCP-приложения, вне схемы).

## MCP-тулы

Не меняются.

## Риски

- Rauthy 0.37.2 может не уметь `resource` для dynamic/ephemeral клиентов → обновление IdP в проде.
- Открытый DCR (если CIMD не заработает): любой может зарегистрировать клиента и показывать пользователю
  страницу входа нашего Rauthy со своим redirect. Смягчение: лимит регистраций по IP, allowlist email
  на бэкенде, `allowed_resources` только наш ресурс — токен годится только для `/mcp`.
- Claude может не найти метаданные Rauthy из-за пути `/auth/v1/` в issuer.
- Смена сигнатуры порта затрагивает фейки в `tests/fakes.py`.
