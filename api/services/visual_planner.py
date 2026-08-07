"""Structured visual planner with a no-cost deterministic fallback."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Callable

from api.post_production_contracts import InteractionType, Transcript, VisualPlan, VisualPlanEvent


PLANNER_MODEL_VERSION = "visual-planner-fallback-v1"
LOGGER = logging.getLogger(__name__)
MIN_PLANNED_EVENT_MS = 1600
MAX_PLANNED_EVENT_MS = 5000
MAX_PLANNED_OVERLAP_MS = 250

_TRAILING_FUNCTION_WORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e",
    "em", "na", "nas", "no", "nos", "o", "os", "para", "pela", "pelo",
    "por", "que", "se", "sem", "um", "uma",
}
_GENERATED_ASSETS = (
    "medical_molecule", "consultation", "science", "warning", "focus",
)
_SUPPORT_NOISE_WORDS = _TRAILING_FUNCTION_WORDS | {
    "aqui", "ajudam", "antes", "está", "estão", "esperava", "isso", "meu",
    "melhor", "não", "nível", "planejar", "processo", "seu", "são", "vindo",
    "você",
}


def _short_visual_text(text: str, limit: int = 72) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" .,:;!?")
    if len(clean) <= limit:
        return clean
    shortened = clean[: limit + 1].rsplit(" ", 1)[0]
    return shortened or clean[:limit]


def _event_id(transcript: Transcript, start: int, end: int, kind: InteractionType) -> str:
    raw = f"{transcript.videoFingerprint}:{start}:{end}:{kind.value}".encode()
    return f"evt-{hashlib.sha256(raw).hexdigest()[:12]}"


def _tokens(value: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ]+", value.casefold())


def _trim_function_words(value: str) -> str:
    words = value.strip(" .,:;!?\n").split()
    while len(words) > 2 and _tokens(words[-1]) and _tokens(words[-1])[-1] in _TRAILING_FUNCTION_WORDS:
        words.pop()
    return " ".join(words).strip(" .,:;!?")


def _is_real_list(spoken: str) -> bool:
    return spoken.count(",") >= 2 or ";" in spoken or ":" in spoken


def _progressive_items(spoken: str) -> list[str]:
    clean = re.sub(r"\s+", " ", spoken).strip(" .")
    clean = re.sub(r"\b(influenciam|incluem|envolvem)\b.*$", "", clean, flags=re.IGNORECASE).strip(" ,")
    parts = [part.strip(" ,;:") for part in re.split(r"[,;:]", clean) if part.strip(" ,;:")]
    if len(parts) < 3:
        return []
    items: list[str] = []
    for part in parts[:4]:
        item = re.sub(r"^(e|ou)\s+", "", part, flags=re.IGNORECASE)
        item = _trim_function_words(" ".join(item.split()[:5]))
        if item:
            items.append(item)
    return items if len(items) >= 3 else []


def generated_asset_ref(spoken: str, visual_text: str) -> str:
    haystack = f"{spoken} {visual_text}".casefold()
    if any(term in haystack for term in ("peptídeo", "molécula", "medicamento")):
        return "generated:medical_molecule"
    if any(term in haystack for term in ("médico", "nutricionista", "dermatologista", "consultório")):
        return "generated:consultation"
    if any(term in haystack for term in ("ciência", "estudo", "evidência")):
        return "generated:science"
    if any(term in haystack for term in ("risco", "alerta", "promessa falsa", "cuidado")):
        return "generated:warning"
    return "generated:focus"


def _compact_visual_text(kind: InteractionType, spoken: str, proposed: str) -> str:
    if kind == InteractionType.progressive_list:
        items = _progressive_items(spoken)
        if items:
            return _short_visual_text(" • ".join(items), limit=96)

    if kind == InteractionType.supporting_visual:
        keywords: list[str] = []
        for token in re.findall(r"[\wÀ-ÿ]+", spoken, flags=re.UNICODE):
            if token.casefold() in _SUPPORT_NOISE_WORDS or len(token) < 4:
                continue
            if token.casefold() not in {item.casefold() for item in keywords}:
                keywords.append(token)
            if len(keywords) == 3:
                break
        if len(keywords) >= 2:
            return " · ".join(keywords)

    source = proposed.strip() or spoken
    proposed_words = source.split()[:6]
    compact = _trim_function_words(" ".join(proposed_words))

    gerund = re.search(r"\b\w+(?:ando|endo|indo)\b\s+(.+)", spoken, flags=re.IGNORECASE)
    if gerund and re.search(r"\b\w+(?:ando|endo|indo)\b\s*$", compact, flags=re.IGNORECASE):
        complement = re.sub(r"^(em|para|por)\s+", "", gerund.group(1), flags=re.IGNORECASE)
        compact = _trim_function_words(" ".join(complement.split()[:6])) or compact

    return _short_visual_text(compact)


def _expanded_event_range(transcript: Transcript, event: VisualPlanEvent) -> tuple[int, int]:
    start = event.startWordIndex
    end = event.endWordIndex
    if end >= len(transcript.words):
        return start, end
    start_ms = transcript.words[start].startMs
    proposed = _trim_function_words(event.visualText)
    needs_completion = bool(re.search(r"\b\w+(?:ando|endo|indo)\b\s*$", proposed, flags=re.IGNORECASE))
    while end + 1 < len(transcript.words):
        duration = transcript.words[end].endMs - start_ms
        if duration >= MIN_PLANNED_EVENT_MS and not needs_completion:
            break
        next_end = transcript.words[end + 1].endMs
        if next_end - start_ms > MAX_PLANNED_EVENT_MS:
            break
        end += 1
        if needs_completion and re.search(r"[.!?]$", transcript.words[end].text):
            break
    return start, end


def _tighten_event(transcript: Transcript, event: VisualPlanEvent) -> VisualPlanEvent:
    start, end = _expanded_event_range(transcript, event)
    selected = transcript.words[start : end + 1]
    spoken = " ".join(word.text for word in selected)
    kind = event.interactionType
    if kind == InteractionType.progressive_list and not _is_real_list(spoken):
        kind = InteractionType.caption_emphasis
        matches = re.findall(r"\bo que\s+[^.!?]+", spoken, flags=re.IGNORECASE)
        proposed = " ".join(matches[-1].split()[:5]) if matches else event.visualText
    else:
        proposed = event.visualText
    visual_text = _compact_visual_text(kind, spoken, proposed)
    asset_ref = event.assetRef
    if kind == InteractionType.supporting_visual:
        if not asset_ref or not asset_ref.startswith("generated:"):
            asset_ref = generated_asset_ref(spoken, visual_text)
    payload = event.model_dump(mode="json")
    payload.update(
        id=_event_id(transcript, start, end, kind),
        startWordIndex=start,
        endWordIndex=end,
        interactionType=kind,
        visualText=visual_text,
        assetRef=asset_ref,
    )
    return VisualPlanEvent.model_validate(payload)


def normalize_visual_plan(transcript_payload: dict[str, Any], plan_payload: dict[str, Any]) -> dict[str, Any]:
    transcript = Transcript.model_validate(transcript_payload)
    plan = VisualPlan.model_validate(plan_payload)
    normalized = sorted(
        (_tighten_event(transcript, event) for event in plan.events),
        key=lambda event: (event.startWordIndex, event.endWordIndex),
    )
    accepted: list[VisualPlanEvent] = []
    for event in normalized:
        if accepted:
            previous = accepted[-1]
            overlap = (
                transcript.words[previous.endWordIndex].endMs
                - transcript.words[event.startWordIndex].startMs
            )
            if overlap > MAX_PLANNED_OVERLAP_MS:
                if event.confidence > previous.confidence:
                    accepted[-1] = event
                continue
        accepted.append(event)
    plan.events = accepted
    return plan.model_dump(mode="json")


def deterministic_visual_plan(transcript_payload: dict[str, Any]) -> dict[str, Any]:
    transcript = Transcript.model_validate(transcript_payload)
    if not transcript.words:
        raise ValueError("A transcrição precisa conter palavras indexadas.")
    events: list[VisualPlanEvent] = []
    usable_segments = [segment for segment in transcript.segments if segment.get("startWordIndex") is not None]
    for position, segment in enumerate(usable_segments):
        if position % 2 and position != len(usable_segments) - 1:
            continue
        start = int(segment["startWordIndex"])
        end = int(segment["endWordIndex"])
        text = str(segment.get("text") or "")
        lower = text.casefold()
        if position == len(usable_segments) - 1 and any(term in lower for term in ("salve", "compartilhe", "comente", "procure", "consulte")):
            kind = InteractionType.cta_card
        elif any(marker in text for marker in (":", ";")):
            kind = InteractionType.progressive_list
        elif position == 0:
            kind = InteractionType.kinetic_text
        else:
            kind = InteractionType.caption_emphasis
        events.append(
            VisualPlanEvent(
                id=_event_id(transcript, start, end, kind),
                startWordIndex=start,
                endWordIndex=end,
                interactionType=kind,
                visualText=_short_visual_text(text),
                intensity="high" if position == 0 else "medium",
                reason="Trecho completo da fala com começo e fim verificáveis.",
                confidence=0.78,
                fallback=InteractionType.caption_emphasis,
            )
        )
    if not events:
        last = min(len(transcript.words) - 1, 8)
        text = " ".join(word.text for word in transcript.words[: last + 1])
        kind = InteractionType.caption_emphasis
        events.append(
            VisualPlanEvent(
                id=_event_id(transcript, 0, last, kind),
                startWordIndex=0,
                endWordIndex=last,
                interactionType=kind,
                visualText=_short_visual_text(text),
                intensity="medium",
                reason="Fallback para transcrição sem segmentos utilizáveis.",
                confidence=0.65,
                fallback=kind,
            )
        )
    return VisualPlan(
        modelVersion=PLANNER_MODEL_VERSION,
        transcriptVersion=transcript.version,
        videoFingerprint=transcript.videoFingerprint,
        events=events,
    ).model_dump(mode="json")


def plan_visuals(
    transcript_payload: dict[str, Any],
    *,
    cache_get: Callable[[str, Any], dict[str, Any] | None] | None = None,
    cache_put: Callable[[str, Any, dict[str, Any]], None] | None = None,
    record_usage: Callable[[str, str, Any], None] | None = None,
) -> tuple[dict[str, Any], str]:
    """Return a structured Claude plan only when explicitly enabled, otherwise fallback."""
    cache_key = {
        "videoFingerprint": transcript_payload.get("videoFingerprint"),
        "transcriptVersion": transcript_payload.get("version"),
        "plannerVersion": PLANNER_MODEL_VERSION,
    }
    if cache_get and (cached := cache_get("post_production.plan", cache_key)):
        VisualPlan.model_validate(cached)
        return normalize_visual_plan(transcript_payload, cached), "cache"

    paid_enabled = os.getenv("POST_PRODUCTION_USE_CLAUDE") == "1"
    has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if paid_enabled and has_key:
        try:
            plan, message, model = _anthropic_visual_plan(transcript_payload)
            plan = normalize_visual_plan(transcript_payload, plan)
            if cache_put:
                cache_put("post_production.plan", cache_key, plan)
            if record_usage:
                record_usage("post_production.plan", model, message)
            return plan, "anthropic"
        except Exception as exc:
            # A provider/schema failure must not make local post-production unavailable.
            LOGGER.warning("Post-production planner fallback: %s: %s", type(exc).__name__, exc)
    plan = normalize_visual_plan(transcript_payload, deterministic_visual_plan(transcript_payload))
    if cache_put:
        cache_put("post_production.plan", cache_key, plan)
    return plan, "fallback"


def _anthropic_visual_plan(transcript_payload: dict[str, Any]) -> tuple[dict[str, Any], Any, str]:
    import anthropic

    transcript = Transcript.model_validate(transcript_payload)
    indexed_text = "\n".join(f"{word.index}: {word.text}" for word in transcript.words)
    prompt = f"""Planeje interações visuais para esta fala em português brasileiro.
Escolha SOMENTE startWordIndex e endWordIndex; nunca produza timestamps.
Use apenas estas interações: none, caption_emphasis, kinetic_text, progressive_list,
supporting_visual e cta_card. Não crie estatísticas, prescrições, diagnósticos,
promessas ou qualquer alegação ausente na fala. Retorne de 4 a 6 intervenções,
sem usar none. Varie os tipos conforme o conteúdo e use progressive_list quando
a fala realmente enumerar pelo menos três itens. visualText deve ter de 2 a 6
palavras, formar uma ideia completa, nunca terminar em artigo/preposição, ser
popular, usar exclusivamente palavras contidas no intervalo e não repetir a
legenda inteira. Para supporting_visual, escolha um assetRef entre
medical_molecule, consultation, science, warning e focus; nos demais use null.
Cada elemento deve permanecer entre 1,5 e 5 segundos. Evite sobreposição.

PALAVRAS INDEXADAS:
{indexed_text[:90000]}"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "startWordIndex", "endWordIndex", "interactionType", "visualText",
                        "intensity", "assetRef", "reason", "confidence", "fallback",
                    ],
                    "properties": {
                        "startWordIndex": {"type": "integer"},
                        "endWordIndex": {"type": "integer"},
                        "interactionType": {"type": "string", "enum": [kind.value for kind in InteractionType]},
                        "visualText": {"type": "string"},
                        "intensity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "assetRef": {
                            "type": ["string", "null"],
                            "enum": [None, *_GENERATED_ASSETS],
                        },
                        "reason": {"type": "string"},
                        "confidence": {"type": "number"},
                        "fallback": {"type": "string", "enum": [kind.value for kind in InteractionType]},
                    },
                },
            }
        },
    }
    model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    message = anthropic.Anthropic().messages.create(
        model=model,
        max_tokens=4000,
        system="Você é editor de vídeo e revisor responsável de conteúdo médico.",
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(getattr(block, "text", "") for block in message.content)
    candidates = json.loads(raw).get("events", [])
    events: list[VisualPlanEvent] = []
    for candidate in candidates:
        start = int(candidate["startWordIndex"])
        end = int(candidate["endWordIndex"])
        if start > end or end >= len(transcript.words):
            continue
        spoken = " ".join(word.text for word in transcript.words[start : end + 1])
        proposed = _short_visual_text(str(candidate.get("visualText") or ""))
        spoken_tokens = set(re.findall(r"[\wÀ-ÿ]+", spoken.casefold()))
        proposed_tokens = set(re.findall(r"[\wÀ-ÿ]+", proposed.casefold()))
        if not proposed_tokens.issubset(spoken_tokens):
            proposed = _short_visual_text(spoken)
        kind = InteractionType(candidate["interactionType"])
        events.append(
            VisualPlanEvent(
                id=_event_id(transcript, start, end, kind),
                startWordIndex=start,
                endWordIndex=end,
                interactionType=kind,
                visualText=proposed,
                intensity=candidate["intensity"],
                assetRef=candidate.get("assetRef"),
                reason=str(candidate["reason"])[:180],
                confidence=float(candidate["confidence"]),
                fallback=InteractionType(candidate["fallback"]),
            )
        )
    if not events:
        raise ValueError("Claude não retornou eventos visuais válidos.")
    plan = VisualPlan(
        modelVersion=f"anthropic:{model}",
        transcriptVersion=transcript.version,
        videoFingerprint=transcript.videoFingerprint,
        events=events,
    ).model_dump(mode="json")
    return plan, message, model
