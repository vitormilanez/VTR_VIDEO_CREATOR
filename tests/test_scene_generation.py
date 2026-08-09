from __future__ import annotations

import unittest
from unittest.mock import patch

from api import server
from api.services.scene_generation import build_scene_generation_result


class SceneGenerationTests(unittest.TestCase):
    def test_builds_one_future_request_per_scene_and_keeps_voice(self) -> None:
        result = build_scene_generation_result(
            script_id="script-1",
            scene_plan={
                "scenes": [
                    {"id": "scene-1", "avatarId": "avatar-close", "text": "Hook"},
                    {"id": "scene-2", "avatarId": "avatar-front", "text": "Explicação"},
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
        self.assertEqual({item.voice_mood for item in result.requests}, {"upbeat"})
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
        ), patch.object(server, "_production_profile", return_value={"voiceId": "voice-1"}):
            response = server.get_scene_generation_plan("script-1")
        self.assertEqual(response["generation"]["status"], "not_submitted")
        self.assertEqual(response["generation"]["requests"][0]["avatarId"], "avatar-1")

    def test_paid_submission_stops_before_provider_when_script_is_not_approved(self) -> None:
        payload = server.SceneVideoConfirmIn(confirmed=True)
        script = {
            "id": "script-1",
            "status": "rascunho",
            "textoFalado": " ".join(f"palavra{index}" for index in range(100)),
        }
        with patch.object(server, "_find_script", return_value=script), patch.object(
            server, "_heygen_cli"
        ) as heygen_cli:
            with self.assertRaises(server.HTTPException) as raised:
                server.submit_scene_generation("script-1", payload)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Pronto", raised.exception.detail)
        heygen_cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
