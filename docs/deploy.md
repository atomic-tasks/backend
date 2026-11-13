# Деплой

Runbook прода (спека 0006, ADR 0011): VPS с уже работающим Traefik, один compose-стек в `/opt/atomic-tasks`,
выкатка из GitHub Actions по тегу с подтверждением. Файлы стека — `deploy/`.

Обозначения ниже: `<API_HOST>` — адрес API (например, `atomic.example.com`), `<AUTH_HOST>` — Rauthy
(`auth.example.com`), `<server>` — SSH-адрес VPS.

## 1. Что должно быть на сервере

- Docker с Compose v2, `curl`, `flock` (util-linux).
- Traefik, подключённый к docker-провайдеру, с внешней сетью, entrypoint на 443 и certresolver (Let's Encrypt).
  Узнать параметры:

  ```bash
  docker network ls                     # имя сети Traefik → TRAEFIK_NETWORK
  docker network inspect <сеть> -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'   # → TRAEFIK_SUBNET
  ```

  Имена entrypoint и certresolver — из статического конфига Traefik (`entryPoints`, `certificatesResolvers`).
  Если у Traefik `exposedByDefault=false`, это нормально: наши сервисы ставят `traefik.enable=true`.
- DNS: записи `A` (и `AAAA`, если есть IPv6) для `<API_HOST>` и `<AUTH_HOST>` на IP сервера.

## 2. Пользователь и каталоги (один раз, под root)

```bash
useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy                    # фактически root — см. ADR 0011
install -d -o deploy -g deploy -m 700 /opt/atomic-tasks /var/backups/atomic-tasks
```

В `~deploy/.ssh/authorized_keys` — две строки: ваш личный ключ (обычный доступ, для обслуживания и скачивания
бэкапов) и ключ CI с ограничением из `deploy/authorized_keys.example`.

## 3. Первая установка стека (под deploy)

Нужен релиз, в котором уже есть `deploy.tar.gz` (первый — после мёржа спеки 0006).

```bash
cd /opt/atomic-tasks
V=0.2.0   # версия релиза
curl -fsSLO "https://github.com/atomic-tasks/backend/releases/download/v$V/deploy.tar.gz"
tar -xzf deploy.tar.gz && rm deploy.tar.gz
curl -fsSL -o .env "https://raw.githubusercontent.com/atomic-tasks/backend/v$V/deploy/.env.example"
chmod 600 .env && chmod 755 deploy.sh backup.sh
```

Заполнить `.env`: хосты и Traefik из п. 1, секреты — командами из комментариев в файле. Затем:

```bash
./deploy.sh "$V"
```

Пакет `ghcr.io/atomic-tasks/backend` должен быть публичным (GitHub → Packages → Package settings →
Change visibility), иначе pull упадёт с `unauthorized`.

## 4. Rauthy

1. **Issuer.** Проверить, что Rauthy за прокси отдаёт https-issuer, ровно такой, какой ждёт API
   (`https://<AUTH_HOST>/auth/v1/`, `deploy/compose.yaml`):

   ```bash
   curl -s https://<AUTH_HOST>/auth/v1/.well-known/openid-configuration | jq -r .issuer
   ```

   Если отличается — входы будут отклоняться с 401; остановиться и разобраться до настройки провайдеров.
2. **Администратор.** Пароль при первом запуске — в логах:
   `docker compose logs rauthy | grep -i -A2 password` (нужен `export VERSION=$(cat .deployed-version)` —
   без него compose не читает файл). Войти в `https://<AUTH_HOST>/auth/v1/admin`, сменить пароль,
   зарегистрировать passkey — MFA для админки в проде обязательна.
3. **GitHub и Google** — как в `docs/dev/rauthy.md`, разделы 3–4, но с прод-адресами:
   Homepage `https://<AUTH_HOST>`, callback / redirect URI `https://<AUTH_HOST>/auth/v1/providers/callback`.
   Для прода — отдельные OAuth-приложения, не локальные. У провайдеров включить auto-onboarding.
   В Google — перевести consent screen из тестового режима или добавить себя в Test users.
4. **Клиент Swagger** — как в `docs/dev/rauthy.md`, раздел 6: `atomic-tasks-swagger`, public, PKCE S256,
   redirect `https://<API_HOST>/docs/oauth2-redirect`, allowed origin `https://<API_HOST>`.

## 5. Проверка после первой установки

- `https://<API_HOST>/health` → `{"status":"ok"}`, сертификат валиден.
- `https://<API_HOST>/docs` → Authorize → вход через Google → `GET /api/v1/me` → `POST /api/v1/tokens`.
- Claude Code с этим токеном:

  ```bash
  claude mcp add --transport http atomic-tasks https://<API_HOST>/mcp --header "Authorization: Bearer at_..."
  ```

- Метаданные ресурса для MCP-коннекторов (спека 0007):
  `curl https://<API_HOST>/.well-known/oauth-protected-resource/mcp` → `resource` = `https://<API_HOST>/mcp`,
  `authorization_servers` = `https://<AUTH_HOST>/auth/v1/`.
- Коннектор в приложении Claude: Settings → Connectors → Add custom connector → URL `https://<API_HOST>/mcp`,
  без client id и secret → Connect → вход через Google. Агент видит дерево (`browse_folder`).
  Если Claude пишет «Сервер не поддерживает автоматическую регистрацию клиентов», а в
  `docker compose logs rauthy` — `Cannot fetch ephemeral client document … 403 Forbidden`, значит `claude.ai`
  не отдаёт документ клиента IP сервера (блокировка по региону). Тогда клиент заводится вручную:
  1. Админка Rauthy → Clients → добавить: Client ID `claude-connector`, **public** (без секрета),
     redirect `https://claude.ai/api/mcp/auth_callback`, flows `authorization_code` и `refresh_token`,
     PKCE `S256`, scopes `openid email profile`, Allowed resources `https://<API_HOST>/mcp`.
  2. В `.env` на сервере: `MCP__EXTRA_TRUSTED_CLIENTS=["claude-connector"]` (JSON в одну строку),
     затем `export VERSION=<текущая версия>` и `docker compose up -d api`.
  3. В Claude, в настройках коннектора: «Клиент OAuth» → «Использовать свой OAuth-клиент» → `claude-connector`,
     секрет пустой.

  Для других приложений (ChatGPT и т.п.) — так же, отдельный клиент со своим redirect URI.
  Подключение без токена из Claude Code — так же через OAuth:
  `claude mcp add --transport http atomic-tasks https://<API_HOST>/mcp`, затем `/mcp` → Authenticate.
- Тело больше 1 МиБ отклоняется прокси:
  `head -c 2000000 /dev/zero | curl -s -o /dev/null -w '%{http_code}\n' -X POST --data-binary @- https://<API_HOST>/api/v1/tasks`
  → `413`.
- Память: `docker stats --no-stream` — записать в «Открытые вопросы» спеки 0006.

## 6. Выкатка из GitHub Actions

Один раз, **до первого тега с джобой `deploy`**: если environment `production` не существует, GitHub создаёт
его при первом запуске джобы сам — без правил защиты.

1. Environment `production` с защитой (или то же в UI, см. шаг 4):

   ```bash
   R=repos/atomic-tasks/backend/environments/production
   gh api -X PUT $R --input - <<EOF
   {"wait_timer":0,"prevent_self_review":false,"can_admins_bypass":false,
    "reviewers":[{"type":"User","id":$(gh api user -q .id)}],
    "deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
   EOF
   gh api -X POST $R/deployment-branch-policies -f name=main -f type=branch
   gh api -X POST $R/deployment-branch-policies -f name='v*' -f type=tag
   ```

   - reviewer — джоба ждёт вашего Approve; `prevent_self_review` выключен, иначе одобрить свой запуск некому;
   - `can_admins_bypass: false` — подтверждение не обходит и админ;
   - только ветка `main` и теги `v*` получают секреты: ветка с изменённым `release.yml` до ключа не дотянется.
2. Ключ CI (на ноутбуке, без пароля):
   `ssh-keygen -t ed25519 -N '' -C github-actions-atomic-tasks-deploy -f deploy_key`.
   Публичную часть — на сервер строкой из `deploy/authorized_keys.example`.
3. `known_hosts` сервера: `ssh-keyscan -p <порт> <server>`. Сверить отпечаток с выводом на самом сервере
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` — иначе закрепим чужой ключ.
4. GitHub → Settings → Environments → **production** (проверить правила из шага 1):
   - Required reviewers — вы;
   - Deployment branches and tags — Selected: тег `v*` и ветка `main` (ручной запуск — только из `main`);
   - Secrets: `DEPLOY_SSH_KEY` (приватный ключ целиком), `DEPLOY_KNOWN_HOSTS` (вывод ssh-keyscan);
   - Variables: `DEPLOY_HOST`, `DEPLOY_USER` (`deploy`), `DEPLOY_PORT` (если не 22), `API_HOST`.

   ```bash
   gh secret set DEPLOY_SSH_KEY --env production < deploy_key
   gh secret set DEPLOY_KNOWN_HOSTS --env production < known_hosts
   gh variable set DEPLOY_HOST --env production --body <server>
   ```

   После загрузки удалить `deploy_key` с ноутбука.

Каждый релиз: тег по `guides/releases.md` → после публикации джоба `deploy` ждёт подтверждения →
Review deployments → Approve. Джоба выкатывает версию тега и проверяет `https://<API_HOST>/openapi.json`.

## 7. Откат и повторная выкатка

```bash
gh workflow run release.yml --ref main -f version=0.2.0
```

Миграции назад не откатываются. Если новая схема несовместима со старым кодом — восстановление из бэкапа (п. 8).

Если `deploy.sh` пишет «в релизе новая версия deploy.sh» — посмотреть дифф и заменить руками:

```bash
diff deploy.sh deploy.sh.new && mv deploy.sh.new deploy.sh && chmod 755 deploy.sh
```

## 8. Бэкап и восстановление

Cron пользователя `deploy` (`crontab -e`):

```
15 3 * * * /opt/atomic-tasks/backup.sh >> /opt/atomic-tasks/backup.log 2>&1
```

Дампы — `/var/backups/atomic-tasks/<YYYY-MM-DD>/{atomic_tasks,rauthy}.dump`, 7 дней. Копия только на сервере:
при потере VPS теряется всё после последнего скачивания. Забрать на ноутбук (личным ключом):

```bash
scp -r deploy@<server>:/var/backups/atomic-tasks/"$(date +%F)" ~/atomic-tasks-backups/
```

Проверка, что бэкап восстанавливается (прод не трогается — разворачиваем во временную базу рядом):

```bash
cd /opt/atomic-tasks && export VERSION=$(cat .deployed-version) && ./backup.sh
D=/var/backups/atomic-tasks/$(date +%F)
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" restore_check && pg_restore --no-owner -U "$POSTGRES_USER" -d restore_check' < "$D/atomic_tasks.dump"
for db in atomic_tasks restore_check; do
  docker compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d $db -tAc \"select '$db', (select count(*) from users), (select count(*) from folders), (select count(*) from tasks)\""
done   # числа должны совпасть
docker compose exec -T postgres pg_restore -l < "$D/rauthy.dump" | head -5   # оглавление без ошибок
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" restore_check'
```

Дата каталога — по часам сервера (обычно UTC).

Восстановление поверх прода (на сервере, под deploy):

```bash
cd /opt/atomic-tasks && export VERSION=$(cat .deployed-version)
D=/var/backups/atomic-tasks/2026-11-11
docker compose stop api rauthy
for db in atomic_tasks rauthy; do
  docker compose exec -T postgres sh -c "pg_restore --clean --if-exists -U \"\$POSTGRES_USER\" -d $db" < "$D/$db.dump"
done
docker compose up -d
```

## 9. Обслуживание

Любая команда compose в `/opt/atomic-tasks` — с `export VERSION=$(cat .deployed-version)`: без версии
compose отказывается читать файл, чтобы случайно не поднять API с другим образом.

```bash
docker compose ps
docker compose logs -f --tail 100 api
```
