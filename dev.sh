#!/usr/bin/env bash
# Sobe backend (API FastAPI) + frontend (Vite) juntos para desenvolvimento local.
# Uso: ./dev.sh   (Ctrl+C para parar os dois)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Vite 8 exige Node >= 20.19. Usa node@22 do Homebrew se o node padrao for antigo.
if [ -d /opt/homebrew/opt/node@22/bin ]; then
  export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
elif [ -d /usr/local/opt/node@22/bin ]; then
  export PATH="/usr/local/opt/node@22/bin:$PATH"
fi
echo "node: $(node --version)"

# --- PostgreSQL local ---
# Lê somente as duas chaves necessárias, sem executar o arquivo de ambiente.
if [ -f "$ROOT/.env.database" ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      DATA_BACKEND|DATABASE_URL) export "$key=$value" ;;
    esac
  done < "$ROOT/.env.database"
fi
if [ "${DATA_BACKEND:-sheets}" = "postgres" ]; then
  echo "Iniciando PostgreSQL local..."
  "$ROOT/tools/local_postgres.sh" start
fi

# --- API Python ---
if [ ! -d "$ROOT/.venv" ]; then
  echo "Criando venv e instalando deps da API..."
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/api/requirements.txt"
fi
if [ "${DATA_BACKEND:-sheets}" = "postgres" ]; then
  echo "Aplicando migrations..."
  "$ROOT/.venv/bin/alembic" upgrade head
fi
echo "Iniciando API em http://127.0.0.1:8000 ..."
"$ROOT/.venv/bin/python" -m uvicorn api.server:app \
  --reload \
  --reload-dir "$ROOT/api" \
  --reload-dir "$ROOT/integrations" \
  --port 8000 &
API_PID=$!

# --- Frontend ---
if [ ! -d "$ROOT/web/node_modules" ]; then
  echo "Instalando deps do frontend..."
  (cd "$ROOT/web" && npm install --no-audit --no-fund)
fi
echo "Iniciando frontend em http://localhost:8080 ..."
(cd "$ROOT/web" && npm run dev -- --force --host 127.0.0.1) &
WEB_PID=$!

trap 'echo; echo "Parando..."; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM
wait
