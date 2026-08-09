"""Prompt e fingerprints do Claude Narrative Director.

Este módulo prepara uma única decisão global. Ele não chama Anthropic, não
persiste versões e não gera shots no HeyGen.
"""

from __future__ import annotations

import json
from typing import Any

from api.services.story_contract import (
    STORY_CONTRACT_SCHEMA,
    STORY_CONTRACT_VERSION,
    STORY_PROMPT_VERSION,
    StoryBrief,
    canonical_hash,
    speech_words,
)


def allowed_provider_strategies(capabilities: dict[str, Any]) -> list[str]:
    strategies = ["local_compositor"]
    video_agent = capabilities.get("videoAgent")
    direct_video = capabilities.get("directVideo")
    if isinstance(video_agent, dict) and video_agent.get("supported"):
        strategies.append("video_agent")
    if isinstance(direct_video, dict) and direct_video.get("supported"):
        strategies.append("direct_video")
    return sorted(strategies)


def story_cache_payload(
    *,
    brief: StoryBrief | dict[str, Any],
    approved_speech: str,
    script_revision: int,
    final_speech_hash: str,
    script_contract_version: str,
    provider_capabilities_version: str,
    provider_strategies: list[str],
    model: str,
) -> dict[str, Any]:
    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    brief_json = parsed_brief.model_dump(mode="json")
    character_anchor = {
        "characterId": parsed_brief.characterId,
        "lookId": parsed_brief.lookId,
        "characterDescription": parsed_brief.characterDescription,
        "wardrobeDirection": parsed_brief.wardrobeDirection,
    }
    reference_assets = [asset.model_dump(mode="json") for asset in parsed_brief.referenceAssets]
    return {
        "storyContractVersion": STORY_CONTRACT_VERSION,
        "storyPromptVersion": STORY_PROMPT_VERSION,
        "brief": brief_json,
        "briefHash": canonical_hash(brief_json),
        "characterAnchorHash": canonical_hash(character_anchor),
        "referenceAssetHashes": [asset["sha256"] for asset in reference_assets],
        "approvedSpeech": approved_speech,
        "scriptRevision": script_revision,
        "finalSpeechHash": final_speech_hash,
        "scriptContractVersion": script_contract_version,
        "providerCapabilitiesVersion": provider_capabilities_version,
        "providerStrategies": sorted(provider_strategies),
        "model": model,
    }


def build_story_prompt(
    *,
    brief: StoryBrief | dict[str, Any],
    approved_speech: str,
    script_revision: int,
    final_speech_hash: str,
    provider_capabilities_version: str,
    provider_strategies: list[str],
) -> tuple[list[dict[str, Any]], str]:
    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    indexed_speech = [
        {"index": index, "word": word}
        for index, word in enumerate(speech_words(approved_speech))
    ]
    stable_rules = (
        "Você é o Claude Narrative Director do AI Video Creator. Planeje a história completa "
        "em uma única resposta estruturada. A fala aprovada é imutável: não escreva fala, "
        "não acrescente fatos médicos, doses, percentuais, diagnósticos ou recomendações. "
        "Cada shot referencia somente índices de palavras, com início inclusivo e fim exclusivo. "
        "Os intervalos devem começar em 0, ser contíguos, sem lacunas/sobreposição, e terminar "
        "exatamente em wordCount. Use somente characterId, lookId, referenceAssetIds e "
        "providerStrategy fornecidos no contexto. medicalAssertions deve ser sempre []. "
        "Para cada shot, entregue subject, period, wardrobe, atmosphere e heygenPrompt final, "
        "pronto para o provider e sem placeholders. O heygenPrompt é uma direção visual, nunca fala. "
        "Use somente estas rotas: avatar_anchor + direct_video para personagem falando; "
        "cinematic_broll + video_agent para ação visual sem lip-sync; local_transition + "
        "local_compositor sem chamada HeyGen. Mantenha continuidade de rosto, idade, cabelo, "
        "barba, corpo, figurino, acessórios, período, arquitetura, materiais, luz, paleta e câmera. "
        "Inclua no heygenPrompt as restrições relevantes da Character Bible, Visual Bible e "
        "Historical Setting, além dos anacronismos e mudanças proibidas. "
        "A soma de durationSeconds deve ser a duração solicitada e o custo de cada provider "
        "HeyGen é 1 job; local_compositor é 0. Não inclua texto fora do JSON."
    )
    system = [
        {
            "type": "text",
            "text": stable_rules,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": "JSON SCHEMA CANÔNICO:\n"
            + json.dumps(STORY_CONTRACT_SCHEMA, ensure_ascii=False, sort_keys=True),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    context = {
        "bindings": {
            "storyContractVersion": STORY_CONTRACT_VERSION,
            "storyPromptVersion": STORY_PROMPT_VERSION,
            "scriptRevision": script_revision,
            "finalSpeechHash": final_speech_hash,
            "providerCapabilitiesVersion": provider_capabilities_version,
        },
        "storyBrief": parsed_brief.model_dump(mode="json"),
        "allowedProviderStrategies": sorted(provider_strategies),
        "approvedSpeech": approved_speech,
        "wordCount": len(indexed_speech),
        "indexedSpeech": indexed_speech,
    }
    return system, json.dumps(context, ensure_ascii=False, indent=2)


def build_repair_instruction(error_code: str, error_message: str) -> str:
    return (
        "CORREÇÃO ÚNICA: a resposta anterior foi rejeitada pelo contrato local. "
        f"Código: {error_code}. Motivo: {error_message[:500]}. "
        "Gere novamente o JSON completo corrigindo somente a estrutura e o planejamento. "
        "A fala aprovada, os IDs permitidos e o objetivo educacional continuam imutáveis."
    )
