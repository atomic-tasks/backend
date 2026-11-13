# Задачи

- [x] Проверить Rauthy локально: есть ли в 0.37.2 `resource` (RFC 8707) и `allowed_resources` для
      ephemeral/dynamic клиентов, объявляет ли discovery CIMD (`client_id_metadata_document_supported`)
      и `registration_endpoint`. Результат и выбор CIMD/DCR (и версия Rauthy) — в «Открытые вопросы» спеки —
      записано
- [x] ADR 0012: регистрация клиента Claude (CIMD/DCR), привязка токена к ресурсу, токен MCP не принимается
      в REST — ADR в `docs/adr/`
- [x] `AuthTarget`, новые сигнатуры `TokenVerifier.verify` и `AuthService.authenticate`, выбор допустимых
      `aud` в `OidcTokenVerifier`, `McpSettings.resource_url` и проброс в провайдерах — mypy и lint-imports
      чистые, существующие тесты зелёные
- [x] Тест в `integration/test_oidc_verifier.py`: токен с `aud` = MCP-ресурс принимается для `MCP`
      и отклоняется для `API`; без настроенного ресурса — отклоняется для обоих (дорогая ошибка: переигрывание
      токена коннектора против REST) — тесты зелёные
- [x] Маршрут `/.well-known/oauth-protected-resource/mcp` и `WWW-Authenticate` с `resource_metadata` на `401`
      в `McpAuthMiddleware`; при пустом `resource_url` — `404` и прежний `401` — проверено curl локально
- [x] Конфиг Rauthy локально (`docker/rauthy`, `.env.example`): CIMD,
      `allowed_resources` = `http://localhost:8000/mcp`; версия образа прежняя — Rauthy поднимается,
      `authorize` для CIMD-клиента открывает вход
- [x] Сквозная проверка локально через Claude Code (OAuth без PAT): вход через Google, токен с нужным `aud`,
      `browse_folder` возвращает дерево; шаги — в `docs/dev/rauthy.md` п. 7. Понадобился `RFC_8252_ENABLE`
- [x] Прод-конфиг: `deploy/rauthy/config.toml`, `deploy/compose.yaml`; шаги подключения коннектора
      в `docs/deploy.md` (обновление Rauthy не нужно) — runbook обновлён
- [x] `docs/architecture.md`: аутентификация коннектора; ruff, mypy, lint-imports, pytest чистые
- [ ] После выкатки: коннектор в приложении Claude (веб и телефон) подключается к `https://<API_HOST>/mcp`,
      агент видит дерево; refresh работает через сутки; результаты — в спеку, статус в roadmap — «реализована»
