# Rauthy локально

IdP проекта (ADR 0009). Здесь: как поднять его локально и проверить то, что нам от него нужно
(первый шаг спеки 0001). Rauthy работает на `http://localhost:8080`, наш API — на `http://localhost:8000`.

## 1. Секреты в .env

```bash
cp .env.example .env   # если .env ещё нет — иначе допишите блок Rauthy из .env.example
```

Заполните в `.env`:

```bash
echo "RAUTHY_ENC_KEY: $(openssl rand -hex 4)/$(openssl rand -base64 32)"
openssl rand -hex 24   # дважды — для RAUTHY_HQL_SECRET_RAFT и RAUTHY_HQL_SECRET_API
```

- `RAUTHY_ENC_KEYS` — строка вида `a1b2c3d4/....=`, `RAUTHY_ENC_KEY_ACTIVE` — её часть до `/` (`a1b2c3d4`).
- `RAUTHY_DB_PASSWORD` — любой, без кавычек.
- `RAUTHY_ADMIN_EMAIL` — ваш email (станет логином администратора Rauthy).

## 2. Запуск

База для Rauthy создаётся скриптом `docker/postgres/init/01-rauthy.sh` **только на пустом томе Postgres**.
Если Postgres уже запускался раньше и данных там нет — пересоздайте том:

```bash
docker compose down -v
```

Если данные уже есть — создайте роль и базу вручную:

```bash
docker compose exec postgres psql -U atomic_tasks -d atomic_tasks \
  -c "CREATE ROLE rauthy LOGIN PASSWORD '<RAUTHY_DB_PASSWORD>'" -c "CREATE DATABASE rauthy OWNER rauthy"
```

Затем:

```bash
docker compose up -d postgres rauthy
docker compose logs rauthy | grep -i -A2 password   # пароль администратора при первом запуске
```

Админка: http://localhost:8080/auth/v1/admin — вход по `RAUTHY_ADMIN_EMAIL` и паролю из логов.
Сразу смените пароль и добавьте passkey для администратора.

## 3. GitHub

1. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App
   ([ссылка](https://github.com/settings/applications/new)).
   - Homepage URL: `http://localhost:8080`
   - Authorization callback URL: `http://localhost:8080/auth/v1/providers/callback`
2. Скопируйте Client ID, сгенерируйте Client secret.
3. Админка Rauthy → Providers → добавить → тип `GitHub`, вставить Client ID и secret, включить
   **auto-onboarding**, сохранить.

## 4. Google

1. [Google Cloud Console](https://console.cloud.google.com/) → создать проект → APIs & Services →
   OAuth consent screen (External, тестовый режим, добавить свой email в Test users).
2. Credentials → Create credentials → OAuth client ID → Web application.
   - Authorized redirect URI: `http://localhost:8080/auth/v1/providers/callback`
3. Админка Rauthy → Providers → добавить → тип `Google`, если есть шаблон, иначе `OIDC`.
   Включите у провайдера **auto-onboarding** — иначе при первом входе будет «User not found».
   Auto-link не включайте.
   - Issuer: `https://accounts.google.com` (адреса подтянутся через discovery)
   - Scope: `openid email profile`
   - Client ID и secret из Google.

## 5. Что проверить и записать в спеку

Результаты — в «Открытые вопросы» спеки 0001. Если пункт не работает — останавливаемся и пересматриваем ADR 0009.

- [x] **Вход через Google.** http://localhost:8080/auth/v1/account → войти через Google. Пользователь появился
      в админке (Users) с вашим email.
- [ ] **Вход через GitHub**, в том числе с приватным email в GitHub. Какой email получил пользователь,
      отмечен ли он подтверждённым.
- [ ] **Создание пользователя при первом входе** при выключенной открытой регистрации
      (`[user_registration] enable = false`). Если Rauthy отказывает — попробуйте `enable = true` и запишите,
      что получилось: доступ к нашим данным всё равно ограничит allowlist в бэкенде.
- [x] **Привязка второго провайдера** — не поддерживается: один аккаунт Rauthy = один провайдер (ADR 0009).
  Админ Rauthy — отдельный служебный аккаунт (`admin@localhost`), не ваш рабочий email.
- [ ] **Discovery и регистрация клиентов.** Временно поставьте `[dynamic_clients] enable = true`
      в `docker/rauthy/config.toml`, `docker compose restart rauthy`, затем:

      ```bash
      curl -s http://localhost:8080/auth/v1/.well-known/openid-configuration | python3 -m json.tool \
        | grep -E '"(issuer|jwks_uri|userinfo_endpoint|registration_endpoint)"|signing_alg|code_challenge'
      ```

      Нужны `registration_endpoint` и `S256` в `code_challenge_methods_supported`. Верните `enable = false`.

## 6. Вход в Swagger через Rauthy

1. Админка Rauthy → Clients → добавить клиента:
   - Client ID: `atomic-tasks-swagger`, тип **public** (без секрета, confidential выключен);
   - Redirect URI: `http://localhost:8000/docs/oauth2-redirect`;
   - Allowed origin: `http://localhost:8000` — Swagger обменивает код на токен прямо из браузера;
   - Flows: `authorization_code` (+ `refresh_token`), PKCE `S256`;
   - Scopes: `openid email profile`.
2. В `.env` — блок `AUTH__*` из `.env.example`, в `AUTH__ALLOWED_EMAILS` ваш email.
3. `docker compose up -d --build api`, открыть http://localhost:8000/docs → **Authorize** → блок OAuth2 →
   отметить scopes → войти через Google.
4. `GET /api/v1/me` — при первом входе создаётся пользователь. Затем `POST /api/v1/tokens` — токен для Claude Code.

Если `/me` отвечает 401 «Токен недействителен» — проверьте `aud` и `iss` токена (скопировать из Swagger, декодировать
`python -c "import jwt,sys;print(jwt.decode(sys.argv[1],options={'verify_signature':False}))" <token>`):
`aud` должен быть в `AUTH__AUDIENCE`, `iss` — равен `AUTH__ISSUER`. Если 403 «Регистрация закрыта» —
email не в allowlist или не подтверждён.
