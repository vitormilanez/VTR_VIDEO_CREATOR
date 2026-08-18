from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from api.services.medical_identity import (
    MEDICAL_DEFAULT_SAFE_CTA,
    MEDICAL_EDITORIAL_PROMPT,
    safe_editorial_cta,
)
from api.services.script_editor import duration_limits
from integrations.portuguese_br import prepare_script_for_heygen_voice


SpeechMode = Literal["natural", "direto", "enfatico", "fiel"]
VoiceMood = Literal["confident", "upbeat", "warm", "serious", "neutral"]
CtaMode = Literal["auto", "manual", "none", "visual"]

VARIABLE_CTAS = [
    MEDICAL_DEFAULT_SAFE_CTA,
    "Salve este conteúdo para rever com calma.",
    "Use esta informação para preparar suas dúvidas para a consulta.",
    "Antes de qualquer tratamento, converse com o médico responsável pelo seu cuidado.",
]

LEGACY_OUTRO = "Me siga para mais dicas, e obrigado."
LEGACY_CAPTURE_CTAS = (
    "Me siga para acompanhar mais conteúdos como este.",
    "Quer entender melhor seu corpo? Me acompanhe por aqui.",
    "Salva este vídeo porque você vai precisar lembrar disso.",
    "Se esse conteúdo fez sentido, me acompanha para ver os próximos.",
    "Quer mais dicas? Siga e acompanhe.",
)

SPEECH_PRESETS: dict[str, dict[str, Any]] = {
    "natural": {"speed": 0.96, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "direto": {"speed": 1.0, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "enfatico": {"speed": 0.98, "pitch": 0, "volume": 1, "locale": "pt-BR"},
    "fiel": {"speed": 1.0, "pitch": 0, "volume": 1, "locale": "pt-BR"},
}


VOICE_MOOD_PRESETS: dict[str, dict[str, Any]] = {
    "confident": {
        "speedMultiplier": 1.02,
        "pitch": 1,
        "direction": (
            "confident, positive and reassuring, with conversational energy; "
            "never sad or melancholic"
        ),
    },
    "upbeat": {
        "speedMultiplier": 1.04,
        "pitch": 2,
        "direction": (
            "upbeat, lively and optimistic, with clear enthusiasm but without sounding theatrical"
        ),
    },
    "warm": {
        "speedMultiplier": 0.99,
        "pitch": 0,
        "direction": "warm, empathetic and approachable; gentle, but not sad or slow",
    },
    "serious": {
        "speedMultiplier": 0.99,
        "pitch": -1,
        "direction": "serious, objective and composed; informative, not gloomy or alarmist",
    },
    "neutral": {
        "speedMultiplier": 1.0,
        "pitch": 0,
        "direction": "neutral, clear and natural; avoid sadness, drama or exaggerated enthusiasm",
    },
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
    """Faixa de geração do perfil central, sem usar o limite rígido como meta."""
    return duration_limits(duration_seconds)


def video_agent_word_limits(duration_seconds: int) -> tuple[int, int]:
    """Todos os modos usam o mesmo perfil central de fala e duração."""
    return duration_limits(duration_seconds)


def speech_preset(mode: str) -> dict[str, Any]:
    return dict(SPEECH_PRESETS.get(mode, SPEECH_PRESETS["natural"]))


def speech_speed(mode: str) -> float:
    return float(speech_preset(mode)["speed"])


def voice_mood_preset(mood: str) -> dict[str, Any]:
    return dict(VOICE_MOOD_PRESETS.get(mood, VOICE_MOOD_PRESETS["confident"]))


def voice_mood_direction(mood: str) -> str:
    return str(voice_mood_preset(mood)["direction"])


def voice_settings(mode: str, mood: str = "confident") -> dict[str, Any]:
    """Combina ritmo e humor usando apenas ajustes aceitos pelo Direct Avatar."""
    settings = speech_preset(mode)
    mood_preset = voice_mood_preset(mood)
    settings["speed"] = round(
        min(1.5, max(0.5, float(settings["speed"]) * float(mood_preset["speedMultiplier"]))),
        2,
    )
    settings["pitch"] = float(mood_preset["pitch"])
    return settings


def strip_known_outros(text: str, selected_outro: str = "") -> str:
    body = text
    for candidate in {
        selected_outro.strip(),
        LEGACY_OUTRO,
        "Veja o contexto no perfil.",
        *LEGACY_CAPTURE_CTAS,
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
    if cta:
        cta = safe_editorial_cta(cta)

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
    safe_manual_cta = safe_editorial_cta(manual_cta)
    cta_instruction = {
        "auto": "Escolha somente um CTA educativo neutro, sem venda, captacao ou pedido para seguir.",
        "manual": f'Use exatamente este CTA educativo, se houver: "{safe_manual_cta}".',
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
- Retorne somente JSON no schema solicitado.

{MEDICAL_EDITORIAL_PROMPT}"""
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
