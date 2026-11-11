#!/usr/bin/env bash
# Ежедневный бэкап обеих баз (спека 0006): cron пользователя деплоя, см. docs/deploy.md.
# Дампы pg_dump -Fc в $BACKUP_DIR/<YYYY-MM-DD>/, хранятся 7 дней.
set -euo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/var/backups/atomic-tasks}"
KEEP_DAYS="${KEEP_DAYS:-7}"
STACK_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

cd "$STACK_DIR"
# compose.yaml требует VERSION — берём выкаченную
VERSION="$(cat .deployed-version)"
export VERSION

dest="$BACKUP_DIR/$(date +%F)"
mkdir -p "$dest"

for db in atomic_tasks rauthy; do
  # Суперпользователь стека читает обе базы; имя пользователя — из окружения контейнера
  docker compose exec -T postgres sh -c "pg_dump -Fc -U \"\$POSTGRES_USER\" -d $db" > "$dest/$db.dump.part"
  mv "$dest/$db.dump.part" "$dest/$db.dump"
done
echo "backup: $dest"

# Ротация: только каталоги-даты, ничего другого в BACKUP_DIR не трогаем
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '????-??-??' -mtime +"$((KEEP_DAYS - 1))" \
  -exec rm -rf {} +
