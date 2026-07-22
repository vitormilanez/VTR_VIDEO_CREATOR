#!/usr/bin/env python3
"""Salva um snapshot local das abas principais do Google Sheets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dashboard.app import SHEETS, rows_to_dicts
from integrations.google_sheets_rest_client import GoogleSheetsRestClient


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "data" / "sheets_snapshot.json"


def build_snapshot() -> dict[str, Any]:
    client = GoogleSheetsRestClient()
    sheets = {
        name: rows_to_dicts(client.get_values(range_name))
        for name, range_name in SHEETS.items()
    }
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "google_sheets",
        "sheets": sheets,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sincroniza Google Sheets para snapshot local.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Snapshot gerado: {args.output}")
    for name, rows in snapshot["sheets"].items():
        print(f"- {name}: {len(rows)} linhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
