from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api import server
from api.services.scene_generation import build_scene_generation_result


class SceneGenerationTests(unittest.TestCase):
    def test_builds_one_future_request_per_scene_and_keeps_voice(self) -> None:
        result = build_scene_generation_result(
            script_id="script-1",
            scene_plan={
                "scenes": [
                    {
                        "id": "scene-1",
                        "avatarId": "avatar-close",
                        "lookRole": "standing",
                        "text": "Hook",
                    },
                    {
                        "id": "scene-2",
                        "avatarId": "avatar-front",
                        "lookRole": "seated",
                        "text": "Explicação",
                    },
                ]
            },
            voice_id="voice-fixed",
            speech_mode="natural",
            voice_mood="upbeat",
            orientation="portrait",
            spoken_text_by_scene={"scene-1": "Fala exata do hook."},
        )

        self.assertEqual(result.status, "not_submitted")
        self.assertEqual(result.provider, "heygen")
        self.assertEqual(result.scene_count, 2)
        self.assertEqual([item.avatar_id for item in result.requests], ["avatar-close", "avatar-front"])
        self.assertEqual({item.voice_id for item in result.requests}, {"voice-fixed"})
        self.assertEqual(result.requests[0].spoken_text, "Fala exata do hook.")
        self.assertEqual([item.look_role for item in result.requests], ["standing", "seated"])
        self.assertEqual({item.voice_mood for item in result.requests}, {"upbeat"})
        self.assertEqual(result.to_dict()["requests"][0]["lookRole"], "standing")
        self.assertEqual(result.to_dict()["requests"][0]["voiceMood"], "upbeat")
        self.assertEqual(result.to_dict()["requests"][1]["orientation"], "portrait")

    def test_requires_resolved_avatar_per_scene(self) -> None:
        with self.assertRaisesRegex(ValueError, "avatarId"):
            build_scene_generation_result(
                script_id="script-1",
                scene_plan={"scenes": [{"id": "scene-1", "text": "Sem look"}]},
                voice_id="voice-fixed",
            )

    def test_api_only_returns_not_submitted_plan(self) -> None:
        with patch.object(server, "_find_script", return_value={"id": "script-1"}), patch.object(
            server,
            "_scene_plan",
            return_value={"scenes": [{"id": "scene-1", "avatarId": "avatar-1", "text": "Fala"}]},
        ), patch.object(
            server,
            "_production_profile",
            return_value={"voiceId": "voice-1", "avatarId": "avatar-1", "primaryAvatarId": "avatar-1"},
        ):
            response = server.get_scene_generation_plan("script-1")
        self.assertEqual(response["generation"]["status"], "not_submitted")
        self.assertEqual(response["generation"]["requests"][0]["avatarId"], "avatar-1")

    def test_single_request_rejects_long_duration_before_any_provider_call(self) -> None:
        with self.assertRaises(server.HTTPException) as raised:
            server.create_video(
                server.VideoCreateIn(
                    scriptId="script-long-single",
                    durationSeconds=90,
                    generationMode="direct",
                )
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("duas câmeras", str(raised.exception.detail))

    def test_two_camera_profile_rejects_any_single_mocked_heygen_job(self) -> None:
        with patch.object(
            server,
            "_production_profile",
            return_value={"avatarMode": "set", "generationMode": "direct"},
        ), patch.object(server, "_find_script") as find_script:
            with self.assertRaises(server.HTTPException) as raised:
                server.create_video(
                    server.VideoCreateIn(
                        scriptId="script-two-camera",
                        durationSeconds=45,
                        generationMode="direct",
                    )
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("job único", str(raised.exception.detail))
        find_script.assert_not_called()

    def test_two_camera_submission_locks_mocked_heygen_looks_voice_and_audio_policy(self) -> None:
        """The provider mock proves each scene gets its assigned fixed look.

        This is deliberately an integration-style mock: no HeyGen request is
        sent, but the exact two payloads and the persisted continuity policy
        are inspected as they would be in production.
        """
        script_id = "script-two-camera"
        script = {"id": script_id, "titulo": "Teste", "textoFalado": "Abertura. Explicação."}
        scene_plan = {
            "scriptId": script_id,
            "transitionStyle": "hard_cut",
            "scenes": [
                {
                    "id": "scene-1",
                    "text": "Abertura.",
                    "lookRole": "standing",
                    "avatarId": "look-standing",
                },
                {
                    "id": "scene-2",
                    "text": "Explicação.",
                    "lookRole": "seated",
                    "avatarId": "look-seated",
                },
            ],
        }
        profile = {
            "avatarMode": "set",
            "avatarSetId": "set-1",
            "voiceId": "voice-fixed",
        }
        authorization = {
            "script": script,
            "scriptRevision": 4,
            "finalSpeechHash": "a" * 64,
            "contractVersion": "2.0.0",
        }
        provider_payloads: list[dict[str, object]] = []

        def fake_heygen_json(
            _command: str,
            _args: list[str],
            *,
            payload: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> dict[str, object]:
            del timeout
            assert payload is not None
            provider_payloads.append(payload)
            return {"data": {"video_id": f"mock-{len(provider_payloads)}"}}

        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            try:
                payload = server.SceneVideoConfirmIn(
                    confirmed=True,
                    durationSeconds=90,
                    idempotencyKey="mock-batch-01",
                    expectedScriptRevision=4,
                    expectedFinalSpeechHash="a" * 64,
                    contractVersion="2.0.0",
                )
                with patch.object(server, "_authorize_paid_generation", return_value=authorization), patch.object(
                    server, "_scene_plan_synced_to_script", return_value=scene_plan
                ), patch.object(server, "_production_profile", return_value=profile), patch.object(
                    server, "_heygen_cli", return_value="heygen-mock"
                ), patch.object(
                    server,
                    "_private_avatar_library",
                    return_value=(
                        [],
                        [
                            {"id": "look-standing", "status": "completed", "group_id": "doctor-1"},
                            {"id": "look-seated", "status": "completed", "group_id": "doctor-1"},
                        ],
                        False,
                    ),
                ), patch.object(server, "_run_heygen_json", side_effect=fake_heygen_json):
                    response = server.submit_scene_generation(script_id, payload)
            finally:
                server.OPERATIONAL_DB = original_database

        self.assertEqual([item["avatar_id"] for item in provider_payloads], ["look-standing", "look-seated"])
        self.assertEqual([item["voice_id"] for item in provider_payloads], ["voice-fixed", "voice-fixed"])
        self.assertEqual(provider_payloads[0]["voice_settings"], provider_payloads[1]["voice_settings"])
        self.assertEqual([job["remoteVideoId"] for job in response["jobs"]], ["mock-1", "mock-2"])
        self.assertEqual({job["productionSettings"]["voiceId"] for job in response["jobs"]}, {"voice-fixed"})
        self.assertTrue(all(job["productionSettings"]["backgroundMusic"] is False for job in response["jobs"]))
        self.assertTrue(
            all(job["productionSettings"]["audioPolicy"] == "hard_cut_no_voice_mix" for job in response["jobs"])
        )
        self.assertTrue(all(job["continuity"]["avatarGroupId"] == "doctor-1" for job in response["jobs"]))

    def test_regenerates_only_the_problematic_mocked_scene(self) -> None:
        script_id = "script-regenerate-one"
        script = {"id": script_id, "titulo": "Teste", "textoFalado": "Abertura. Explicação."}
        scene_plan = {
            "scriptId": script_id,
            "transitionStyle": "hard_cut",
            "scenes": [
                {
                    "id": "scene-1",
                    "text": "Abertura.",
                    "lookRole": "standing",
                    "avatarId": "look-standing",
                },
                {
                    "id": "scene-2",
                    "text": "Explicação.",
                    "lookRole": "seated",
                    "avatarId": "look-seated",
                },
            ],
        }
        profile = {
            "avatarMode": "set",
            "avatarSetId": "set-1",
            "voiceId": "voice-fixed",
        }
        authorization = {
            "script": script,
            "scriptRevision": 4,
            "finalSpeechHash": "a" * 64,
            "contractVersion": "2.0.0",
        }
        provider_payloads: list[dict[str, object]] = []

        def fake_heygen_json(
            _command: str,
            _args: list[str],
            *,
            payload: dict[str, object] | None = None,
            timeout: int = 120,
        ) -> dict[str, object]:
            del timeout
            assert payload is not None
            provider_payloads.append(payload)
            return {"data": {"video_id": "mock-regenerated"}}

        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            try:
                server._job_store().upsert(
                    "video",
                    {
                        "id": "scene-old",
                        "scriptId": script_id,
                        "scriptRevision": 4,
                        "finalSpeechHash": "a" * 64,
                        "contractVersion": "2.0.0",
                        "status": "pronto",
                        "provider": "heygen",
                        "progresso": 100,
                        "criadoEm": "2026-08-11T12:00:00+00:00",
                        "atualizadoEm": "2026-08-11T12:01:00+00:00",
                        "submissionState": "completed",
                        "isScene": True,
                        "sceneBatchId": "batch-original",
                        "sceneId": "scene-2",
                        "sceneOrder": 2,
                        "productionSettings": {
                            "avatarId": "look-seated",
                            "lookRole": "seated",
                            "voiceId": "voice-fixed",
                            "orientation": "portrait",
                            "durationSeconds": 90,
                            "speechMode": "natural",
                            "voiceMood": "confident",
                            "captions": True,
                            "optimizePronunciation": True,
                            "spokenText": "Explicação.",
                        },
                    },
                )
                with patch.object(server, "_authorize_paid_generation", return_value=authorization), patch.object(
                    server, "_scene_plan_synced_to_script", return_value=scene_plan
                ), patch.object(server, "_production_profile", return_value=profile), patch.object(
                    server, "_heygen_cli", return_value="heygen-mock"
                ), patch.object(
                    server,
                    "_private_avatar_library",
                    return_value=(
                        [],
                        [
                            {"id": "look-standing", "status": "completed", "group_id": "doctor-1"},
                            {"id": "look-seated", "status": "completed", "group_id": "doctor-1"},
                        ],
                        False,
                    ),
                ), patch.object(server, "_run_heygen_json", side_effect=fake_heygen_json):
                    response = server.regenerate_scene_video(
                        "scene-old", server.SceneRegenerateIn(confirmed=True)
                    )
            finally:
                server.OPERATIONAL_DB = original_database

        replacement = response["job"]
        self.assertNotEqual(replacement["id"], "scene-old")
        self.assertEqual(replacement["regeneratedFromJobId"], "scene-old")
        self.assertEqual(replacement["sceneBatchId"], "batch-original")
        self.assertEqual(replacement["sceneId"], "scene-2")
        self.assertEqual(replacement["remoteVideoId"], "mock-regenerated")
        self.assertEqual([item["avatar_id"] for item in provider_payloads], ["look-seated"])
        self.assertEqual([item["voice_id"] for item in provider_payloads], ["voice-fixed"])
        self.assertEqual(replacement["productionSettings"]["voiceId"], "voice-fixed")
        self.assertFalse(replacement["productionSettings"]["backgroundMusic"])
        self.assertEqual(replacement["productionSettings"]["cutPolicy"], "hard_cut")


if __name__ == "__main__":
    unittest.main()
