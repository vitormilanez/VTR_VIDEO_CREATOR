#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cuts_python="${CUTS_BOOTSTRAP_PYTHON:-python3.12}"
cuts_env="$project_root/.venv-cuts"

if ! command -v "$cuts_python" >/dev/null 2>&1; then
  echo "Python 3.12 não encontrado. Instale-o ou defina CUTS_BOOTSTRAP_PYTHON." >&2
  exit 1
fi

if [[ ! -x "$cuts_env/bin/python" ]]; then
  "$cuts_python" -m venv "$cuts_env"
fi

"$cuts_env/bin/python" -m pip install --upgrade pip
"$cuts_env/bin/python" -m pip install -r "$project_root/api/requirements-cuts.txt"
"$cuts_env/bin/python" -c "from faster_whisper import WhisperModel; print('Ambiente de cortes pronto.')"
