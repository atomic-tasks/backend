#!/bin/sh
# Выполняется один раз при создании тома Postgres: отдельная роль и база для Rauthy.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE rauthy LOGIN PASSWORD '${RAUTHY_DB_PASSWORD}';
CREATE DATABASE rauthy OWNER rauthy;
SQL
