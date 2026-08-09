"""Contrato determinístico do Story Mode.

Claude propõe a narrativa, mas este módulo puro decide se o plano pode existir:
schema, cobertura da fala, IDs permitidos, custo estrutural e vínculos de versão.
Nenhuma função aqui faz I/O ou chama providers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.services.script_editor import WORD_PATTERN


STORY_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "shared" / "story_contract.json"
STORY_CONTRACT_SCHEMA: dict[str, Any] = json.loads(
    STORY_CONTRACT_PATH.read_text(encoding="utf-8")
)
STORY_CONTRACT_VERSION = "story-contract-v1"
STORY_PROMPT_VERSION = "story-director-v1"
PROVIDER_STRATEGIES = ("video_agent", "direct_video", "local_compositor")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoryReferenceAsset(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    kind: Literal["image", "video", "document"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    description: str = Field(default="", max_length=300)


class StoryBrief(StrictModel):
    storyType: Literal[
        "historical_explainer",
        "medical_explainer",
        "narrative_explainer",
    ] = "narrative_explainer"
    educationalGoal: str = Field(min_length=10, max_length=500)
    period: str = Field(default="", max_length=160)
    location: str = Field(default="", max_length=200)
    realismLevel: Literal["high", "medium", "stylized"] = "high"
    historicalAccuracy: Literal["strict", "inspired", "not_applicable"] = (
        "not_applicable"
    )
    tone: Literal[
        "curious_educational",
        "documentary",
        "warm_explainer",
        "dramatic_restrained",
    ] = "curious_educational"
    durationSeconds: int = Field(ge=10, le=180)
    orientation: Literal["portrait", "landscape", "square"] = "portrait"
    productionTier: Literal["standard", "cinematic", "premium"] = "cinematic"
    maxHeyGenJobs: int = Field(default=6, ge=0, le=12)
    maxRegenerationsPerShot: int = Field(default=1, ge=0, le=2)
    maxBudgetUsd: float | None = Field(default=None, ge=0, le=10000)
    characterId: str | None = Field(default=None, max_length=160)
    lookId: str | None = Field(default=None, max_length=160)
    characterDescription: str = Field(default="", max_length=500)
    wardrobeDirection: str = Field(default="", max_length=300)
    referenceAssets: list[StoryReferenceAsset] = Field(default_factory=list, max_length=12)


class NarrativeArc(StrictModel):
    opening: str = Field(min_length=3, max_length=240)
    development: str = Field(min_length=3, max_length=240)
    turn: str = Field(min_length=3, max_length=240)
    ending: str = Field(min_length=3, max_length=240)


class HistoricalSetting(StrictModel):
    period: str = Field(max_length=160)
    location: str = Field(max_length=200)
    accuracyMode: Literal["strict", "inspired", "not_applicable"]


class StoryBible(StrictModel):
    premise: str = Field(min_length=10, max_length=500)
    educationalGoal: str = Field(min_length=10, max_length=500)
    narrativeArc: NarrativeArc
    historicalSetting: HistoricalSetting


class Wardrobe(StrictModel):
    base: str = Field(max_length=240)
    accessories: list[str] = Field(max_length=8)
    colors: list[str] = Field(max_length=8)


class CharacterBible(StrictModel):
    characterId: str | None = Field(max_length=160)
    lookId: str | None = Field(max_length=160)
    identityRule: str = Field(min_length=3, max_length=300)
    voiceRule: str = Field(min_length=3, max_length=300)
    wardrobe: Wardrobe
    forbiddenChanges: list[str] = Field(min_length=1, max_length=12)


class VisualBible(StrictModel):
    palette: str = Field(min_length=3, max_length=240)
    lighting: str = Field(min_length=3, max_length=240)
    cameraStyle: str = Field(min_length=3, max_length=240)
    texture: str = Field(min_length=3, max_length=240)
    forbiddenAnachronisms: list[str] = Field(max_length=20)


class ShotSpeech(StrictModel):
    mode: Literal["avatar_speaks", "voice_continues_from_base_scene"]
    startWordIndex: int = Field(ge=0)
    endWordIndex: int = Field(ge=1)


class ShotCharacter(StrictModel):
    required: bool
    characterId: str | None = Field(max_length=160)
    lookId: str | None = Field(max_length=160)


class ShotCamera(StrictModel):
    framing: str = Field(min_length=2, max_length=160)
    movement: str = Field(min_length=2, max_length=160)
    lens: str = Field(min_length=2, max_length=160)


class ShotEstimatedCost(StrictModel):
    heygenJobs: int = Field(ge=0, le=1)
    anthropicCalls: Literal[0]


class StoryShot(StrictModel):
    id: str = Field(pattern=r"^shot-[0-9]{2}$")
    order: int = Field(ge=1, le=12)
    narrativePurpose: str = Field(min_length=3, max_length=300)
    shotType: Literal[
        "avatar_anchor",
        "historical_broll",
        "modern_broll",
        "transition",
        "local_asset",
    ]
    providerStrategy: Literal["video_agent", "direct_video", "local_compositor"]
    durationSeconds: float = Field(gt=0, le=30)
    speech: ShotSpeech
    character: ShotCharacter
    environment: str = Field(min_length=3, max_length=500)
    action: str = Field(min_length=3, max_length=500)
    camera: ShotCamera
    lighting: str = Field(min_length=2, max_length=200)
    continuityKeys: list[str] = Field(min_length=1, max_length=12)
    referenceAssetIds: list[str] = Field(max_length=12)
    negativePrompt: list[str] = Field(max_length=20)
    audioPolicy: Literal["preserve_base_narration", "mute_generated_audio"]
    estimatedCost: ShotEstimatedCost


class StoryPlan(StrictModel):
    contractVersion: Literal["story-contract-v1"]
    storyBible: StoryBible
    characterBible: CharacterBible
    visualBible: VisualBible
    medicalAssertions: list[str] = Field(max_length=0)
    shots: list[StoryShot] = Field(min_length=1, max_length=12)


class StoryContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def speech_words(speech: str) -> list[str]:
    return WORD_PATTERN.findall(speech)


def _semantic_strings(plan: StoryPlan) -> list[str]:
    arc = plan.storyBible.narrativeArc
    values = [
        plan.storyBible.premise,
        plan.storyBible.educationalGoal,
        arc.opening,
        arc.development,
        arc.turn,
        arc.ending,
    ]
    for shot in plan.shots:
        values.extend(
            [
                shot.narrativePurpose,
                shot.environment,
                shot.action,
                shot.lighting,
            ]
        )
    return values


def _numeric_claims(text: str) -> set[str]:
    return {
        match.casefold().replace(" ", "")
        for match in re.findall(
            r"(?<![\w-])\d+(?:[.,]\d+)?\s*(?:%|mg|g|kg|ml|anos?|dias?|semanas?|meses?)?",
            text,
            flags=re.IGNORECASE,
        )
    }


def _medical_signals(text: str) -> set[str]:
    stems = (
        "caus",
        "cur",
        "trat",
        "preven",
        "reduz",
        "aument",
        "melhor",
        "pior",
        "risco",
        "sintom",
        "diagn",
        "dose",
        "efeito",
        "doenç",
        "condiç",
        "medic",
        "terap",
        "mortal",
        "câncer",
        "cancer",
        "diabet",
        "pressão",
        "pressao",
        "colesterol",
        "obes",
        "clínic",
        "clinic",
    )
    tokens = {token.casefold() for token in re.findall(r"[\wÀ-ÿ-]+", text)}
    return {stem for stem in stems if any(token.startswith(stem) for token in tokens)}


def validate_story_plan(
    raw: Any,
    *,
    brief: StoryBrief | dict[str, Any],
    approved_speech: str,
    allowed_provider_strategies: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Valida o plano e retorna JSON canônico pronto para persistência."""

    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    try:
        plan = StoryPlan.model_validate(raw)
    except ValidationError as exc:
        raise StoryContractError("STORY_SCHEMA_INVALID", str(exc)) from exc

    words = speech_words(approved_speech)
    if not words:
        raise StoryContractError("APPROVED_SPEECH_EMPTY", "A fala aprovada está vazia.")
    if plan.storyBible.educationalGoal.strip() != parsed_brief.educationalGoal.strip():
        raise StoryContractError(
            "EDUCATIONAL_GOAL_CHANGED",
            "O Story Director alterou o objetivo educacional aprovado no briefing.",
        )
    setting = plan.storyBible.historicalSetting
    if setting.accuracyMode != parsed_brief.historicalAccuracy:
        raise StoryContractError(
            "HISTORICAL_ACCURACY_CHANGED",
            "O plano alterou o nível de rigor histórico do briefing.",
        )
    if parsed_brief.period and setting.period.strip() != parsed_brief.period.strip():
        raise StoryContractError("PERIOD_CHANGED", "O plano alterou o período do briefing.")
    if parsed_brief.location and setting.location.strip() != parsed_brief.location.strip():
        raise StoryContractError("LOCATION_CHANGED", "O plano alterou o local do briefing.")

    if plan.characterBible.characterId != parsed_brief.characterId:
        raise StoryContractError("CHARACTER_ID_UNKNOWN", "O plano inventou ou trocou o personagem.")
    if plan.characterBible.lookId != parsed_brief.lookId:
        raise StoryContractError("LOOK_ID_UNKNOWN", "O plano inventou ou trocou o look.")

    allowed_providers = set(allowed_provider_strategies)
    if not allowed_providers.issubset(PROVIDER_STRATEGIES):
        raise StoryContractError(
            "PROVIDER_CONTEXT_INVALID", "O contexto contém uma estratégia de provider desconhecida."
        )
    allowed_assets = {asset.id for asset in parsed_brief.referenceAssets}
    seen_assets: set[str] = set()
    cursor = 0
    heygen_jobs = 0
    for index, shot in enumerate(plan.shots, start=1):
        expected_id = f"shot-{index:02d}"
        if shot.order != index or shot.id != expected_id:
            raise StoryContractError(
                "SHOT_ORDER_INVALID", "Shots devem ter ordem contínua e IDs canônicos."
            )
        if shot.speech.startWordIndex != cursor:
            raise StoryContractError(
                "SPEECH_COVERAGE_GAP",
                "O Shot Plan deixou uma lacuna ou sobreposição na fala aprovada.",
            )
        if shot.speech.endWordIndex <= shot.speech.startWordIndex:
            raise StoryContractError(
                "SPEECH_RANGE_INVALID", "Todo shot precisa cobrir ao menos uma palavra."
            )
        if shot.speech.endWordIndex > len(words):
            raise StoryContractError(
                "SPEECH_RANGE_INVALID", "Um shot ultrapassou a fala aprovada."
            )
        cursor = shot.speech.endWordIndex
        if shot.providerStrategy not in allowed_providers:
            raise StoryContractError(
                "PROVIDER_NOT_ALLOWED",
                f"A estratégia '{shot.providerStrategy}' não está disponível no contexto.",
            )
        unknown_assets = set(shot.referenceAssetIds) - allowed_assets
        if unknown_assets:
            raise StoryContractError(
                "ASSET_ID_UNKNOWN",
                "O plano usou assets que não pertencem ao briefing: "
                + ", ".join(sorted(unknown_assets)),
            )
        seen_assets.update(shot.referenceAssetIds)
        if shot.character.required:
            if (
                not parsed_brief.characterId
                or shot.character.characterId != parsed_brief.characterId
                or shot.character.lookId != parsed_brief.lookId
            ):
                raise StoryContractError(
                    "SHOT_CHARACTER_UNKNOWN", "Um shot exige um personagem não autorizado."
                )
        elif shot.character.characterId is not None or shot.character.lookId is not None:
            raise StoryContractError(
                "SHOT_CHARACTER_INCONSISTENT",
                "Shots sem personagem devem usar IDs nulos.",
            )
        if shot.shotType == "avatar_anchor" and not shot.character.required:
            raise StoryContractError(
                "AVATAR_ANCHOR_MISSING_CHARACTER", "Avatar anchor exige o personagem aprovado."
            )
        expected_jobs = 0 if shot.providerStrategy == "local_compositor" else 1
        if shot.estimatedCost.heygenJobs != expected_jobs:
            raise StoryContractError(
                "SHOT_COST_INCONSISTENT", "O custo estrutural do shot não corresponde ao provider."
            )
        heygen_jobs += expected_jobs

    if cursor != len(words):
        raise StoryContractError(
            "SPEECH_COVERAGE_INCOMPLETE",
            f"O plano cobriu {cursor} de {len(words)} palavras aprovadas.",
        )
    if heygen_jobs > parsed_brief.maxHeyGenJobs:
        raise StoryContractError(
            "HEYGEN_JOB_LIMIT_EXCEEDED",
            f"O plano exige {heygen_jobs} jobs, acima do limite de {parsed_brief.maxHeyGenJobs}.",
        )
    total_duration = sum(shot.durationSeconds for shot in plan.shots)
    if abs(total_duration - parsed_brief.durationSeconds) > 1:
        raise StoryContractError(
            "STORY_DURATION_MISMATCH",
            "A soma dos shots precisa corresponder à duração do briefing (tolerância de 1s).",
        )

    allowed_claim_context = " ".join(
        [
            approved_speech,
            parsed_brief.educationalGoal,
            parsed_brief.period,
            parsed_brief.location,
        ]
    )
    allowed_numbers = _numeric_claims(allowed_claim_context)
    proposed_numbers = _numeric_claims(" ".join(_semantic_strings(plan)))
    if proposed_numbers - allowed_numbers:
        raise StoryContractError(
            "UNAUTHORIZED_NUMERIC_CLAIM",
            "O plano introduziu número, dose ou frequência que não existe na fala ou no briefing.",
        )
    allowed_medical_signals = _medical_signals(allowed_claim_context)
    proposed_medical_signals = _medical_signals(" ".join(_semantic_strings(plan)))
    if proposed_medical_signals - allowed_medical_signals:
        raise StoryContractError(
            "UNAUTHORIZED_MEDICAL_ASSERTION",
            "O plano introduziu linguagem clínica que não existe na fala ou no briefing.",
        )

    return plan.model_dump(mode="json")


def story_hash(plan: dict[str, Any]) -> str:
    return canonical_hash(plan)
