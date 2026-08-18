#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PG_DATA_DIR="${LOCAL_POSTGRES_DATA_DIR:-$PROJECT_ROOT/.local-postgres/data}"
PG_LOG_FILE="${LOCAL_POSTGRES_LOG_FILE:-$PROJECT_ROOT/.local-postgres/postgres.log}"
PG_PORT="${LOCAL_POSTGRES_PORT:-55432}"
PG_USER="${LOCAL_POSTGRES_USER:-$(id -un)}"
PG_DATABASE="${LOCAL_POSTGRES_DATABASE:-ai_video_creator}"

initialize() {
  if [ -f "$PG_DATA_DIR/PG_VERSION" ]; then
    return
  fi
  mkdir -p "$(dirname "$PG_DATA_DIR")"
  initdb -D "$PG_DATA_DIR" -U "$PG_USER" --auth=trust --encoding=UTF8 --locale=C
}

start() {
  initialize
  if ! pg_ctl -D "$PG_DATA_DIR" status >/dev/null 2>&1; then
    pg_ctl -D "$PG_DATA_DIR" -l "$PG_LOG_FILE" -o "-p $PG_PORT -h 127.0.0.1" -w start
  fi
  if ! psql -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$PG_DATABASE'" | grep -q '^1$'; then
    createdb -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" "$PG_DATABASE"
  fi
  pg_isready -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE"
}

stop() {
  if [ -f "$PG_DATA_DIR/PG_VERSION" ] && pg_ctl -D "$PG_DATA_DIR" status >/dev/null 2>&1; then
    pg_ctl -D "$PG_DATA_DIR" -m fast -w stop
  else
    echo "PostgreSQL local já está parado."
  fi
}

status() {
  if [ -f "$PG_DATA_DIR/PG_VERSION" ] && pg_ctl -D "$PG_DATA_DIR" status >/dev/null 2>&1; then
    pg_isready -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE"
  else
    echo "PostgreSQL local parado."
    return 1
  fi
}

case "${1:-status}" in
  init) initialize ;;
  start) start ;;
  stop) stop ;;
  status) status ;;
  *)
    echo "Uso: $0 {init|start|stop|status}" >&2
    exit 2
    ;;
esac
