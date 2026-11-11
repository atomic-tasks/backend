# План

## Затронутые слои и файлы

Код приложения не меняется. Новое — инфраструктура и документация.

```
deploy/
├── compose.yaml            # прод-стек: postgres, rauthy, migrate, api; labels Traefik; без ports
├── rauthy/config.toml      # прод-конфиг Rauthy (https, proxy_mode, MFA админки, без danger-insecure)
├── .env.example            # все переменные прода с комментариями, без значений секретов
├── deploy.sh               # выкатка версии: проверка аргумента, pull, migrate, up, проверка /openapi.json
├── backup.sh               # pg_dump обеих баз + ротация 7 дней; для cron
└── authorized_keys.example # строка с forced command и ограничениями для ключа CI
.github/workflows/release.yml  # + deploy-бандл в релиз, + джоба deploy (environment production), + workflow_dispatch
docs/deploy.md              # runbook: подготовка сервера, первый запуск, Rauthy, выкатка, откат, бэкап и восстановление
docs/adr/0011-deploy-behind-traefik.md
docs/architecture.md        # раздел «Деплой»
docs/roadmap.md             # статус 0006, закрытый техдолг
compose.yaml                # без изменений (локальная разработка)
```

`docker/postgres/init/01-rauthy.sh` переиспользуется прод-стеком как есть.

## Стек на сервере

- Каталог `/opt/atomic-tasks` (переменная `DEPLOY_PATH`): `compose.yaml`, `rauthy/`, `docker/postgres/init/`,
  `deploy.sh`, `backup.sh` из deploy-бандла релиза; `.env` — только на сервере, руками.
- Сети: `internal` (postgres, rauthy, api, migrate) и внешняя сеть Traefik `${TRAEFIK_NETWORK}` (rauthy, api).
  Postgres в сети Traefik не попадает.
- Labels:
  - api: `Host(${API_HOST})`, entrypoint `${TRAEFIK_ENTRYPOINT}`, `tls.certresolver=${TRAEFIK_CERTRESOLVER}`,
    middleware `buffering.maxRequestBodyBytes=1048576`; `traefik.docker.network=${TRAEFIK_NETWORK}`.
  - rauthy: `Host(${AUTH_HOST})`, тот же entrypoint и certresolver, порт 8080.
- API: `image: ghcr.io/atomic-tasks/backend:${VERSION}`; переменные приложения передаются поимённо
  (секреты Rauthy в контейнер API не попадают); env: `AUTH__ISSUER=https://${AUTH_HOST}/auth/v1/`,
  `AUTH__INTERNAL_URL=http://rauthy:8080` (JWKS без выхода наружу), `MCP__ALLOWED_HOSTS=["${API_HOST}"]`,
  `FORWARDED_ALLOW_IPS=${TRAEFIK_SUBNET}` (uvicorn читает его из env; `--proxy-headers` уже в CMD).
- `restart: unless-stopped` у долгоживущих сервисов; healthcheck у Postgres как локально.
- Postgres: том `postgres-data`, `shm_size` по умолчанию; порт не публикуется.

## Rauthy в проде

- Статичный `deploy/rauthy/config.toml`: `scheme = "http"` (TLS терминирует Traefik), `proxy_mode = true`,
  cookie_mode и `admin_force_mfa` по умолчанию (`host`, `true`).
- Из env (compose): `PUB_URL=AUTH_HOST`, `TRUSTED_PROXIES` = подсеть Traefik + внутренняя подсеть стека
  (с `proxy_mode` Rauthy блокирует остальные источники, а API ходит за JWKS изнутри), `RP_ID=AUTH_HOST`,
  `RP_ORIGIN=https://AUTH_HOST:443`.
- Внутренняя сеть стека с фиксированной подсетью `INTERNAL_SUBNET` (по умолчанию `172.31.250.0/24`).
- Redirect URI провайдеров: `https://AUTH_HOST/auth/v1/providers/callback`. Клиент Swagger:
  redirect `https://API_HOST/docs/oauth2-redirect`, allowed origin `https://API_HOST`.

## Выкатка

`release.yml` после публикации релиза:

1. Шаг в джобе `release`: `tar` каталога `deploy/` + `docker/postgres/init/` → `deploy.tar.gz` в GitHub Release
   (конфиг стека версионируется вместе с образом).
2. Джоба `deploy` (`needs: release`, `environment: production`, `permissions: {}`):
   - `ssh` из runner без сторонних actions: ключ из `secrets.DEPLOY_SSH_KEY`, `known_hosts` из
     `secrets.DEPLOY_KNOWN_HOSTS`, `StrictHostKeyChecking=yes`;
   - команда — только версия: `ssh deploy@host X.Y.Z`. На сервере forced command
     `deploy.sh "$SSH_ORIGINAL_COMMAND"` с `restrict` в `authorized_keys`.
3. `workflow_dispatch` с входом `version` — только джоба `deploy` (для отката и повторной выкатки).
   Версия проверяется тем же regex, что тег.

`deploy.sh <X.Y.Z>`:

1. Аргумент строго `^[0-9]+\.[0-9]+\.[0-9]+$`, иначе выход.
2. Скачать `deploy.tar.gz` релиза `vX.Y.Z` из GitHub (публичный репозиторий, https), распаковать во временный
   каталог и заменить файлы стека (кроме `.env`).
3. `VERSION=X.Y.Z docker compose pull api migrate`.
4. `docker compose run --rm migrate` — при ошибке выход, API не трогаем.
5. `docker compose up -d --remove-orphans`.
6. До 60 с ждать, пока `http://api:8000/openapi.json` (изнутри сети через `docker compose exec`) вернёт
   `info.version == X.Y.Z`; записать версию в `.deployed-version`.

Сам `deploy.sh` на сервере обновляется руками (он же forced command). Новая версия из бандла кладётся
рядом как `deploy.sh.new`, и runbook говорит, когда её применить.

## Бэкап

`backup.sh` (cron пользователя деплоя, ежедневно): `docker compose exec -T postgres pg_dump -Fc` для
`atomic_tasks` и `rauthy` → `/var/backups/atomic-tasks/<дата>/`, права `600`, удаление старше 7 дней.
Runbook: `scp` свежего дампа на ноутбук; восстановление — `pg_restore --clean` в остановленный стек.

## Модель данных и миграции

Без изменений.

## Порты и сервисы

Без изменений.

## FastAPI

Без изменений. Проверка версии — по `info.version` в `/openapi.json`.

## MCP-тулы

Без изменений.

## Риски

- **Issuer за прокси**: если Rauthy с `scheme = "http"` отдаст `http://`-issuer, `AUTH__ISSUER` разойдётся с `iss`.
  Проверяется первым после запуска (runbook, п. 4).
- **Forced command + бандл из релиза**: на сервере нужна загрузка с github.com. Если это неудобно — запасной путь:
  `scp` бандла из джобы (тогда ключу нужен `scp` в forced command, сложнее ограничить).
- **Пользователь в группе `docker` — фактически root** на VPS, где живут и другие сервисы. Forced command
  снижает риск утечки ключа CI, но не отменяет его. Принимаем.
- **Миграции без отката**: релиз с несовместимой миграцией откатывается только восстановлением из бэкапа.
  Правило для будущих миграций: expand → contract в разных релизах.
- **Бэкап на том же сервере**: при потере VPS теряем данные с момента последнего ручного скачивания.
- **Hairpin**: если `AUTH__INTERNAL_URL` не задан, API ходит за JWKS через публичный адрес. Мы его задаём.
