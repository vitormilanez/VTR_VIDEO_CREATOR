"""Contrato do Claude para transformar um roteiro em diálogo educativo.

Este módulo não persiste dados e não chama provedores. Ele concentra o prompt,
o schema e a validação determinística da conversa devolvida pelo modelo.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping


PODCAST_DIALOGUE_PROMPT_VERSION = "2026-08-17-v1-educational-dialogue"

PODCAST_DIALOGUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speakerId": {"type": "string", "enum": ["a", "b"]},
                    "text": {"type": "string"},
                },
                "required": ["speakerId", "text"],
            },
        },
    },
    "required": ["title", "turns"],
}


def dialogue_turn_bounds(duration_seconds: int) -> tuple[int, int]:
    """Quantidade de falas suficiente para ritmo de pergunta e resposta."""

    if duration_seconds <= 30:
        return 4, 8
    if duration_seconds <= 45:
        return 6, 10
    if duration_seconds <= 60:
        return 8, 14
    if duration_seconds <= 90:
        return 10, 18
    if duration_seconds <= 120:
        return 12, 22
    return 16, 30


def build_podcast_dialogue_prompt(
    *,
    source: Mapping[str, Any],
    host_name: str,
    guest_name: str,
    duration_seconds: int,
    direction: str = "",
) -> tuple[str, str]:
    minimum_turns, maximum_turns = dialogue_turn_bounds(duration_seconds)
    system = f"""Você é um roteirista de podcast médico educativo em português brasileiro.
Transforme o material fornecido em uma conversa natural entre HOST e GUEST.

Papéis:
- HOST (speakerId \"a\", nome {host_name}): representa a dúvida de uma pessoa leiga. Faz perguntas curtas, úteis e fáceis de acompanhar.
- GUEST (speakerId \"b\", nome {guest_name}): explica como especialista, com frases faláveis, linguagem simples e tom responsável.

Regras obrigatórias:
- Comece com HOST, alterne rigorosamente HOST e GUEST e termine com GUEST.
- Retorne entre {minimum_turns} e {maximum_turns} falas para aproximadamente {duration_seconds} segundos.
- Cada fala deve conter uma ideia. Evite respostas longas, aula técnica, repetição e introduções genéricas.
- Use somente fatos, números, ressalvas e contexto presentes no MATERIAL_FONTE. Nunca invente estudo, percentual, eficácia, risco, diagnóstico, causalidade ou experiência clínica.
- Preserve incerteza e limitações. Não transforme resultado preliminar em aprovação, comparação direta, cura ou recomendação individual.
- Não prescreva, não cite dose e não incentive compra ou uso de produto sem aprovação e acompanhamento profissional.
- Explique termos técnicos em linguagem cotidiana quando forem indispensáveis.
- Não inclua os rótulos HOST ou GUEST dentro de text. Não escreva direção de cena, emoção, legenda ou observação editorial.
- Retorne somente JSON compatível com o schema solicitado.

VERSÃO DO PROMPT: {PODCAST_DIALOGUE_PROMPT_VERSION}"""
    user_payload = {
        "MATERIAL_FONTE": dict(source),
        "DURACAO_SEGUNDOS": duration_seconds,
        "ORIENTACAO_OPCIONAL": direction.strip() or "Nenhuma orientação adicional.",
        "SAIDA": {
            "title": "Título curto para a conversa",
            "turns": [
                {"speakerId": "a", "text": "Pergunta curta do HOST"},
                {"speakerId": "b", "text": "Resposta educativa do GUEST"},
            ],
        },
    }
    return system, json.dumps(user_payload, ensure_ascii=False, indent=2)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_podcast_dialogue(
    parsed: Mapping[str, Any],
    *,
    duration_seconds: int,
) -> dict[str, Any]:
    """Valida estrutura, alternância e limites antes de exibir o rascunho."""

    if not isinstance(parsed, Mapping):
        raise ValueError("Claude não retornou uma conversa estruturada.")
    title = _clean_text(parsed.get("title"))
    if not title:
        raise ValueError("Claude não retornou um título para a conversa.")

    raw_turns = parsed.get("turns")
    if not isinstance(raw_turns, list):
        raise ValueError("Claude não retornou a lista de falas.")
    minimum_turns, maximum_turns = dialogue_turn_bounds(duration_seconds)
    if not minimum_turns <= len(raw_turns) <= maximum_turns:
        raise ValueError(
            f"Claude retornou {len(raw_turns)} falas; esperado para esta duração: "
            f"{minimum_turns}–{maximum_turns}."
        )

    turns: list[dict[str, str]] = []
    expected_speaker = "a"
    for index, item in enumerate(raw_turns, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"A fala {index} não veio estruturada corretamente.")
        speaker_id = _clean_text(item.get("speakerId")).casefold()
        text = _clean_text(item.get("text"))
        if speaker_id != expected_speaker:
            expected_label = "HOST" if expected_speaker == "a" else "GUEST"
            raise ValueError(f"A fala {index} deveria ser do {expected_label}.")
        if not text:
            raise ValueError(f"A fala {index} está vazia.")
        if len(text) > 1200:
            raise ValueError(f"A fala {index} ultrapassa 1.200 caracteres.")
        if re.match(r"^(?:HOST|GUEST)\s*:", text, re.IGNORECASE):
            raise ValueError(f"A fala {index} contém um rótulo HOST/GUEST dentro do texto.")
        turns.append({"speakerId": speaker_id, "text": text})
        expected_speaker = "b" if expected_speaker == "a" else "a"

    if turns[-1]["speakerId"] != "b":
        raise ValueError("A conversa precisa terminar com uma resposta do GUEST.")
    return {"title": title[:240], "turns": turns}
