from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api import server
from tests.test_story_director import SPEECH, brief, source_context, valid_plan


@pytest.fixture
def story_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database = tmp_path / "operations.db"
    monkeypatch.setattr(server, "OPERATIONAL_DB", database)
    return database


def seed_story(*, approved_shots: set[str] | None = None) -> tuple[dict, dict]:
    approved = approved_shots if approved_shots is not None else {"shot-01", "shot-02"}
    selected_brief = brief().model_copy(
        update={"maxHeyGenJobs": 4, "maxRegenerationsPerShot": 1, "maxBudgetUsd": 20}
    )
    project = server._save_story_brief("script-story", selected_brief)
    version = server._save_story_version(
        project_id=project["id"],
        plan=valid_plan(),
        source=source_context(),
        provider_capabilities_version="heygen-test-v1",
        request_fingerprint="shot-generation-test-" + "a" * 40,
        model="claude-story-test",
        shot_reviews=[
            {
                "shotId": shot_id,
                "promptOverride": "",
                "lockIdentity": True,
                "lockWardrobe": True,
                "lockEnvironment": True,
                "approved": shot_id in approved,
            }
            for shot_id in ("shot-01", "shot-02")
        ],
        story_bible_approved=True,
    )
    return project, version


def authorization(
    project: dict,
    version: dict,
    *,
    providers: list[str] | None = None,
    max_budget: float = 20,
    worst_case_jobs: int = 4,
) -> dict:
    selected_brief = brief().model_copy(
        update={"maxHeyGenJobs": 4, "maxRegenerationsPerShot": 1, "maxBudgetUsd": max_budget}
    )
    budget_hash = "b" * 64
    return {
        "project": project,
        "version": {**version, "plan": valid_plan()},
        "brief": selected_brief.model_dump(mode="json"),
        "source": {
            **source_context(),
            "speech": SPEECH,
            "script": {"id": "script-story", "status": "aprovado_clinicamente"},
        },
        "providerContext": {
            "capabilities": {"capabilitiesVersion": "heygen-test-v1"},
            "providerCapabilitiesVersion": "heygen-test-v1",
            "providerStrategies": providers
            if providers is not None
            else ["direct_video", "video_agent", "local_compositor"],
        },
        "budget": {
            "budgetHash": budget_hash,
            "worstCaseHeyGenJobs": worst_case_jobs,
            "maxBudgetUsd": max_budget,
            "providerRatesUsd": {
                "direct_video": 3.0,
                "video_agent": 2.0,
                "local_compositor": 0.0,
            },
        },
        "approval": {"budgetHash": budget_hash},
    }


def payload(shot: dict, version: dict, key: str, *, regenerate: bool = False):
    return server.StoryShotGenerateIn(
        expectedStoryHash=version["storyHash"],
        expectedPromptHash=shot["promptHash"],
        expectedBudgetHash="b" * 64,
        idempotencyKey=key,
        regenerate=regenerate,
        confirmed=True,
    )


def error_code(exc: pytest.ExceptionInfo[server.HTTPException]) -> str:
    return str(exc.value.detail["code"])


def test_unapproved_shot_never_reaches_provider(story_database: Path) -> None:
    project, version = seed_story(approved_shots={"shot-02"})
    shot = server._story_shots(version["id"])[0]
    provider = MagicMock()
    with (
        patch.object(server, "_authorize_story_production", return_value=authorization(project, version)),
        patch.object(server, "_story_provider_submit", provider),
        pytest.raises(server.HTTPException) as raised,
    ):
        server.generate_story_shot(shot["id"], payload(shot, version, "unapproved-shot"))

    assert error_code(raised) == "STORY_SHOT_NOT_APPROVED"
    provider.assert_not_called()


def test_missing_capability_blocks_before_provider(story_database: Path) -> None:
    project, version = seed_story()
    shot = server._story_shots(version["id"])[1]
    provider = MagicMock()
    context = authorization(project, version, providers=["direct_video", "local_compositor"])
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
        pytest.raises(server.HTTPException) as raised,
    ):
        server.generate_story_shot(shot["id"], payload(shot, version, "missing-capability"))

    assert error_code(raised) == "STORY_SHOT_CAPABILITY_UNAVAILABLE"
    provider.assert_not_called()


def test_budget_limit_blocks_before_provider(story_database: Path) -> None:
    project, version = seed_story()
    shot = server._story_shots(version["id"])[1]
    provider = MagicMock()
    context = authorization(project, version, max_budget=1)
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
        pytest.raises(server.HTTPException) as raised,
    ):
        server.generate_story_shot(shot["id"], payload(shot, version, "over-budget"))

    assert error_code(raised) == "STORY_BUDGET_EXCEEDED"
    provider.assert_not_called()


def test_same_idempotency_key_submits_exact_prompt_only_once(story_database: Path) -> None:
    project, version = seed_story()
    shot = server._story_shots(version["id"])[1]
    context = authorization(project, version)
    provider = MagicMock(return_value={"session_id": "provider-shot-02"})
    request = payload(shot, version, "stable-shot-02")
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
    ):
        first = server.generate_story_shot(shot["id"], request)
        second = server.generate_story_shot(shot["id"], request)

    assert first["generation"]["status"] == "submitted"
    assert second["deduplicated"] is True
    assert second["generation"]["id"] == first["generation"]["id"]
    assert provider.call_count == 1
    assert provider.call_args.args[1]["prompt"] == valid_plan()["shots"][1]["heygenPrompt"]


def test_regeneration_updates_only_selected_shot(story_database: Path) -> None:
    project, version = seed_story()
    shots = server._story_shots(version["id"])
    context = authorization(project, version, max_budget=20, worst_case_jobs=4)
    provider = MagicMock(side_effect=[{"session_id": "job-01"}, {"session_id": "job-02"}, {"session_id": "job-02b"}])
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
    ):
        generated_first = server.generate_story_shot(
            shots[0]["id"], payload(shots[0], version, "shot-01-revision-1")
        )["generation"]
        generated_second = server.generate_story_shot(
            shots[1]["id"], payload(shots[1], version, "shot-02-revision-1")
        )["generation"]
        server._set_story_generation(generated_first["id"], status="completed")
        server._set_story_generation(generated_second["id"], status="completed")
        regenerated_second = server.generate_story_shot(
            shots[1]["id"],
            payload(shots[1], version, "shot-02-revision-2", regenerate=True),
        )["generation"]

    saved = server._story_shots(version["id"])
    assert saved[0]["currentGenerationId"] == generated_first["id"]
    assert saved[0]["shotRevision"] == 1
    assert saved[1]["currentGenerationId"] == regenerated_second["id"]
    assert saved[1]["shotRevision"] == 2
    assert saved[1]["regenerationCount"] == 1
    assert provider.call_count == 3


def test_uncertain_submission_cannot_be_repeated_with_new_key(story_database: Path) -> None:
    project, version = seed_story()
    shot = server._story_shots(version["id"])[1]
    context = authorization(project, version)
    provider = MagicMock(side_effect=TimeoutError("provider timeout"))
    with (
        patch.object(server, "_authorize_story_production", return_value=context),
        patch.object(server, "_story_provider_submit", provider),
    ):
        failed = server.generate_story_shot(
            shot["id"], payload(shot, version, "uncertain-shot-02")
        )
        with pytest.raises(server.HTTPException) as raised:
            server.generate_story_shot(
                shot["id"],
                payload(shot, version, "uncertain-shot-02-new", regenerate=True),
            )

    assert failed["ok"] is False
    assert failed["generation"]["retrySafe"] is False
    assert error_code(raised) == "STORY_SHOT_SUBMISSION_UNCERTAIN"
    assert provider.call_count == 1
