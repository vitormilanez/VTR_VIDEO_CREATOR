from __future__ import annotations

import pytest

from api import server
from api.services.podcast_generation import (
    build_podcast_generation_result,
    podcast_spoken_text,
)


def podcast_plan() -> dict:
    return {
        "orientation": "portrait",
        "participants": [
            {
                "id": "a",
                "name": "Apresentador",
                "avatarId": "avatar-a",
                "voiceId": "voice-a",
            },
            {
                "id": "b",
                "name": "Especialista",
                "avatarId": "avatar-b",
                "voiceId": "voice-b",
            },
        ],
        "turns": [
            {"id": "turn-1", "speakerId": "a", "text": "O que precisamos entender?"},
            {"id": "turn-2", "speakerId": "b", "text": "Primeiro, vamos separar os fatos."},
            {"id": "turn-3", "speakerId": "a", "text": "E qual é o cuidado principal?"},
        ],
    }


def test_builds_one_avatar_and_voice_pair_per_turn() -> None:
    result = build_podcast_generation_result(
        script_id="script-1",
        podcast_plan=podcast_plan(),
        speech_mode="natural",
        voice_mood="confident",
    )

    assert result.turn_count == 3
    assert [request.speaker_id for request in result.requests] == ["a", "b", "a"]
    assert [request.avatar_id for request in result.requests] == [
        "avatar-a",
        "avatar-b",
        "avatar-a",
    ]
    assert [request.voice_id for request in result.requests] == [
        "voice-a",
        "voice-b",
        "voice-a",
    ]
    assert result.to_dict()["estimatedCalls"] == 3


def test_rejects_reusing_the_same_voice_for_both_participants() -> None:
    plan = podcast_plan()
    plan["participants"][1]["voiceId"] = "voice-a"

    with pytest.raises(ValueError, match="voz diferente"):
        build_podcast_generation_result(script_id="script-1", podcast_plan=plan)


def test_requires_both_participants_to_speak() -> None:
    plan = podcast_plan()
    for turn in plan["turns"]:
        turn["speakerId"] = "a"

    with pytest.raises(ValueError, match="dois participantes"):
        build_podcast_generation_result(script_id="script-1", podcast_plan=plan)


def test_canonical_dialogue_keeps_timeline_order_without_speaker_labels() -> None:
    assert podcast_spoken_text(podcast_plan()) == (
        "O que precisamos entender?\n\n"
        "Primeiro, vamos separar os fatos.\n\n"
        "E qual é o cuidado principal?"
    )


def test_podcast_plan_persists_separately_from_scene_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "OPERATIONAL_DB", tmp_path / "operations.db")
    saved = server._save_podcast_plan(
        "script-1",
        {
            **podcast_plan(),
            "title": "Conversa educativa",
            "captions": True,
            "musicTrackId": None,
        },
    )

    assert saved["transitionStyle"] == "hard_cut"
    assert server._podcast_plan("script-1") == saved
    assert server._scene_plan("script-1") is None


def test_ready_podcast_jobs_require_matching_cast_and_one_batch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "OPERATIONAL_DB", tmp_path / "operations.db")
    plan = podcast_plan()

    def save_job(
        job_id: str,
        turn_id: str,
        speaker_id: str,
        avatar_id: str,
        voice_id: str,
        batch_id: str,
    ) -> None:
        server._job_store().upsert(
            "video",
            {
                "id": job_id,
                "scriptId": "script-1",
                "status": "pronto",
                "provider": "heygen",
                "progresso": 100,
                "criadoEm": "2026-08-17T12:00:00+00:00",
                "atualizadoEm": "2026-08-17T12:00:00+00:00",
                "isScene": True,
                "isPodcastScene": True,
                "sceneBatchId": batch_id,
                "sceneId": turn_id,
                "speakerId": speaker_id,
                "productionSettings": {
                    "speakerId": speaker_id,
                    "avatarId": avatar_id,
                    "voiceId": voice_id,
                },
            },
        )

    save_job("turn-1", "turn-1", "a", "avatar-a", "voice-a", "batch-1")
    save_job("turn-2", "turn-2", "b", "avatar-b", "voice-b", "batch-1")
    assert server._podcast_jobs_ready("script-1", plan) is None

    save_job("turn-3", "turn-3", "a", "avatar-a", "voice-a", "batch-1")
    ready = server._podcast_jobs_ready("script-1", plan)
    assert [job["id"] for job in ready or []] == ["turn-1", "turn-2", "turn-3"]
