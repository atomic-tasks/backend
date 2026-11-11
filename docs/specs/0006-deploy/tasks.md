# Задачи

- [x] Разведка Rauthy 0.37: какие параметры (`pub_url`, `proxy_mode`, `trusted_proxies`, webauthn, cookie_mode,
      `admin_force_mfa`) задаются через env — ответ записан в «Открытые вопросы» спеки, выбран способ конфигурации
- [x] ADR 0011 «Деплой за Traefik, выкатка из GitHub Actions через forced command» — принят
- [x] `deploy/compose.yaml` + `deploy/.env.example` — `docker compose -f deploy/compose.yaml config` проходит
      с примером env; портов на хосте нет; labels Traefik для api и rauthy, буфер 1 МиБ на api
- [x] `deploy/rauthy/config.toml` для прода — нет `danger-insecure`, MFA админки включена, proxy_mode и
      trusted_proxies, webauthn на `AUTH_HOST`
- [x] `deploy/deploy.sh` — `shellcheck` чистый; неверный аргумент → выход без действий; при упавшей миграции
      API не перезапускается; проверка `info.version`
- [x] `deploy/backup.sh` — `shellcheck` чистый; дампы обеих баз с правами `600`, удаление старше 7 дней
- [x] `deploy/authorized_keys.example` — `restrict,command="..."`
- [x] `release.yml`: `deploy.tar.gz` в релизе; джоба `deploy` с `environment: production` и `permissions: {}`;
      `workflow_dispatch` с проверкой версии — `actionlint` чистый
- [x] `docs/deploy.md` — runbook: DNS, пользователь деплоя, подсеть Traefik, `.env`, ключ CI и `known_hosts`,
      environment `production` с reviewer, первый запуск, Rauthy (passkey, Google/GitHub, клиент Swagger),
      выкатка, откат, cron бэкапа, скачивание и восстановление
- [ ] Первый деплой на сервер по runbook (вместе с автором) — сценарий «Первый запуск» из спеки пройден целиком,
      включая MCP из Claude Code; пакет ghcr публичный
- [ ] Восстановление из бэкапа проверено один раз; `docker stats` и вход через GitHub записаны в спеку
- [ ] `docs/architecture.md` (раздел «Деплой»), `docs/roadmap.md` (0006 реализована, техдолг: лимит тела, MFA
      админки, ghcr public, вход через GitHub — закрыт), статус спеки — «реализована»
