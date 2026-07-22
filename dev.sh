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

# --- API Python ---
if [ ! -d "$ROOT/.venv" ]; then
  echo "Criando venv e instalando deps da API..."
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/api/requirements.txt"
fi
echo "Iniciando API em http://127.0.0.1:8000 ..."
"$ROOT/.venv/bin/python" -m uvicorn api.server:app --reload --port 8000 &
API_PID=$!

# --- Frontend ---
if [ ! -d "$ROOT/web/node_modules" ]; then
  echo "Instalando deps do frontend..."
  (cd "$ROOT/web" && npm install --no-audit --no-fund)
fi
echo "Iniciando frontend em http://localhost:8080 ..."
(cd "$ROOT/web" && npm run dev) &
WEB_PID=$!

trap 'echo; echo "Parando..."; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM
wait
