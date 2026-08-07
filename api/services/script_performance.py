from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from integrations.portuguese_br import prepare_script_for_heygen_voice


SpeechMode = Literal["natural", "direto", "enfatico", "fiel"]
CtaMode = Literal["auto", "manual", "none", "visual"]

VARIABLE_CTAS = [
    "Me siga para acompanhar mais conteúdos como este.",
    "Quer entender melhor seu corpo? Me acompanhe por aqui.",
    "Salva este vídeo porque você vai precisar lembrar disso.",
    "Antes de começar qualquer tratamento, converse com seu médico.",
    "Se esse conteúdo fez sentido, me acompanha para ver os próximos.",
]

LEGACY_OUTRO = "Me siga para mais dicas, e obrigado."

SPEECH_PRESETS: dict[str, dict[str, Any]] = {
    "natural": {"speed": 0.96, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "direto": {"speed": 1.0, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "enfatico": {"speed": 0.98, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "fiel": {"speed": 1.0, "pitch": 0, "volume": 1, "locale": "pt-BR"},
}


PERFORMANCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "spokenText": {"type": "string"},
        "displayText": {"type": "string"},
        "tone": {"type": "string"},
        "pace": {"type": "string"},
        "emotion": {"type": "string"},
        "emphasisWords": {"type": "array", "items": {"type": "string"}},
        "pauseAfterSentencesMs": {"type": "array", "items": {"type": "integer"}},
        "recommendedVoiceSpeed": {"type": "number"},
        "recommendedSpeechMode": {"type": "string"},
        "cta": {"type": "string"},
    },
    "required": [
        "spokenText",
        "displayText",
        "tone",
        "pace",
        "emotion",
        "emphasisWords",
        "pauseAfterSentencesMs",
        "recommendedVoiceSpeed",
        "recommendedSpeechMode",
        "cta",
    ],
}


def duration_word_limits(duration_seconds: int) -> tuple[int, int]:
    return {
        10: (18, 24),
        15: (25, 36),
        30: (55, 72),
        45: (85, 108),
        60: (115, 144),
    }.get(duration_seconds, (85, 108))


def video_agent_word_limits(duration_seconds: int) -> tuple[int, int]:
    """Faixa conservadora para o Video Agent.

    O Agent adiciona pausas, cortes e interacoes visuais. Por isso a mesma
    quantidade de palavras usada na geracao direta costuma produzir um video
    mais longo. Esta faixa deixa espaco para essa edicao sem adicionar nenhuma
    instrucao extra ao prompt enviado ao HeyGen.
    """
    return {
        10: (16, 21),
        15: (22, 30),
        30: (45, 62),
        45: (68, 84),
        60: (90, 108),
    }.get(duration_seconds, (68, 84))


def speech_preset(mode: str) -> dict[str, Any]:
    return dict(SPEECH_PRESETS.get(mode, SPEECH_PRESETS["natural"]))


def speech_speed(mode: str) -> float:
    return float(speech_preset(mode)["speed"])


def strip_known_outros(text: str, selected_outro: str = "") -> str:
    body = text
    for candidate in {
        selected_outro.strip(),
        LEGACY_OUTRO,
        "Veja o contexto no perfil.",
        *VARIABLE_CTAS,
    }:
        if candidate:
            body = re.sub(rf"\s*{re.escape(candidate)}\s*", " ", body, flags=re.I)
    return re.sub(r"[ \t]+", " ", body).strip()


def display_text(text: str) -> str:
    clean = text or ""
    phonetic_pairs = {
        "Maundjáro": "Mounjaro",
        "Ozêmpic": "Ozempic",
        "Uegóvi": "Wegovy",
        "Ribélsus": "Rybelsus",
        "G L P um": "GLP-1",
    }
    for source, target in phonetic_pairs.items():
        clean = re.sub(rf"\b{re.escape(source)}\b", target, clean, flags=re.I)
    return re.sub(r"\s+", " ", clean).strip()


def spoken_text(text: str, *, optimize_pronunciation: bool) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not optimize_pronunciation:
        return normalized
    return prepare_script_for_heygen_voice(normalized, add_sentence_breaks=False)


def fit_ten_second_text(text: str) -> str:
    clean = strip_known_outros(text)
    sentences = re.findall(r"[^.!?…]+[.!?…]*", clean)
    selected: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.strip().split()
        if not words:
            continue
        remaining = 24 - count
        if len(words) <= remaining:
            selected.append(sentence.strip())
            count += len(words)
            if count >= 18:
                break
        elif remaining > 0:
            selected.append(" ".join(words[:remaining]).rstrip(" ,:;") + "…")
            break
    result = " ".join(selected).strip()
    return result or " ".join(clean.split()[:24]).strip()


def fit_text_to_duration(
    text: str,
    duration_seconds: int,
    outro: str,
    *,
    cta_mode: CtaMode = "manual",
) -> str:
    if duration_seconds == 10 or cta_mode in {"none", "visual"}:
        return fit_ten_second_text(text) if duration_seconds == 10 else strip_known_outros(text, outro)

    selected_outro = re.sub(r"\s+", " ", outro).strip()
    _minimum_words, maximum_words = duration_word_limits(duration_seconds)
    outro_words = len(selected_outro.split()) if selected_outro else 0
    body_limit = max(1, maximum_words - outro_words)
    clean = strip_known_outros(text, selected_outro)
    sentences = re.findall(r"[^.!?…]+[.!?…]*", clean)
    selected: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.strip().split()
        if not words:
            continue
        remaining = body_limit - count
        if remaining <= 0:
            break
        if len(words) <= remaining:
            selected.append(sentence.strip())
            count += len(words)
        else:
            selected.append(" ".join(words[:remaining]).rstrip(" ,:;") + "…")
            break
    body = " ".join(selected).strip() or " ".join(clean.split()[:body_limit]).strip()
    return f"{body.rstrip()} {selected_outro}".strip() if selected_outro else body


def preview_text(text: str) -> str:
    return fit_ten_second_text(text)


def contains_phonetic_spelling(text: str) -> bool:
    return bool(re.search(r"\b(Maundjáro|Ozêmpic|Uegóvi|Ribélsus|G L P um)\b", text, re.I))


def normalize_performance_response(
    raw: dict[str, Any],
    *,
    source_text: str,
    duration_seconds: int,
    cta_mode: CtaMode,
    manual_cta: str,
    optimize_pronunciation: bool = True,
) -> dict[str, Any]:
    display = display_text(str(raw.get("displayText") or raw.get("spokenText") or source_text))
    cta = str(raw.get("cta") or "").strip()
    if cta_mode == "manual":
        cta = manual_cta.strip()
    elif cta_mode in {"none", "visual"}:
        cta = ""
    elif not cta:
        cta = VARIABLE_CTAS[0]

    fitted_display = fit_text_to_duration(
        display,
        duration_seconds,
        cta,
        cta_mode=cta_mode,
    )
    spoken = spoken_text(fitted_display, optimize_pronunciation=optimize_pronunciation)
    mode = str(raw.get("recommendedSpeechMode") or "natural")
    if mode not in SPEECH_PRESETS:
        mode = "natural"
    speed = float(raw.get("recommendedVoiceSpeed") or speech_speed(mode))
    if speed < 0.85 or speed > 1.15:
        speed = speech_speed(mode)
    return {
        "spokenText": spoken,
        "displayText": fitted_display,
        "tone": str(raw.get("tone") or "médico humano e seguro"),
        "pace": str(raw.get("pace") or "frases curtas, com pausas naturais"),
        "emotion": str(raw.get("emotion") or "calmo e convincente"),
        "emphasisWords": [str(item) for item in raw.get("emphasisWords") or []][:8],
        "pauseAfterSentencesMs": [int(item) for item in raw.get("pauseAfterSentencesMs") or []][:20],
        "recommendedVoiceSpeed": round(speed, 2),
        "recommendedSpeechMode": mode,
        "cta": cta,
    }


@dataclass(frozen=True)
class PerformancePrompt:
    system: str
    user: str


def build_performance_prompt(
    *,
    text: str,
    medical_cautions: str,
    duration_seconds: int,
    cta_mode: CtaMode,
    manual_cta: str,
    recent_ctas: list[str],
    video_agent: bool = False,
) -> PerformancePrompt:
    minimum_words, maximum_words = (
        video_agent_word_limits(duration_seconds)
        if video_agent
        else duration_word_limits(duration_seconds)
    )
    cta_instruction = {
        "auto": "Escolha um CTA natural e especifico para o conteudo, sem repetir historico.",
        "manual": f'Use exatamente este CTA, se houver: "{manual_cta.strip()}".',
        "none": "Nao inclua CTA falado.",
        "visual": "Nao inclua CTA falado; considere que o CTA sera apenas visual.",
    }[cta_mode]
    system = f"""Voce e diretor de performance de fala para videos curtos do Dr. Guilherme.
Reescreva para portugues brasileiro falado, como uma pessoa diante da camera.

Regras:
- Uma ideia por frase; frases curtas e de tamanhos variados.
- Evite "voce sabia?" como padrao.
- Evite "alem disso", "portanto" e "dessa forma".
- Evite excesso de termos tecnicos; nao use girias artificiais.
- Tom medico seguro, humano, convincente e natural.
- Sem doses, prescricao, promessa de resultado ou diagnostico.
- Nao invente informacoes.
- Use transicoes naturais e pequenas pausas quando fizer sentido.
- Considere rigorosamente {duration_seconds}s: {minimum_words} a {maximum_words} palavras.
- Nao repita a mesma noticia, lista de riscos ou conclusao em frases diferentes.
- Estruture: gancho e fato principal primeiro; explicacao ou exemplo no meio; um unico alerta clinico curto no fim.
- O alerta clinico deve ocupar no maximo uma frase curta e nao pode repetir o gancho.
- Prefira "as chamadas canetas para emagrecimento" quando marca especifica nao for essencial.
- Evite citar repetidamente Mounjaro, Ozempic ou Wegovy.
- O displayText nunca deve conter grafia fonetica.
- Retorne somente JSON no schema solicitado."""
    user = "\n".join(
        [
            f"DURACAO: {duration_seconds}s",
            f"CTA: {cta_instruction}",
            f"CTAS RECENTES A EVITAR: {' | '.join(recent_ctas[-5:]) or 'nenhum'}",
            f"CUIDADOS MEDICOS: {medical_cautions or 'Conteudo educativo; reforcar avaliacao individual quando necessario.'}",
            "TEXTO ORIGINAL:",
            text,
        ]
    )
    return PerformancePrompt(system=system, user=user)
