#!/usr/bin/env bash
# Publica o frontend local por um Quick Tunnel HTTPS, sempre atras do Caddy
# com autenticacao HTTP Basic. A URL muda a cada reinicio do tunel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CADDYFILE="$ROOT/.online/Caddyfile"
CADDY_PID=""

for command_name in caddy cloudflared curl lsof; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando ausente: $command_name" >&2
    exit 1
  fi
done

if [ ! -f "$CADDYFILE" ]; then
  echo "Configuracao ausente: $CADDYFILE" >&2
  exit 1
fi

if ! lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "O frontend nao esta ativo em 127.0.0.1:8080. Inicie ./dev.sh primeiro." >&2
  exit 1
fi

caddy validate --config "$CADDYFILE" --adapter caddyfile
caddy run --config "$CADDYFILE" --adapter caddyfile &
CADDY_PID=$!

cleanup() {
  if [ -n "$CADDY_PID" ]; then
    kill "$CADDY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

gateway_ready="false"
for _attempt in {1..30}; do
  gateway_status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8081/ || true)"
  if [ "$gateway_status" = "401" ]; then
    gateway_ready="true"
    break
  fi
  sleep 0.2
done

if [ "$gateway_ready" != "true" ]; then
  echo "O gateway protegido nao respondeu em 127.0.0.1:8081." >&2
  exit 1
fi

echo "Gateway protegido ativo. Criando URL HTTPS gratuita..."
cloudflared tunnel --url http://127.0.0.1:8081 --no-autoupdate
