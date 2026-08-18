"""Contexto editorial e identidade herdada pelo Pack de Conteúdo."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from api.pack_design import EDUCATIONAL_FLOW_VERSION


PACK_CONTEXT_VERSION = "pack-context-v3"
PACK_EDUCATIONAL_FLOW_VERSION = EDUCATIONAL_FLOW_VERSION


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _narrative_brief(
    script: Mapping[str, Any],
    idea: Mapping[str, Any],
) -> dict[str, Any]:
    """Transforma ideia + roteiro aprovado em fontes explícitas para cada tela."""
    title = _first_text(script.get("titulo"), idea.get("titulo"), script.get("tema"))
    hook = _first_text(script.get("hook"), idea.get("hook"), title)
    tension = _first_text(script.get("dorConflito"), idea.get("publicoDor"), hook)
    explanation = _first_text(
        script.get("explicacaoSimples"),
        idea.get("angulo"),
        script.get("textoFalado"),
    )
    turn = _first_text(script.get("virada"), explanation)
    care = _first_text(script.get("cuidadosMedicos"), idea.get("observacaoCompliance"))
    cta = _first_text(script.get("cta"), idea.get("cta"), "Converse com um profissional.")
    learning_goal = _first_text(title, explanation, hook, "o tema")
    return {
        "centralTopic": title,
        "educationalFlowVersion": PACK_EDUCATIONAL_FLOW_VERSION,
        "learningGoal": f"Explicar {learning_goal} em linguagem simples, do conceito aos cuidados.",
        "tone": "educativo, acolhedor e sem julgamento",
        "plainLanguageRules": [
            "Comece pelo que a pessoa vai entender, não por uma provocação.",
            "Defina termos técnicos quando eles aparecerem.",
            "Prefira comparações claras, exemplos concretos e frases curtas.",
            "Transforme dúvidas comuns em explicações, sem culpar ou confrontar quem lê.",
        ],
        "sourcePriority": [
            "approvedScript",
            "linkedIdea",
            "medicalCompliance",
        ],
        "slidePlan": [
            {
                "slide": 1,
                "stage": "tema e objetivo",
                "purpose": "apresentar o assunto e o que a pessoa vai entender",
                "writingDirection": "abertura acolhedora; use o tema sem criar urgência ou confronto",
                "sourceText": title or hook or explanation,
            },
            {
                "slide": 2,
                "stage": "contexto",
                "purpose": "situar uma dúvida comum ou uma distinção importante",
                "writingDirection": "converta a tensão em pergunta ou comparação neutra, sem acusar quem lê",
                "sourceText": tension or explanation,
            },
            {
                "slide": 3,
                "stage": "conceito-chave",
                "purpose": "definir o conceito central em linguagem cotidiana",
                "writingDirection": "explique siglas, nomes e termos técnicos antes de avançar",
                "sourceText": explanation,
            },
            {
                "slide": 4,
                "stage": "como funciona",
                "purpose": "explicar o mecanismo ou contexto em passos simples",
                "writingDirection": "organize a explicação em duas ou três ideias que se conectam",
                "sourceText": explanation,
            },
            {
                "slide": 5,
                "stage": "o que a fonte mostra",
                "purpose": "apresentar evidência, dado ou implicação com contexto",
                "writingDirection": "se usar dado, diga o que ele significa; sem número isolado ou conclusão além da fonte",
                "sourceText": turn or explanation,
            },
            {
                "slide": 6,
                "stage": "cuidados e limites",
                "purpose": "explicar o que ainda exige cautela ou avaliação individual",
                "writingDirection": "feche a explicação com limite claro, sem medo ou julgamento",
                "sourceText": care or turn or explanation,
            },
            {
                "slide": 7,
                "stage": "resumo e próximo passo",
                "purpose": "retomar o aprendizado e indicar um próximo passo educativo seguro",
                "writingDirection": "resuma sem prescrever e use apenas CTA educativo neutro",
                "sourceText": cta,
            },
        ],
    }


def pack_identity(profile: Mapping[str, Any], avatar_set: Mapping[str, Any] | None) -> dict[str, Any]:
    mode = str(profile.get("avatarMode") or "single")
    looks = [
        {
            "role": str(look.get("role") or ""),
            "avatarId": str(look.get("avatarId") or ""),
        }
        for look in (avatar_set or {}).get("looks", [])
        if isinstance(look, Mapping) and look.get("avatarId")
    ]
    primary_avatar_id = str(
        profile.get("primaryAvatarId") or profile.get("avatarId") or (looks[0]["avatarId"] if looks else "")
    )
    return {
        "avatarMode": mode,
        "avatarSetId": str(profile.get("avatarSetId") or "") if mode == "set" else "",
        "primaryAvatarId": primary_avatar_id,
        "voiceId": str(profile.get("voiceId") or ""),
        "looks": looks,
    }


def identity_key(identity: Mapping[str, Any]) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def build_pack_context(
    *,
    script: Mapping[str, Any],
    idea: Mapping[str, Any] | None = None,
    profile: Mapping[str, Any],
    avatar_set: Mapping[str, Any] | None,
    design_system: Mapping[str, Any],
    compliance_rules: list[Mapping[str, Any]],
) -> dict[str, Any]:
    identity = pack_identity(profile, avatar_set)
    linked_idea = dict(idea or {})
    linked_idea.setdefault("ideaId", script.get("ideaId"))
    linked_idea.setdefault("tema", script.get("tema"))
    linked_idea.setdefault("formatoSugerido", script.get("formatoSugerido"))
    context = {
        "version": PACK_CONTEXT_VERSION,
        "idea": linked_idea,
        "script": dict(script),
        "performance": {
            "displayText": script.get("textoFalado") or "",
            "speechMode": profile.get("speechMode") or "natural",
            "generationMode": profile.get("generationMode") or "direct",
        },
        "avatarSet": dict(avatar_set) if avatar_set else {"mode": "single", "identity": identity},
        "identity": identity,
        "designSystem": dict(design_system),
        "compliance": list(compliance_rules),
        "narrativeBrief": _narrative_brief(script, linked_idea),
    }
    context["identityKey"] = identity_key(identity)
    return context
