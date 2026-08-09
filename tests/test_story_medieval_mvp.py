from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api import server
from api.services.story_contract import StoryContractError, validate_story_plan
from tests.fixtures.story_medieval import (
    SPEECH,
    medieval_brief,
    medieval_plan,
    medieval_source,
)


def seed_medieval_story() -> tuple[dict, dict]:
    project = server._save_story_brief("script-medieval", medieval_brief())
    plan = medieval_plan()
    version = server._save_story_version(
        project_id=project["id"],
        plan=plan,
        source=medieval_source(),
        provider_capabilities_version="heygen-medieval-test-v1",
        request_fingerprint="medieval-mvp-" + "a" * 48,
        model="claude-story-test",
        shot_reviews=[
            {
                "shotId": shot["id"],
                "promptOverride": "",
                "lockIdentity": True,
                "lockWardrobe": True,
                "lockEnvironment": True,
                "approved": True,
            }
            for shot in plan["shots"]
        ],
        story_bible_approved=True,
    )
    return project, version


def medieval_authorization(project: dict, version: dict) -> dict:
    return {
        "project": project,
        "version": {**version, "plan": medieval_plan()},
        "brief": medieval_brief().model_dump(mode="json"),
        "source": medieval_source(),
        "providerContext": {
            "capabilities": {"capabilitiesVersion": "heygen-medieval-test-v1"},
            "providerCapabilitiesVersion": "heygen-medieval-test-v1",
            "providerStrategies": ["direct_video", "video_agent", "local_compositor"],
        },
        "budget": {
            "budgetHash": "b" * 64,
            "worstCaseHeyGenJobs": 12,
            "maxBudgetUsd": 50.0,
            "providerRatesUsd": {
                "direct_video": 3.0,
                "video_agent": 2.0,
                "local_compositor": 0.0,
            },
        },
        "approval": {"budgetHash": "b" * 64},
    }


def test_medieval_fixture_is_six_ordered_shots_bound_to_approved_speech() -> None:
    validated = validate_story_plan(
        medieval_plan(),
        brief=medieval_brief(),
        approved_speech=SPEECH,
        allowed_provider_strategies=["video_agent", "direct_video", "local_compositor"],
    )

    assert [shot["strategy"] for shot in validated["shots"]] == [
        "cinematic_broll",
        "avatar_anchor",
        "cinematic_broll",
        "avatar_anchor",
        "cinematic_broll",
        "avatar_anchor",
    ]
    assert [shot["order"] for shot in validated["shots"]] == list(range(1, 7))
    assert all(len(shot["heygenPrompt"]) >= 40 for shot in validated["shots"])
    with pytest.raises(StoryContractError) as stale:
        validate_story_plan(
            medieval_plan(),
            brief=medieval_brief(),
            approved_speech=SPEECH + " Agora.",
            allowed_provider_strategies=["video_agent", "direct_video", "local_compositor"],
        )
    assert stale.value.code == "SPEECH_COVERAGE_INCOMPLETE"


def test_story_director_accepts_fixture_in_one_mocked_call_without_heygen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "OPERATIONAL_DB", tmp_path / "operations.db")
    message = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=300,
            output_tokens=500,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=100,
        )
    )
    heygen = MagicMock()
    with (
        patch.dict(server.os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False),
        patch.object(
            server,
            "_story_director_model_call",
            return_value=(message, json.dumps(medieval_plan(), ensure_ascii=False)),
        ) as anthropic,
        patch.object(server, "_run_heygen_json", heygen),
    ):
        result = server._run_story_director(
            brief=medieval_brief(),
            source=medieval_source(),
            provider_context={
                "providerCapabilitiesVersion": "heygen-medieval-test-v1",
                "providerStrategies": ["video_agent", "direct_video", "local_compositor"],
            },
            model="claude-story-test",
            repair_model="claude-repair-test",
        )

    assert len(result["plan"]["shots"]) == 6
    assert result["retryCount"] == 0
    assert anthropic.call_count == 1
    heygen.assert_not_called()


def test_six_medieval_shots_submit_one_at_a_time_with_provider_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "OPERATIONAL_DB", tmp_path / "operations.db")
    project, version = seed_medieval_story()
    context = medieval_authorization(project, version)
    provider = MagicMock(
        side_effect=[{"session_id": f"provider-shot-{index:02d}"} for index in range(1, 7)]
    )
    real_transport = MagicMock()
    results = []
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
        patch.object(server, "_run_heygen_json", real_transport),
    ):
        for shot in server._story_shots(version["id"]):
            results.append(
                server.generate_story_shot(
                    shot["id"],
                    server.StoryShotGenerateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedPromptHash=shot["promptHash"],
                        expectedBudgetHash="b" * 64,
                        idempotencyKey=f"medieval-{shot['shotId']}-revision-1",
                        confirmed=True,
                    ),
                )
            )

    assert [result["generation"]["storyShotId"] for result in results] == [
        shot["id"] for shot in server._story_shots(version["id"])
    ]
    assert all(result["generation"]["status"] == "submitted" for result in results)
    assert provider.call_count == 6
    real_transport.assert_not_called()
