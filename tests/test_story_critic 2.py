from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch

import pytest

from api import server
from api.services.story_contract import STORY_CONTRACT_VERSION, StoryBrief
from api.services.story_critic import (
    STORY_CRITIC_CONTRACT_VERSION,
    StoryCriticError,
    estimate_story_budget,
    validate_story_critique,
)


SPEECH = "A obesidade é uma condição complexa e merece avaliação individual por profissional qualificado."
SPEECH_HASH = server.hash_text(SPEECH)


def story_brief(*, max_budget: float | None = 20) -> StoryBrief:
    return StoryBrief(
        educationalGoal="Explicar o tema com apoio visual responsável.",
        durationSeconds=20,
        maxHeyGenJobs=2,
        maxRegenerationsPerShot=1,
        maxBudgetUsd=max_budget,
        characterId="doctor-main",
        lookId="look-main",
    )


def plan() -> dict:
    return {
        "contractVersion": STORY_CONTRACT_VERSION,
        "storyBible": {
            "premise": "Uma progressão visual educativa e cuidadosa.",
            "educationalGoal": story_brief().educationalGoal,
            "narrativeArc": {
                "opening": "Abertura",
                "development": "Desenvolvimento",
                "turn": "Virada",
                "ending": "Conclusão",
            },
            "historicalSetting": {
                "period": "",
                "location": "",
                "accuracyMode": "not_applicable",
            },
        },
        "characterBible": {
            "characterId": "doctor-main",
            "lookId": "look-main",
            "identityRule": "Preservar identidade",
            "voiceRule": "Preservar voz",
            "wardrobe": {"base": "neutro", "accessories": [], "colors": ["grafite"]},
            "forbiddenChanges": ["trocar rosto"],
        },
        "visualBible": {
            "palette": "neutra",
            "lighting": "suave",
            "cameraStyle": "documental",
            "texture": "realista",
            "forbiddenAnachronisms": [],
        },
        "medicalAssertions": [],
        "shots": [
            {
                "id": "shot-01",
                "providerStrategy": "video_agent",
                "estimatedCost": {"heygenJobs": 1, "anthropicCalls": 0},
            },
            {
                "id": "shot-02",
                "providerStrategy": "direct_video",
                "estimatedCost": {"heygenJobs": 1, "anthropicCalls": 0},
            },
        ],
    }


def valid_critique() -> dict:
    return {
        "contractVersion": STORY_CRITIC_CONTRACT_VERSION,
        "decision": "ready",
        "overallRisk": "low",
        "summary": "Plano coerente e pronto para aprovação humana.",
        "issues": [],
        "shotAssessments": [
            {
                "shotId": "shot-01",
                "difficulty": "medium",
                "continuityRisk": "low",
                "historicalRisk": "not_applicable",
                "medicalRisk": "low",
                "recommendedProvider": "video_agent",
                "recommendationReason": "Mantém o movimento visual planejado.",
                "redundantWithShotId": None,
            },
            {
                "shotId": "shot-02",
                "difficulty": "low",
                "continuityRisk": "low",
                "historicalRisk": "not_applicable",
                "medicalRisk": "low",
                "recommendedProvider": "direct_video",
                "recommendationReason": "Preserva o avatar anchor com previsibilidade.",
                "redundantWithShotId": None,
            },
        ],
    }


def provider_capabilities() -> dict:
    return {
        "capabilitiesVersion": "heygen-test-v1",
        "videoAgent": {"supported": True},
        "directVideo": {"supported": True},
    }


def editor_state() -> dict:
    return {
        "scriptRevision": 3,
        "finalSpeechHash": SPEECH_HASH,
        "approvedScriptRevision": 3,
        "approvedFinalSpeechHash": SPEECH_HASH,
        "contractVersion": "script-editor-v1",
        "humanReviewApproved": True,
    }


def seed_story(brief: StoryBrief | None = None) -> tuple[dict, dict]:
    selected_brief = brief or story_brief()
    project = server._save_story_brief("script-story", selected_brief)
    version = server._save_story_version(
        project_id=project["id"],
        plan=plan(),
        source={
            "scriptRevision": 3,
            "finalSpeechHash": SPEECH_HASH,
            "scriptContractVersion": "script-editor-v1",
        },
        provider_capabilities_version="heygen-test-v1",
        request_fingerprint="d" * 64,
        model="claude-story-test",
        shot_reviews=[
            {
                "shotId": "shot-01",
                "promptOverride": "",
                "lockIdentity": True,
                "lockWardrobe": True,
                "lockEnvironment": False,
                "approved": True,
            },
            {
                "shotId": "shot-02",
                "promptOverride": "",
                "lockIdentity": True,
                "lockWardrobe": True,
                "lockEnvironment": False,
                "approved": True,
            },
        ],
        story_bible_approved=True,
    )
    return project, version


def message() -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=60,
            cache_read_input_tokens=20,
            cache_creation_input_tokens=0,
        )
    )


def common_patches():
    return (
        patch.object(
            server,
            "_find_script",
            return_value={
                "id": "script-story",
                "status": "aprovado_clinicamente",
                "textoFalado": SPEECH,
            },
        ),
        patch.object(server, "_script_editor_state", return_value=editor_state()),
        patch.object(server, "_heygen_capabilities", return_value=provider_capabilities()),
    )


def test_critic_contract_requires_complete_shot_coverage_and_stable_providers() -> None:
    result = validate_story_critique(
        valid_critique(),
        plan=plan(),
        allowed_provider_strategies=["video_agent", "direct_video", "local_compositor"],
    )
    assert [item["shotId"] for item in result["shotAssessments"]] == [
        "shot-01",
        "shot-02",
    ]

    invalid = valid_critique()
    invalid["shotAssessments"][1]["shotId"] = "shot-03"
    with pytest.raises(StoryCriticError) as raised:
        validate_story_critique(
            invalid,
            plan=plan(),
            allowed_provider_strategies=["video_agent", "direct_video"],
        )
    assert raised.value.code == "STORY_CRITIC_SHOT_COVERAGE_INVALID"


def test_budget_is_local_and_blocks_missing_rates_or_ceiling() -> None:
    missing = estimate_story_budget(
        plan=plan(),
        brief=story_brief(max_budget=None),
        provider_rates={"video_agent": None, "direct_video": None, "local_compositor": 0},
    )
    assert {issue["code"] for issue in missing["issues"]} == {
        "BUDGET_MAX_REQUIRED",
        "BUDGET_RATE_UNAVAILABLE",
    }
    exceeded = estimate_story_budget(
        plan=plan(),
        brief=story_brief(max_budget=8),
        provider_rates={"video_agent": 2, "direct_video": 3, "local_compositor": 0},
    )
    assert exceeded["estimatedInitialUsd"] == 5
    assert exceeded["estimatedWorstCaseUsd"] == 10
    assert exceeded["issues"][0]["code"] == "BUDGET_EXCEEDED"


def test_critique_cache_then_human_budget_approval_unlocks_production() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            _project, version = seed_story()
            payload = server.StoryCritiqueCreateIn(
                expectedStoryHash=version["storyHash"],
                expectedProviderCapabilitiesVersion="heygen-test-v1",
                confirmed=True,
            )
            find_script, state, capabilities = common_patches()
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_CRITIC_MODEL": "claude-critic-test",
                        "HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD": "2",
                        "HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD": "3",
                    },
                    clear=False,
                ),
                find_script,
                state,
                capabilities,
                patch.object(
                    server,
                    "_story_critic_model_call",
                    return_value=(message(), json.dumps(valid_critique(), ensure_ascii=False)),
                ) as critic_call,
                patch.object(server, "_run_heygen_json") as heygen,
            ):
                first = server.create_story_version_critique(version["id"], payload)
                second = server.create_story_version_critique(version["id"], payload)
                critique = first["critique"]
                with pytest.raises(server.HTTPException) as blocked:
                    server._authorize_story_production(version["id"])
                approval = server.approve_story_version(
                    version["id"],
                    server.StoryPlanApprovalIn(
                        critiqueId=critique["id"],
                        expectedStoryHash=version["storyHash"],
                        expectedBudgetHash=critique["budget"]["budgetHash"],
                        confirmed=True,
                    ),
                )
                authorized = server._authorize_story_production(version["id"])

            assert critic_call.call_count == 1
            assert heygen.call_count == 0
            assert first["critique"]["id"] == second["critique"]["id"]
            assert second["cacheHit"] is True
            assert blocked.value.detail["code"] == "STORY_BUDGET_APPROVAL_REQUIRED"
            assert approval["version"]["approved"] is True
            assert authorized["budget"]["approvalEligible"] is True
        finally:
            server.OPERATIONAL_DB = original_database


def test_valid_recritique_creates_a_new_revision_without_deleting_the_previous_one() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            _project, version = seed_story()
            environment = {
                "ANTHROPIC_API_KEY": "test-key",
                "ANTHROPIC_STORY_CRITIC_MODEL": "claude-critic-test",
                "HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD": "2",
                "HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD": "3",
            }
            find_script, state, capabilities = common_patches()
            with (
                patch.dict(server.os.environ, environment, clear=False),
                find_script,
                state,
                capabilities,
                patch.object(
                    server,
                    "_story_critic_model_call",
                    return_value=(message(), json.dumps(valid_critique())),
                ),
            ):
                first = server.create_story_version_critique(
                    version["id"],
                    server.StoryCritiqueCreateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedProviderCapabilitiesVersion="heygen-test-v1",
                        confirmed=True,
                    ),
                )
                second = server.create_story_version_critique(
                    version["id"],
                    server.StoryCritiqueCreateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedProviderCapabilitiesVersion="heygen-test-v1",
                        confirmed=True,
                        forceNewVersion=True,
                        idempotencyKey="critique-redo-valid-01",
                    ),
                )

            assert first["critique"]["critiqueRevision"] == 1
            assert second["critique"]["critiqueRevision"] == 2
            assert first["critique"]["id"] != second["critique"]["id"]
            current = server._story_version(version["id"])
            assert current is not None
            assert current["activeCritiqueId"] == second["critique"]["id"]
            conn = server._ai_db()
            try:
                assert conn.execute("SELECT COUNT(*) FROM story_critiques").fetchone()[0] == 2
            finally:
                conn.close()
        finally:
            server.OPERATIONAL_DB = original_database


def test_plan_above_budget_cannot_be_approved() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            _project, version = seed_story(story_brief(max_budget=8))
            find_script, state, capabilities = common_patches()
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_CRITIC_MODEL": "claude-critic-test",
                        "HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD": "2",
                        "HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD": "3",
                    },
                    clear=False,
                ),
                find_script,
                state,
                capabilities,
                patch.object(
                    server,
                    "_story_critic_model_call",
                    return_value=(message(), json.dumps(valid_critique())),
                ),
            ):
                result = server.create_story_version_critique(
                    version["id"],
                    server.StoryCritiqueCreateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedProviderCapabilitiesVersion="heygen-test-v1",
                        confirmed=True,
                    ),
                )
                with pytest.raises(server.HTTPException) as raised:
                    server.approve_story_version(
                        version["id"],
                        server.StoryPlanApprovalIn(
                            critiqueId=result["critique"]["id"],
                            expectedStoryHash=version["storyHash"],
                            expectedBudgetHash=result["critique"]["budget"]["budgetHash"],
                            confirmed=True,
                        ),
                    )

            assert raised.value.status_code == 422
            assert raised.value.detail["code"] == "BUDGET_EXCEEDED"
        finally:
            server.OPERATIONAL_DB = original_database


def test_invalid_new_critique_preserves_previous_revision() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            _project, version = seed_story()
            find_script, state, capabilities = common_patches()
            environment = {
                "ANTHROPIC_API_KEY": "test-key",
                "ANTHROPIC_STORY_CRITIC_MODEL": "claude-critic-test",
                "HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD": "2",
                "HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD": "3",
            }
            with (
                patch.dict(server.os.environ, environment, clear=False),
                find_script,
                state,
                capabilities,
                patch.object(
                    server,
                    "_story_critic_model_call",
                    return_value=(message(), json.dumps(valid_critique())),
                ),
            ):
                first = server.create_story_version_critique(
                    version["id"],
                    server.StoryCritiqueCreateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedProviderCapabilitiesVersion="heygen-test-v1",
                        confirmed=True,
                    ),
                )
            invalid = valid_critique()
            invalid["shotAssessments"] = []
            find_script, state, capabilities = common_patches()
            with (
                patch.dict(server.os.environ, environment, clear=False),
                find_script,
                state,
                capabilities,
                patch.object(
                    server,
                    "_story_critic_model_call",
                    return_value=(message(), json.dumps(invalid)),
                ) as critic_call,
            ):
                with pytest.raises(server.HTTPException) as raised:
                    server.create_story_version_critique(
                        version["id"],
                        server.StoryCritiqueCreateIn(
                            expectedStoryHash=version["storyHash"],
                            expectedProviderCapabilitiesVersion="heygen-test-v1",
                            confirmed=True,
                            forceNewVersion=True,
                            idempotencyKey="critique-redo-01",
                        ),
                    )

            assert raised.value.status_code == 502
            assert critic_call.call_count == 2
            current = server._story_version(version["id"])
            assert current is not None
            assert current["activeCritiqueId"] == first["critique"]["id"]
            conn = server._ai_db()
            try:
                assert conn.execute("SELECT COUNT(*) FROM story_critiques").fetchone()[0] == 1
            finally:
                conn.close()
        finally:
            server.OPERATIONAL_DB = original_database
