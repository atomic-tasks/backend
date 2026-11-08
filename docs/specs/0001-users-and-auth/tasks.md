# Задачи

- [ ] **Zitadel в compose.** Сервис, база `zitadel`, masterkey в `.env.example`, `docs/dev/zitadel.md`.
  Готово: локально вход в консоль Zitadel через Google и GitHub.
- [ ] **Домен.** `User`, `UserIdentity`, `ApiToken`, `TokenScope`, ошибки.
  Готово: unit-тесты на срок, отзыв, права токена и отключённого пользователя.
- [ ] **Таблицы и миграция.** Готово: `alembic upgrade head` и `downgrade base` на чистой базе проходят.
- [ ] **Порты и репозитории**, `TransactionManager`. Готово: mypy и lint-imports чистые.
- [ ] **JwtVerifier и AuthSettings.** Готово: integration-тест проверки JWT на локальных ключах
  (подпись, `iss`, `aud`, `exp`, неизвестный `kid`).
- [ ] **UserService.** Готово: integration-тест на Postgres — создание по allowlist, отказ без `email_verified`,
  повторный вход обновляет email, не создавая дубль.
- [ ] **TokenService.** Готово: integration-тест — жизненный цикл токена, лимит 10, отзыв, просрочка.
- [ ] **FastAPI.** Зависимость аутентификации, `/api/v1/me`, `/api/v1/tokens`, Swagger OAuth, problem details.
  Готово: вход через `/docs` и создание токена вручную работают.
- [ ] **MCP.** ASGI-обёртка аутентификации, `IdentityProvider` для MCP.
  Готово: `/mcp` с PAT отвечает, без токена — 401 с `WWW-Authenticate`.
- [ ] **e2e: изоляция и безопасность.** Пользователь A не видит и не отзывает токены B; PAT не создаёт PAT;
  `read`-токен не меняет данные; отключённый пользователь получает 403; отозванный токен — 401.
- [ ] **Документация.** README (как получить токен и подключить Claude Code), `.env.example`, `docs/architecture.md`.
  Готово: по README можно пройти путь от `docker compose up` до работающего MCP в Claude Code.
