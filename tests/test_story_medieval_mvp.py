from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api import server
from api.services.story_contract import StoryContractError, validate_story_plan
from api.services.story_critic import STORY_CRITIC_CONTRACT_VERSION
from tests.fixtures.story_medieval import (
    SPEECH,
    SPEECH_HASH,
    medieval_brief,
    medieval_plan,
    medieval_source,
)
from tests.test_story_composition import mock_video


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


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is required")
def test_medieval_critical_path_with_mocks_outputs_final_mp4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir=server.ROOT / "data") as temporary:
        root = Path(temporary)
        monkeypatch.setattr(server, "OPERATIONAL_DB", root / "operations.db")
        monkeypatch.setattr(server, "COMPOSED_VIDEO_OUTPUTS", root / "composed")
        source = medieval_source()
        provider_context = {
            "capabilities": {
                "capabilitiesVersion": "heygen-medieval-test-v1",
                "videoAgent": {"supported": True},
                "directVideo": {"supported": True},
            },
            "providerCapabilitiesVersion": "heygen-medieval-test-v1",
            "providerStrategies": ["video_agent", "direct_video", "local_compositor"],
        }
        message = SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=300,
                output_tokens=500,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
        )
        critique_payload = {
            "contractVersion": STORY_CRITIC_CONTRACT_VERSION,
            "decision": "ready",
            "overallRisk": "low",
            "summary": "A história medieval está coerente e pronta para produção.",
            "issues": [],
            "shotAssessments": [
                {
                    "shotId": shot["id"],
                    "difficulty": "medium",
                    "continuityRisk": "low",
                    "historicalRisk": "low",
                    "medicalRisk": "low",
                    "recommendedProvider": shot["providerStrategy"],
                    "recommendationReason": "A estratégia preserva a intenção aprovada do shot.",
                    "redundantWithShotId": None,
                }
                for shot in medieval_plan()["shots"]
            ],
        }
        provider = MagicMock(
            side_effect=[
                {"session_id": f"provider-shot-{index:02d}"} for index in range(1, 8)
            ]
        )
        real_heygen_transport = MagicMock()
        environment = {
            "ANTHROPIC_API_KEY": "mocked-test-key",
            "ANTHROPIC_STORY_MODEL": "claude-story-mock",
            "ANTHROPIC_STORY_CRITIC_MODEL": "claude-critic-mock",
            "HEYGEN_VIDEO_AGENT_ESTIMATED_JOB_USD": "2",
            "HEYGEN_DIRECT_VIDEO_ESTIMATED_JOB_USD": "3",
        }

        with (
            patch.dict(server.os.environ, environment, clear=False),
            patch.object(server, "_story_source_context", return_value=source),
            patch.object(server, "_story_capability_context", return_value=provider_context),
            patch.object(
                server,
                "_story_director_model_call",
                return_value=(message, json.dumps(medieval_plan(), ensure_ascii=False)),
            ) as director,
            patch.object(
                server,
                "_story_critic_model_call",
                return_value=(message, json.dumps(critique_payload, ensure_ascii=False)),
            ) as critic,
            patch.object(server, "_story_provider_submit", provider),
            patch.object(server, "_run_heygen_json", real_heygen_transport),
        ):
            saved_brief = server.save_script_story_brief(
                "script-medieval",
                server.StoryBriefSaveIn(
                    brief=medieval_brief(),
                    expectedScriptRevision=7,
                    expectedFinalSpeechHash=SPEECH_HASH,
                    scriptContractVersion="script-editor-v1",
                ),
            )
            planned = server.create_script_story_plan(
                "script-medieval",
                server.StoryPlanCreateIn(
                    brief=medieval_brief(),
                    expectedScriptRevision=7,
                    expectedFinalSpeechHash=SPEECH_HASH,
                    scriptContractVersion="script-editor-v1",
                    expectedProviderCapabilitiesVersion="heygen-medieval-test-v1",
                    confirmed=True,
                ),
            )
            assert saved_brief["project"]["brief"]["period"] == "Europa medieval, século XIII"
            assert planned["version"]["plan"]["storyBible"]["historicalSetting"][
                "location"
            ] == "Feira pública e botica de uma vila"
            assert len(planned["version"]["plan"]["shots"]) == 6

            edited_plan = json.loads(json.dumps(planned["version"]["plan"]))
            edited_plan["shots"][2]["action"] = (
                "Detalhes de mãos pesando grãos enquanto o médico cruza o quadro ao fundo"
            )
            revised = server.revise_story_version(
                planned["version"]["id"],
                server.StoryPlanRevisionIn(
                    expectedStoryHash=planned["version"]["storyHash"],
                    expectedProviderCapabilitiesVersion="heygen-medieval-test-v1",
                    plan=edited_plan,
                    shotReviews=[
                        server.StoryShotReviewIn(
                            shotId=shot["id"],
                            lockIdentity=True,
                            lockWardrobe=True,
                            lockEnvironment=True,
                            approved=True,
                        )
                        for shot in edited_plan["shots"]
                    ],
                    storyBibleApproved=True,
                    idempotencyKey="medieval-shot-edit-01",
                ),
            )
            version = revised["version"]
            assert version["storyRevision"] == 2
            assert version["plan"]["shots"][2]["action"] == edited_plan["shots"][2]["action"]
            assert version["storyBibleApproved"] is True
            assert all(shot["controls"]["approved"] for shot in version["shots"])

            reviewed = server.create_story_version_critique(
                version["id"],
                server.StoryCritiqueCreateIn(
                    expectedStoryHash=version["storyHash"],
                    expectedProviderCapabilitiesVersion="heygen-medieval-test-v1",
                    confirmed=True,
                ),
            )
            budget = reviewed["critique"]["budget"]
            assert budget["initialHeyGenJobs"] == 6
            assert budget["worstCaseHeyGenJobs"] == 12
            assert budget["estimatedWorstCaseUsd"] == 30
            assert budget["approvalEligible"] is True
            approval = server.approve_story_version(
                version["id"],
                server.StoryPlanApprovalIn(
                    critiqueId=reviewed["critique"]["id"],
                    expectedStoryHash=version["storyHash"],
                    expectedBudgetHash=budget["budgetHash"],
                    confirmed=True,
                ),
            )
            assert approval["version"]["approved"] is True
            assert approval["version"]["budgetApproved"] is True

            initial_generation_ids: dict[str, str] = {}
            colors = ["red", "green", "blue", "yellow", "magenta", "cyan"]
            for index, shot in enumerate(server._story_shots(version["id"])):
                generated = server.generate_story_shot(
                    shot["id"],
                    server.StoryShotGenerateIn(
                        expectedStoryHash=version["storyHash"],
                        expectedPromptHash=shot["promptHash"],
                        expectedBudgetHash=budget["budgetHash"],
                        idempotencyKey=f"medieval-{shot['shotId']}-revision-1",
                        confirmed=True,
                    ),
                )["generation"]
                shot_path = root / f"{shot['shotId']}-revision-1.mp4"
                mock_video(shot_path, colors[index], 300 + index * 50)
                server._set_story_generation(
                    generated["id"],
                    status="completed",
                    output_path=str(shot_path.relative_to(server.ROOT)),
                )
                initial_generation_ids[shot["shotId"]] = generated["id"]

            selected = server._story_shots(version["id"])[2]
            regenerated = server.generate_story_shot(
                selected["id"],
                server.StoryShotGenerateIn(
                    expectedStoryHash=version["storyHash"],
                    expectedPromptHash=selected["promptHash"],
                    expectedBudgetHash=budget["budgetHash"],
                    idempotencyKey="medieval-shot-03-revision-2",
                    regenerate=True,
                    confirmed=True,
                ),
            )["generation"]
            regenerated_path = root / "shot-03-revision-2.mp4"
            mock_video(regenerated_path, "white", 750)
            server._set_story_generation(
                regenerated["id"],
                status="completed",
                output_path=str(regenerated_path.relative_to(server.ROOT)),
            )
            final_shots = server._story_shots(version["id"])
            assert final_shots[2]["currentGenerationId"] == regenerated["id"]
            assert final_shots[2]["shotRevision"] == 2
            assert all(
                shot["currentGenerationId"] == initial_generation_ids[shot["shotId"]]
                for shot in final_shots
                if shot["shotId"] != "shot-03"
            )

            narration = root / "medieval-narration.mp4"
            mock_video(narration, "black", 900)
            server._job_store().upsert(
                "video",
                {
                    "id": "base-medieval-narration",
                    "scriptId": "script-medieval",
                    "status": "pronto",
                    "provider": "local",
                    "progresso": 100,
                    "criadoEm": "2026-08-09T00:00:00+00:00",
                    "atualizadoEm": "2026-08-09T00:00:01+00:00",
                    "outputPath": str(narration.relative_to(server.ROOT)),
                },
            )
            composed = server.compose_story_version(
                version["id"],
                server.StoryComposeIn(
                    expectedStoryHash=version["storyHash"],
                    baseVideoJobId="base-medieval-narration",
                    confirmed=True,
                ),
            )["job"]

        final_path = server.ROOT / composed["outputPath"]
        assert composed["status"] == "pronto"
        assert composed["shotCount"] == 6
        assert composed["narrationPolicy"] == "base_audio_continuous"
        assert composed["storyShots"][2]["generationId"] == regenerated["id"]
        assert final_path.is_file()
        assert final_path.suffix == ".mp4"
        assert server._probe_video_duration(final_path) > 0
        assert director.call_count == 1
        assert critic.call_count == 1
        assert provider.call_count == 7
        real_heygen_transport.assert_not_called()
