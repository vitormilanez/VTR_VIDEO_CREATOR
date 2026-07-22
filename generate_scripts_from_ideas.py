#!/usr/bin/env python3
"""Gera roteiros de Reels a partir da aba Ideias."""

from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass

from integrations.google_sheets_rest_client import GoogleSheetsRestClient
from integrations.portuguese_br import apply_portuguese_br_accents


IDEAS_SHEET = "Ideias"
SCRIPTS_SHEET = "Roteiros"
IDEAS_RANGE = f"'{IDEAS_SHEET}'!A:J"
SCRIPTS_RANGE = f"'{SCRIPTS_SHEET}'!A:O"
SCRIPTS_APPEND_RANGE = f"'{SCRIPTS_SHEET}'!A2:O"

SELECTABLE_STATUSES = {
    "ideia gerada",
    "aprovada",
    "aprovado",
    "aprovada para roteiro",
    "aprovado para roteiro",
}


@dataclass(frozen=True)
class SheetRow:
    index: int
    data: dict[str, str]


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


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


def first_value(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return value.strip()
    return ""


def existing_script_keys(client: GoogleSheetsRestClient) -> set[str]:
    rows = rows_to_dicts(client.get_values(SCRIPTS_RANGE))
    keys: set[str] = set()

    for row in rows:
        theme = normalize(first_value(row.data, ["Tema"]))
        hook = normalize(first_value(row.data, ["Hook"]))
        origin = normalize(first_value(row.data, ["Link origem", "Link doc/video", "Link doc/vídeo"]))
        if origin:
            keys.add(f"origin:{origin}")
        if theme and hook:
            keys.add(f"script:{theme}|{hook}")

    return keys


def idea_key(row: dict[str, str]) -> str:
    origin = normalize(first_value(row, ["Link origem", "Link referência", "Link referencia"]))
    if origin:
        return f"origin:{origin}"
    return f"script:{normalize(first_value(row, ['Tema']))}|{normalize(first_value(row, ['Hook']))}"


def is_selectable(row: SheetRow, include_pending: bool) -> bool:
    status = normalize(first_value(row.data, ["Status"]))
    if status in SELECTABLE_STATUSES:
        return True
    return include_pending and status == "pendente"


def topic_family(theme: str, angle: str, notes: str) -> str:
    text = normalize(f"{theme} {angle} {notes}")
    if any(term in text for term in ["mounjaro", "ozempic", "wegovy", "glp", "semaglutida", "tirzepatida"]):
        return "medicamento"
    if any(term in text for term in ["compuls", "fome emocional", "ansiedade", "culpa"]):
        return "comportamento"
    if any(term in text for term in ["metabolismo", "dieta", "saciedade", "apetite", "efeito sanfona"]):
        return "metabolismo"
    if "obesidade" in text:
        return "obesidade"
    return "educativo"


def category_for(family: str) -> str:
    return {
        "medicamento": "Medicamentos",
        "comportamento": "Comportamento alimentar",
        "metabolismo": "Metabolismo",
        "obesidade": "Obesidade",
    }.get(family, "Educativo")


def title_for(theme: str, hook: str, family: str) -> str:
    if family == "medicamento":
        return f"{theme or 'Tratamento'} sem promessa fácil"
    if family == "comportamento":
        return "A culpa não explica tudo"
    if family == "metabolismo":
        return "Seu corpo não é uma calculadora"
    if family == "obesidade":
        return "Obesidade precisa de cuidado, não julgamento"
    return hook[:90] if hook else f"{theme or 'Emagrecimento'} com responsabilidade"


def conflict_for(pain: str, family: str) -> str:
    if pain:
        return pain
    if family == "medicamento":
        return "Muita gente vê o medicamento como atalho e esquece que indicação depende de avaliação."
    if family == "comportamento":
        return "Muita gente se culpa quando perde o controle com a comida."
    if family == "metabolismo":
        return "A frustração aparece quando a pessoa faz esforço e não entende a resposta do corpo."
    if family == "obesidade":
        return "A pessoa ouve julgamento quando, na verdade, precisa de acompanhamento."
    return "Existe uma dúvida comum sobre emagrecimento que merece explicação simples."


def explanation_for(theme: str, angle: str, family: str) -> str:
    if family == "medicamento":
        return (
            "Medicamentos podem fazer parte do tratamento quando há indicação, mas eles não substituem "
            "diagnóstico, acompanhamento, mudança de hábitos e avaliação de riscos."
        )
    if family == "comportamento":
        return (
            "Fome, ansiedade, rotina, sono e ambiente influenciam escolhas alimentares. Por isso, cuidado "
            "de verdade começa entendendo o contexto, não atacando a pessoa."
        )
    if family == "metabolismo":
        return (
            "Peso corporal envolve gasto energético, saciedade, hormônios, massa muscular, sono e histórico "
            "de dietas. A conta é mais complexa do que apenas comer menos."
        )
    if family == "obesidade":
        return (
            "Obesidade é uma condição multifatorial. O tratamento precisa olhar biologia, comportamento, "
            "ambiente, saúde mental e histórico clínico."
        )
    if angle:
        return f"A ideia é transformar esse tema em uma explicação simples: {angle}"
    return f"O tema {theme or 'emagrecimento'} merece contexto para não virar promessa rápida."


def turn_for(family: str) -> str:
    if family == "medicamento":
        return "A pergunta não é se existe um remédio famoso, é se ele faz sentido para aquele paciente."
    if family == "comportamento":
        return "Quando a gente troca culpa por investigação, o tratamento fica mais humano e mais eficaz."
    if family == "metabolismo":
        return "O caminho melhora quando paramos de tratar o corpo como uma planilha simples."
    if family == "obesidade":
        return "Menos julgamento e mais ciência costuma ser o primeiro passo."
    return "O conteúdo bom não vende atalho; ele ajuda a pessoa a fazer uma pergunta melhor."


def medical_care_for(notes: str, family: str) -> str:
    base = "Não prescrever, não citar dose, não prometer resultado e validar a informação médica antes de publicar."
    if family == "medicamento":
        base += " Reforçar que medicamento exige indicação, acompanhamento e avaliação individual."
    if notes:
        base += f" Observações da ideia: {notes[:220]}"
    return base


def risk_for(family: str) -> str:
    if family == "medicamento":
        return "Alto"
    if family in {"metabolismo", "obesidade"}:
        return "Médio"
    return "Baixo"


def idea_to_script(row: SheetRow) -> list[str]:
    data = row.data
    theme = first_value(data, ["Tema"])
    hook = first_value(data, ["Hook"])
    angle = first_value(data, ["Ângulo", "Angulo"])
    pain = first_value(data, ["Público/Dor", "Publico/Dor", "Dor do público", "Dor do publico"])
    cta = first_value(data, ["CTA"]) or "Salve este vídeo e converse com um médico para avaliar seu caso."
    notes = first_value(data, ["Observações", "Observacoes"])
    format_type = first_value(data, ["Tipo"]) or "Reel"
    family = topic_family(theme, angle, notes)

    script_row = [
        category_for(family),
        theme,
        title_for(theme, hook, family),
        hook or title_for(theme, hook, family),
        conflict_for(pain, family),
        explanation_for(theme, angle, family),
        turn_for(family),
        cta,
        medical_care_for(notes, family),
        risk_for(family),
        "Avatar médico falando" if normalize(format_type) == "reel" else format_type,
        "Aguardando validação médica",
        "Dr. Guilherme",
        "",
        first_value(data, ["Link origem", "Link referência", "Link referencia"]),
    ]
    return [apply_portuguese_br_accents(value) for value in script_row]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera roteiros de Reels a partir da aba Ideias.")
    parser.add_argument("--limit", type=int, default=10, help="Quantidade maxima de roteiros.")
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Tambem processa ideias com status Pendente.",
    )
    parser.add_argument(
        "--no-status-update",
        action="store_true",
        help="Nao marca ideias processadas como Roteiro gerado.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = GoogleSheetsRestClient()
    ideas = rows_to_dicts(client.get_values(IDEAS_RANGE))
    seen = existing_script_keys(client)

    script_rows: list[list[str]] = []
    processed_rows: list[int] = []

    for idea in ideas:
        if not is_selectable(idea, include_pending=args.include_pending):
            continue

        key = idea_key(idea.data)
        if key in seen:
            continue

        script_rows.append(idea_to_script(idea))
        processed_rows.append(idea.index)
        seen.add(key)

        if len(script_rows) >= args.limit:
            break

    if not script_rows:
        print("Nenhum roteiro novo para gerar.")
        return 0

    client.append_rows(SCRIPTS_APPEND_RANGE, script_rows)

    if not args.no_status_update:
        for row_index in processed_rows:
            client.update_values(f"'{IDEAS_SHEET}'!H{row_index}:H{row_index}", [["Roteiro gerado"]])

    print(f"Roteiros gerados na aba '{SCRIPTS_SHEET}': {len(script_rows)}")
    print(f"Linhas de Ideias processadas: {', '.join(str(index) for index in processed_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
