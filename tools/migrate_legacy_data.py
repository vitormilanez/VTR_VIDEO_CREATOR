#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from api.services.data_backend import close_data_backend, content_repository
from api.services.legacy_import import load_and_normalize_snapshot


ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa o snapshot legado para PostgreSQL de forma idempotente."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "data" / "sheets_snapshot.json",
        help="Snapshot JSON a importar.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Somente valida e mostra o relatório.")
    mode.add_argument("--apply", action="store_true", help="Aplica a importação em uma transação.")
    parser.add_argument("--organization", help="UUID da organização de destino.")
    parser.add_argument("--source", default="sheets_snapshot", help="Identificador da fonte legada.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env(ROOT / ".env")
    _load_env(ROOT / ".env.database")
    state, report = load_and_normalize_snapshot(args.snapshot)
    if args.dry_run:
        print(json.dumps({"ok": True, "mode": "dry-run", **report}, ensure_ascii=False, indent=2))
        return 0

    os.environ["DATA_BACKEND"] = "postgres"
    if args.organization:
        os.environ["DEFAULT_ORGANIZATION_ID"] = args.organization
    try:
        result = content_repository().import_legacy_state(state, source=args.source)
        print(
            json.dumps(
                {"mode": "apply", "normalization": report, "import": result},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        close_data_backend()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
