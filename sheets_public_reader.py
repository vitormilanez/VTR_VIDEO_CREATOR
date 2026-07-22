#!/usr/bin/env python3
"""
Le abas publicas do Google Sheets via export CSV.

Uso:
    python sheets_public_reader.py
    python sheets_public_reader.py --gid 1596729829 --output output/radar.csv

Requisito: a planilha precisa estar como "qualquer pessoa com o link pode visualizar".
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from urllib.parse import urlencode

import requests


DEFAULT_SPREADSHEET_ID = "1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ"
DEFAULT_GID = "1596729829"


def build_csv_url(spreadsheet_id: str, gid: str) -> str:
    query = urlencode({"format": "csv", "gid": gid})
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?{query}"


def read_public_sheet(spreadsheet_id: str, gid: str) -> list[dict[str, str]]:
    url = build_csv_url(spreadsheet_id, gid)
    response = requests.get(url, timeout=30)
    if response.status_code in {401, 403}:
        raise RuntimeError(
            "A planilha nao esta acessivel publicamente. No Google Sheets, clique em "
            "Compartilhar > Acesso geral > Qualquer pessoa com o link > Leitor."
        )
    response.raise_for_status()

    text = response.text
    if "<html" in text[:500].lower() or "ServiceLogin" in text:
        raise RuntimeError(
            "A planilha nao parece estar publica. Configure como "
            "'qualquer pessoa com o link pode visualizar'."
        )

    rows = list(csv.DictReader(text.splitlines()))
    return [
        {key.strip(): (value or "").strip() for key, value in row.items() if key}
        for row in rows
        if any((value or "").strip() for value in row.values())
    ]


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Le Google Sheets publico via CSV.")
    parser.add_argument(
        "--spreadsheet-id",
        default=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
        help="ID da planilha Google Sheets.",
    )
    parser.add_argument(
        "--gid",
        default=os.getenv("GOOGLE_SHEETS_GID", DEFAULT_GID),
        help="GID da aba.",
    )
    parser.add_argument(
        "--output",
        default="output/google_sheet_export.csv",
        help="Arquivo CSV local de saida.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_public_sheet(args.spreadsheet_id, args.gid)
    output_path = Path(args.output)
    write_csv(rows, output_path)

    print(f"Linhas lidas: {len(rows)}")
    print(f"Arquivo gerado: {output_path.resolve()}")
    if rows:
        print("Colunas:")
        for column in rows[0].keys():
            print(f"- {column}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
