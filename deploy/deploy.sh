#!/usr/bin/env bash
# Выкатка версии X.Y.Z (спека 0006, ADR 0011). Запуск:
#   ./deploy.sh 0.2.0                — руками на сервере
#   ssh deploy@host 0.2.0            — из CI; здесь это forced command, версия приходит в SSH_ORIGINAL_COMMAND
# Скачивает конфиг стека из GitHub Release этой версии, тянет образ, применяет миграции, перезапускает API
# и ждёт, пока API отдаст новую версию. Если миграции упали — API не трогается.
set -euo pipefail
umask 077

REPO="${DEPLOY_REPO:-atomic-tasks/backend}"
STACK_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

die() { echo "deploy: $*" >&2; exit 1; }

version="${1:-${SSH_ORIGINAL_COMMAND:-}}"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] \
  || die "ожидается версия вида X.Y.Z"

cd "$STACK_DIR"
[[ -f .env ]] || die "нет $STACK_DIR/.env — см. docs/deploy.md"

exec 9>.deploy.lock
flock -n 9 || die "уже идёт другая выкатка"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "deploy: $version — конфиг стека из релиза v$version"
curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$tmp/deploy.tar.gz" \
  "https://github.com/$REPO/releases/download/v$version/deploy.tar.gz"
mkdir "$tmp/bundle"
tar -xzf "$tmp/deploy.tar.gz" -C "$tmp/bundle" --no-same-owner --no-same-permissions

for f in compose.yaml backup.sh rauthy/config.toml docker/postgres/init/01-rauthy.sh; do
  [[ -f "$tmp/bundle/$f" ]] || die "в бандле нет $f"
done
mkdir -p rauthy docker/postgres/init
install -m 644 "$tmp/bundle/compose.yaml" compose.yaml
install -m 644 "$tmp/bundle/rauthy/config.toml" rauthy/config.toml
install -m 755 "$tmp/bundle/docker/postgres/init/01-rauthy.sh" docker/postgres/init/01-rauthy.sh
install -m 755 "$tmp/bundle/backup.sh" backup.sh
# Сам скрипт — forced command; заменяется только руками (docs/deploy.md).
if ! cmp -s "$tmp/bundle/deploy.sh" deploy.sh; then
  install -m 644 "$tmp/bundle/deploy.sh" deploy.sh.new
  echo "deploy: ВНИМАНИЕ — в релизе новая версия deploy.sh, лежит в deploy.sh.new"
fi

export VERSION="$version"

echo "deploy: pull образов"
docker compose pull --quiet

echo "deploy: миграции"
docker compose run --rm migrate || die "миграции упали — API остался на прежней версии"

echo "deploy: перезапуск"
docker compose up -d --remove-orphans

echo "deploy: проверка версии"
check='import json,urllib.request as u;print(json.load(u.urlopen("http://localhost:8000/openapi.json"))["info"]["version"])'
for _ in $(seq 30); do
  running="$(docker compose exec -T api python -c "$check" 2>/dev/null || true)"
  if [[ "$running" == "$version" ]]; then
    echo "$version" > .deployed-version
    echo "deploy: $version работает"
    exit 0
  fi
  sleep 2
done
docker compose logs --tail 50 api >&2
die "API не отдал версию $version за 60 с"
