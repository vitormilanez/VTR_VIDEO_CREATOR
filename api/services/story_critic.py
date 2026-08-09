"""Contrato, prompt e orçamento determinístico do Story Critic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.services.story_contract import StoryBrief, canonical_hash


STORY_CRITIC_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "story_critic_contract.json"
)
STORY_CRITIC_SCHEMA: dict[str, Any] = json.loads(
    STORY_CRITIC_CONTRACT_PATH.read_text(encoding="utf-8")
)
STORY_CRITIC_CONTRACT_VERSION = "story-critic-v1"
STORY_CRITIC_PROMPT_VERSION = "story-critic-prompt-v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriticIssue(StrictModel):
    code: Literal[
        "NARRATIVE_ARC_WEAK",
        "NARRATIVE_PURPOSE_UNCLEAR",
        "SHOT_REDUNDANT",
        "CHARACTER_CONTINUITY_RISK",
        "WARDROBE_CONTINUITY_RISK",
        "ENVIRONMENT_CONTINUITY_RISK",
        "CAMERA_CONTINUITY_RISK",
        "HISTORICAL_ANACHRONISM_RISK",
        "HISTORICAL_ACCURACY_RISK",
        "MEDICAL_VISUAL_OVERCLAIM",
        "MEDICAL_CONTEXT_RISK",
        "PROVIDER_MISMATCH",
        "SHOT_DIFFICULTY_HIGH",
    ]
    category: Literal[
        "narrative", "continuity", "historical", "medical", "redundancy", "provider"
    ]
    severity: Literal["info", "warning", "blocking"]
    shotIds: list[str] = Field(max_length=12)
    message: str = Field(min_length=3, max_length=400)
    suggestedAction: str = Field(min_length=3, max_length=400)


class ShotAssessment(StrictModel):
    shotId: str = Field(pattern=r"^shot-[0-9]{2}$")
    difficulty: Literal["low", "medium", "high"]
    continuityRisk: Literal["low", "medium", "high"]
    historicalRisk: Literal["low", "medium", "high", "not_applicable"]
    medicalRisk: Literal["low", "medium", "high"]
    recommendedProvider: Literal["video_agent", "direct_video", "local_compositor"]
    recommendationReason: str = Field(min_length=3, max_length=400)
    redundantWithShotId: str | None = Field(
        default=None, pattern=r"^shot-[0-9]{2}$"
    )


class StoryCritique(StrictModel):
    contractVersion: Literal["story-critic-v1"]
    decision: Literal["ready", "changes_required", "blocked"]
    overallRisk: Literal["low", "medium", "high"]
    summary: str = Field(min_length=3, max_length=500)
    issues: list[CriticIssue] = Field(max_length=40)
    shotAssessments: list[ShotAssessment] = Field(min_length=1, max_length=12)


class StoryCriticError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_story_critique(
    raw: Any,
    *,
    plan: dict[str, Any],
    allowed_provider_strategies: list[str],
) -> dict[str, Any]:
    try:
        critique = StoryCritique.model_validate(raw)
    except ValidationError as exc:
        raise StoryCriticError("STORY_CRITIC_SCHEMA_INVALID", str(exc)) from exc

    shot_ids = [str(shot["id"]) for shot in plan.get("shots") or []]
    shot_id_set = set(shot_ids)
    assessment_ids = [assessment.shotId for assessment in critique.shotAssessments]
    if assessment_ids != shot_ids:
        raise StoryCriticError(
            "STORY_CRITIC_SHOT_COVERAGE_INVALID",
            "A crítica deve avaliar todos os shots exatamente uma vez e na mesma ordem.",
        )
    allowed_providers = set(allowed_provider_strategies)
    for assessment in critique.shotAssessments:
        if assessment.recommendedProvider not in allowed_providers:
            raise StoryCriticError(
                "STORY_CRITIC_PROVIDER_UNKNOWN",
                "A crítica recomendou um provider fora das capabilities confirmadas.",
            )
        redundant = assessment.redundantWithShotId
        if redundant and (redundant not in shot_id_set or redundant == assessment.shotId):
            raise StoryCriticError(
                "STORY_CRITIC_REDUNDANCY_INVALID",
                "A referência de redundância não aponta para outro shot do plano.",
            )
    for issue in critique.issues:
        if set(issue.shotIds) - shot_id_set:
            raise StoryCriticError(
                "STORY_CRITIC_ISSUE_SHOT_UNKNOWN",
                "A crítica apontou um shot que não pertence ao plano.",
            )
        if issue.code == "SHOT_REDUNDANT" and len(set(issue.shotIds)) < 2:
            raise StoryCriticError(
                "STORY_CRITIC_REDUNDANCY_INVALID",
                "Redundância precisa apontar ao menos dois shots.",
            )

    has_blocking = any(issue.severity == "blocking" for issue in critique.issues)
    has_warning = any(issue.severity == "warning" for issue in critique.issues)
    expected_decision = "blocked" if has_blocking else "changes_required" if has_warning else "ready"
    if critique.decision != expected_decision:
        raise StoryCriticError(
            "STORY_CRITIC_DECISION_INCONSISTENT",
            "A decisão da crítica não corresponde à severidade dos problemas.",
        )
    return critique.model_dump(mode="json")


def configured_provider_rates(environment: dict[str, str]) -> dict[str, float | None]:
    def optional_rate(name: str) -> float | None:
        raw = str(environment.get(name) or "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if value >= 0 else None

    return {
        "video_agent": optional_rate("HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD"),
        "direct_video": optional_rate("HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD"),
        "local_compositor": 0.0,
    }


def estimate_story_budget(
    *,
    plan: dict[str, Any],
    brief: StoryBrief | dict[str, Any],
    provider_rates: dict[str, float | None],
) -> dict[str, Any]:
    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    counts = {"video_agent": 0, "direct_video": 0, "local_compositor": 0}
    for shot in plan.get("shots") or []:
        strategy = str(shot.get("providerStrategy") or "")
        jobs = int((shot.get("estimatedCost") or {}).get("heygenJobs") or 0)
        if strategy in counts:
            counts[strategy] += jobs
    initial_jobs = counts["video_agent"] + counts["direct_video"]
    max_regeneration_jobs = initial_jobs * parsed_brief.maxRegenerationsPerShot
    worst_case_jobs = initial_jobs + max_regeneration_jobs
    missing_rates = sorted(
        strategy
        for strategy in ("video_agent", "direct_video")
        if counts[strategy] and provider_rates.get(strategy) is None
    )
    initial_usd: float | None = None
    worst_case_usd: float | None = None
    if not missing_rates:
        initial_usd = round(
            sum(counts[strategy] * float(provider_rates.get(strategy) or 0) for strategy in counts),
            4,
        )
        worst_case_usd = round(
            initial_usd * (1 + parsed_brief.maxRegenerationsPerShot), 4
        )

    issues: list[dict[str, Any]] = []
    if initial_jobs > parsed_brief.maxHeyGenJobs:
        issues.append(
            {
                "code": "HEYGEN_JOB_LIMIT_EXCEEDED",
                "severity": "blocking",
                "message": f"O plano exige {initial_jobs} jobs e o limite é {parsed_brief.maxHeyGenJobs}.",
                "suggestedAction": "Reduza shots pagos ou aumente conscientemente o limite do briefing.",
            }
        )
    if parsed_brief.maxBudgetUsd is None:
        issues.append(
            {
                "code": "BUDGET_MAX_REQUIRED",
                "severity": "blocking",
                "message": "Defina um orçamento máximo em USD antes da aprovação.",
                "suggestedAction": "Informe o teto financeiro no Story Brief.",
            }
        )
    if missing_rates:
        issues.append(
            {
                "code": "BUDGET_RATE_UNAVAILABLE",
                "severity": "blocking",
                "message": "Falta custo estimado para: " + ", ".join(missing_rates) + ".",
                "suggestedAction": "Configure as estimativas por job no ambiente.",
            }
        )
    if (
        parsed_brief.maxBudgetUsd is not None
        and worst_case_usd is not None
        and worst_case_usd > parsed_brief.maxBudgetUsd
    ):
        issues.append(
            {
                "code": "BUDGET_EXCEEDED",
                "severity": "blocking",
                "message": (
                    f"O pior caso estimado é US$ {worst_case_usd:.2f}, acima do teto "
                    f"de US$ {parsed_brief.maxBudgetUsd:.2f}."
                ),
                "suggestedAction": "Reduza jobs ou regenerações, troque providers ou aumente o teto.",
            }
        )
    budget = {
        "initialHeyGenJobs": initial_jobs,
        "maxRegenerationJobs": max_regeneration_jobs,
        "worstCaseHeyGenJobs": worst_case_jobs,
        "maxHeyGenJobs": parsed_brief.maxHeyGenJobs,
        "maxRegenerationsPerShot": parsed_brief.maxRegenerationsPerShot,
        "providerJobCounts": counts,
        "providerRatesUsd": provider_rates,
        "estimatedInitialUsd": initial_usd,
        "estimatedWorstCaseUsd": worst_case_usd,
        "maxBudgetUsd": parsed_brief.maxBudgetUsd,
        "estimatedAnthropicCalls": 2,
        "issues": issues,
        "approvalEligible": not issues,
    }
    budget["budgetHash"] = canonical_hash(budget)
    return budget


def critic_cache_payload(
    *,
    plan: dict[str, Any],
    brief: StoryBrief | dict[str, Any],
    story_hash: str,
    story_revision: int,
    provider_capabilities_version: str,
    allowed_provider_strategies: list[str],
    model: str,
    force_key: str | None = None,
) -> dict[str, Any]:
    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    return {
        "storyCriticContractVersion": STORY_CRITIC_CONTRACT_VERSION,
        "storyCriticPromptVersion": STORY_CRITIC_PROMPT_VERSION,
        "storyContractVersion": plan.get("contractVersion"),
        "storyHash": story_hash,
        "storyRevision": story_revision,
        "storyBibleHash": canonical_hash(plan.get("storyBible")),
        "characterBibleHash": canonical_hash(plan.get("characterBible")),
        "visualBibleHash": canonical_hash(plan.get("visualBible")),
        "briefHash": canonical_hash(parsed_brief.model_dump(mode="json")),
        "providerCapabilitiesVersion": provider_capabilities_version,
        "allowedProviderStrategies": sorted(allowed_provider_strategies),
        "model": model,
        "forceKey": force_key,
    }


def build_story_critic_prompt(
    *,
    plan: dict[str, Any],
    brief: StoryBrief | dict[str, Any],
    allowed_provider_strategies: list[str],
) -> tuple[list[dict[str, Any]], str]:
    parsed_brief = brief if isinstance(brief, StoryBrief) else StoryBrief.model_validate(brief)
    rules = (
        "Você é o Claude Story Critic. Revise o Story Plan sem reescrever, citar ou completar "
        "a fala aprovada. Avalie arco narrativo, redundância, continuidade de personagem, "
        "figurino, ambiente e câmera, rigor histórico, assertividade visual médica, dificuldade "
        "e adequação do provider. Use somente os códigos, shotIds e providers do schema/contexto. "
        "suggestedAction deve corrigir direção visual, ordem ou provider; nunca conteúdo clínico. "
        "Avalie todos os shots exatamente uma vez e na ordem original. Não estime preço: o backend "
        "calcula orçamento deterministicamente. Não inclua texto fora do JSON."
    )
    system = [
        {"type": "text", "text": rules, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": "JSON SCHEMA CANÔNICO:\n"
            + json.dumps(STORY_CRITIC_SCHEMA, ensure_ascii=False, sort_keys=True),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    user = json.dumps(
        {
            "storyBrief": parsed_brief.model_dump(mode="json"),
            "storyPlan": plan,
            "allowedProviderStrategies": sorted(allowed_provider_strategies),
        },
        ensure_ascii=False,
        indent=2,
    )
    return system, user
