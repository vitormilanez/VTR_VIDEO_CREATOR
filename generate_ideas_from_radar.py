#!/usr/bin/env python3
"""Gera ideias de Reels a partir da aba Radar Tendencias."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from integrations.google_sheets_client import GoogleSheetsClient


RADAR_SHEET = "Radar Tendencias"
IDEAS_SHEET = "Ideias"
RADAR_RANGE = f"'{RADAR_SHEET}'!A:K"
IDEAS_RANGE = f"'{IDEAS_SHEET}'!A:J"
IDEAS_APPEND_RANGE = f"'{IDEAS_SHEET}'!A2:J"


@dataclass(frozen=True)
class SheetRow:
    index: int
    data: dict[str, str]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def rows_to_dicts(values: list[list[str]]) -> list[SheetRow]:
    if not values:
        return []

    headers = [str(header).strip() for header in values[0]]
    rows = []
    for offset, row in enumerate(values[1:], start=2):
        data = {
            header: str(row[index]).strip() if index < len(row) else ""
            for index, header in enumerate(headers)
            if header
        }
        if any(data.values()):
            rows.append(SheetRow(index=offset, data=data))
    return rows


def existing_idea_keys(client: GoogleSheetsClient) -> set[str]:
    values = client.get_values(IDEAS_RANGE)
    rows = rows_to_dicts(values)
    keys = set()

    for row in rows:
        theme = normalize(row.data.get("Tema", ""))
        hook = normalize(row.data.get("Hook", ""))
        origin = normalize(row.data.get("Link origem", ""))
        if origin:
            keys.add(f"origin:{origin}")
        if theme and hook:
            keys.add(f"idea:{theme}|{hook}")

    return keys


def is_selectable(row: SheetRow, include_media: bool) -> bool:
    status = normalize(row.data.get("Status", ""))
    priority = normalize(row.data.get("Prioridade", ""))

    if status not in {"pendente", "em pesquisa"}:
        return False
    if priority == "alta":
        return True
    return include_media and priority in {"media", "medio", "média", "médio"}


def topic_family(theme: str, signal: str) -> str:
    text = normalize(f"{theme} {signal}")
    if any(term in text for term in ["mounjaro", "ozempic", "wegovy", "glp", "semaglutida", "tirzepatida"]):
        return "medicamento"
    if any(term in text for term in ["compuls", "fome emocional", "ansiedade"]):
        return "comportamento"
    if any(term in text for term in ["dieta", "jejum", "metabolismo", "balanca", "bioimpedancia"]):
        return "metabolismo"
    if "obesidade" in text:
        return "obesidade"
    return "educativo"


def make_hook(theme: str, signal: str, pain: str) -> str:
    family = topic_family(theme, signal)
    clean_theme = theme or "emagrecimento"

    if family == "medicamento":
        return f"{clean_theme}: noticia nova ou atalho perigoso?"
    if family == "comportamento":
        return "E se o problema nao for falta de vergonha?"
    if family == "metabolismo":
        return "Seu corpo nao e uma calculadora simples."
    if family == "obesidade":
        return "Obesidade nao se resolve com julgamento."
    if pain:
        return "Essa duvida sobre emagrecimento aparece toda semana."
    return f"O que essa tendencia sobre {clean_theme} realmente significa?"


def make_angle(theme: str, signal: str) -> str:
    family = topic_family(theme, signal)
    if family == "medicamento":
        return "Educativo/provocativo sobre tratamento, indicacao medica e limites dos medicamentos."
    if family == "comportamento":
        return "Acolhedor, com quebra de culpa e explicacao simples do comportamento alimentar."
    if family == "metabolismo":
        return "Explicativo, traduzindo metabolismo em exemplos do dia a dia."
    if family == "obesidade":
        return "Reposicionar obesidade como condicao multifatorial, sem culpa e sem promessa facil."
    return "Transformar a tendencia em conteudo educativo simples, responsavel e compartilhavel."


def make_cta(theme: str, signal: str) -> str:
    family = topic_family(theme, signal)
    if family == "medicamento":
        return "Comente 'avaliacao' se voce quer entender quando faz sentido investigar tratamento."
    if family == "comportamento":
        return "Salve para rever quando a culpa aparecer."
    if family == "metabolismo":
        return "Comente 'metabolismo' se voce quer uma explicacao mais simples."
    return "Envie para alguem que precisa ouvir isso sem culpa."


def make_audience_pain(row: dict[str, str]) -> str:
    pain = row.get("Dor do publico") or row.get("Dor do público")
    if pain:
        return pain
    return "Pessoas interessadas em emagrecimento, obesidade e saude metabolica."


def make_observations(row: dict[str, str]) -> str:
    signal = row.get("Sinal de tendencia") or row.get("Sinal de tendência")
    notes = [
        "Validar informacao medica antes de gravar.",
        "Nao citar dose, nao prometer resultado e nao prescrever.",
    ]
    if signal:
        notes.append(f"Origem: {signal[:180]}")
    return " ".join(notes)


def radar_to_idea(row: SheetRow) -> list[str]:
    data = row.data
    theme = data.get("Tema", "")
    signal = data.get("Sinal de tendencia") or data.get("Sinal de tendência", "")
    pain = make_audience_pain(data)

    return [
        theme,
        make_hook(theme, signal, pain),
        make_angle(theme, signal),
        "Reel",
        pain,
        make_cta(theme, signal),
        data.get("Prioridade", "Media"),
        "Ideia gerada",
        data.get("Link referencia") or data.get("Link referência", ""),
        make_observations(data),
    ]


def idea_key(row: list[str]) -> str:
    origin = normalize(row[8])
    if origin:
        return f"origin:{origin}"
    return f"idea:{normalize(row[0])}|{normalize(row[1])}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera ideias de Reels a partir do Radar Tendencias.")
    parser.add_argument("--limit", type=int, default=10, help="Quantidade maxima de ideias.")
    parser.add_argument(
        "--include-media",
        action="store_true",
        help="Tambem processa tendencias de prioridade Media.",
    )
    parser.add_argument(
        "--no-status-update",
        action="store_true",
        help="Nao marca linhas do Radar como Ideia gerada.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = GoogleSheetsClient()

    radar_rows = rows_to_dicts(client.get_values(RADAR_RANGE))
    seen = existing_idea_keys(client)

    ideas: list[list[str]] = []
    processed_rows: list[int] = []

    for radar_row in radar_rows:
        if not is_selectable(radar_row, include_media=args.include_media):
            continue

        idea = radar_to_idea(radar_row)
        key = idea_key(idea)
        if key in seen:
            continue

        ideas.append(idea)
        processed_rows.append(radar_row.index)
        seen.add(key)

        if len(ideas) >= args.limit:
            break

    if not ideas:
        print("Nenhuma ideia nova para gerar.")
        return 0

    client.append_rows(IDEAS_APPEND_RANGE, ideas)

    if not args.no_status_update:
        for row_index in processed_rows:
            client.update_values(f"'{RADAR_SHEET}'!J{row_index}:J{row_index}", [["Ideia gerada"]])

    print(f"Ideias geradas na aba '{IDEAS_SHEET}': {len(ideas)}")
    print(f"Linhas do Radar processadas: {', '.join(str(index) for index in processed_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
