#!/usr/bin/env python3
"""Envia tendencias do CSV mais recente para a aba Radar Tendencias."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from integrations.google_sheets_rest_client import GoogleSheetsRestClient
from integrations.portuguese_br import apply_portuguese_br_accents


ROOT_DIR = Path(__file__).resolve().parent
TRENDS_OUTPUT_DIR = ROOT_DIR / "trend_hunter" / "output"
RADAR_SHEET = "Radar Tendencias"
RADAR_RANGE = f"'{RADAR_SHEET}'!A:K"
RADAR_APPEND_RANGE = f"'{RADAR_SHEET}'!A2:K"


def latest_trends_csv() -> Path:
    files = sorted(TRENDS_OUTPUT_DIR.glob("trends_*.csv"), reverse=True)
    if not files:
        raise RuntimeError(f"Nenhum CSV encontrado em {TRENDS_OUTPUT_DIR}")
    return files[0]


def read_trends(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def priority_from_score(score: int) -> str:
    if score >= 55:
        return "Alta"
    if score >= 40:
        return "Media"
    return "Baixa"


def public_pain_from_terms(terms: str) -> str:
    normalized = terms.lower()
    if any(term in normalized for term in ["mounjaro", "ozempic", "wegovy", "semaglutida", "tirzepatida", "glp"]):
        return "Dúvida sobre medicamentos, segurança e indicação correta."
    if "compuls" in normalized:
        return "Culpa e perda de controle com a alimentação."
    if "dieta" in normalized:
        return "Cansaço de dietas restritivas e medo do efeito sanfona."
    if "obesidade" in normalized:
        return "Sentir que emagrecimento depende só de força de vontade."
    return "Dúvida sobre emagrecimento, metabolismo e saúde."


def public_pain_from_row(row: dict[str, str]) -> str:
    source_type = row.get("tipo", "")
    if "Dúvida" in source_type:
        return "Dúvida real do público, boa para conteúdo de esclarecimento."
    if "Estudo" in source_type:
        return "Curiosidade sobre estudo novo; precisa de tradução simples e cautelosa."
    return public_pain_from_terms(row.get("termos_encontrados", ""))


def theme_from_trend(row: dict[str, str]) -> str:
    terms = [term.strip() for term in row.get("termos_encontrados", "").split(",") if term.strip()]
    if terms:
        return terms[0].upper() if terms[0].lower() == "glp-1" else terms[0].title()
    title = row.get("trend", "")
    return title.split(" - ")[0][:80]


def subtheme_from_trend(row: dict[str, str]) -> str:
    title = row.get("trend", "")
    return title.split(" - ")[0][:120]


def existing_keys(client: GoogleSheetsRestClient) -> set[str]:
    values = client.get_values(RADAR_RANGE)
    if len(values) <= 1:
        return set()

    keys = set()
    for row in values[1:]:
        # Link referencia = coluna F (idx 5); Sinal de tendencia = coluna G (idx 6)
        link = row[5].strip() if len(row) > 5 else ""
        signal = row[6].strip() if len(row) > 6 else ""
        if link or signal:
            keys.add(f"{link}|{signal}")
    return keys


def trend_to_radar_row(row: dict[str, str]) -> list[object]:
    score = int(float(row.get("score") or 0))
    link = row.get("link_da_fonte", "")
    signal = row.get("trend", "")
    # Ordem DEVE bater com o cabecalho real da aba 'Radar Tendencias':
    # Data | Potencial Viral | Tema | Subtema | Fonte | Link referencia |
    # Sinal de tendencia | Dor do publico | Prioridade | Status | Observacoes
    sheet_row = [
        datetime.now().date().isoformat(),
        min(10, max(1, round(score / 7))),
        theme_from_trend(row),
        subtheme_from_trend(row),
        row.get("fonte", "Trend Hunter"),
        link,
        signal,
        public_pain_from_row(row),
        priority_from_score(score),
        "Pendente",
        (
            f"Tipo: {row.get('tipo', 'Tendência')}. Score {score}. "
            f"{row.get('angulo_de_conteudo', '')} "
            f"{row.get('cuidado_medico_compliance', '')}"
        ).strip(),
    ]
    return [apply_portuguese_br_accents(value) if isinstance(value, str) else value for value in sheet_row]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sincroniza Trend Hunter com Google Sheets.")
    parser.add_argument("--csv", type=Path, default=None, help="CSV de tendencias. Padrao: mais recente.")
    parser.add_argument("--limit", type=int, default=20, help="Quantidade maxima de tendencias para enviar.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv or latest_trends_csv()
    trends = read_trends(csv_path)
    trends = sorted(trends, key=lambda row: int(float(row.get("score") or 0)), reverse=True)

    client = GoogleSheetsRestClient()
    seen = existing_keys(client)

    rows = []
    for trend in trends:
        sheet_row = trend_to_radar_row(trend)
        key = f"{sheet_row[5]}|{sheet_row[6]}"
        if key in seen:
            continue
        rows.append(sheet_row)
        if len(rows) >= args.limit:
            break

    if not rows:
        print("Nenhuma tendencia nova para enviar.")
        return 0

    client.append_rows(RADAR_APPEND_RANGE, rows)
    print(f"CSV usado: {csv_path}")
    print(f"Tendencias enviadas para '{RADAR_SHEET}': {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
