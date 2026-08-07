from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from api import server


class ScenePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(self.temporary.name) / "operations.db"

    def tearDown(self) -> None:
        server.OPERATIONAL_DB = self.original_database
        self.temporary.cleanup()

    def test_scene_plan_resolves_each_role_to_avatar_id(self) -> None:
        avatar_set = server._save_avatar_set(
            name="Duas posições",
            voice_id="voice-1",
            looks=[
                {"avatarId": "look-close", "role": "close", "label": "Close"},
                {"avatarId": "look-front", "role": "front", "label": "Frontal"},
            ],
        )
        server._save_production_profile(
            {
                "scriptId": "script-1",
                "avatarId": "look-close",
                "primaryAvatarId": "look-close",
                "avatarSetId": avatar_set["id"],
                "avatarMode": "set",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )

        plan = server._save_scene_plan(
            "script-1",
            [
                {"id": "scene-a", "text": "Abertura", "lookRole": "close"},
                {"id": "scene-b", "text": "Explicação", "lookRole": "front"},
            ],
        )

        self.assertEqual([scene["avatarId"] for scene in plan["scenes"]], ["look-close", "look-front"])
        self.assertEqual([scene["order"] for scene in plan["scenes"]], [1, 2])
        self.assertEqual(server._scene_plan("script-1"), plan)

    def test_single_avatar_profile_falls_back_to_primary_avatar(self) -> None:
        server._save_production_profile(
            {
                "scriptId": "script-single",
                "avatarId": "look-only",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )

        plan = server._save_scene_plan(
            "script-single",
            [{"text": "Cena única", "lookRole": "close"}],
        )

        self.assertEqual(plan["scenes"][0]["avatarId"], "look-only")
        self.assertEqual(plan["scenes"][0]["lookRole"], "close")

    def test_scene_director_requires_explicit_claude_configuration(self) -> None:
        payload = server.SceneDirectorIn(displayText="Texto educativo para dividir em cenas.")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False), patch.object(
            server, "_find_script", return_value={"id": "script-director"}
        ), patch.object(
            server,
            "_production_profile",
            return_value={"avatarMode": "single", "avatarId": "look-only"},
        ):
            with self.assertRaises(server.HTTPException) as raised:
                server.direct_scene_plan("script-director", payload)
        self.assertEqual(raised.exception.status_code, 503)

    def test_scene_director_cache_avoids_new_paid_call(self) -> None:
        cached = {
            "ok": True,
            "provider": "claude",
            "promptVersion": server.SCENE_DIRECTOR_PROMPT_VERSION,
            "scenes": [{"text": "Cache", "lookRole": "primary", "reason": "hook"}],
        }
        payload = server.SceneDirectorIn(displayText="Texto educativo para dividir em cenas.")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.object(
            server, "_find_script", return_value={"id": "script-director"}
        ), patch.object(
            server,
            "_production_profile",
            return_value={"avatarMode": "single", "avatarId": "look-only"},
        ), patch.object(server, "_ai_cache_get", return_value=cached) as cache_get, patch.object(
            server, "_record_anthropic_usage"
        ) as record_usage:
            result = server.direct_scene_plan("script-director", payload)
        self.assertEqual(result, cached)
        self.assertEqual(cache_get.call_args.args[0], "scene-plan.direct")
        self.assertEqual(cache_get.call_args.args[1]["promptVersion"], server.SCENE_DIRECTOR_PROMPT_VERSION)
        record_usage.assert_not_called()

    def test_visual_director_requires_saved_scene_plan(self) -> None:
        payload = server.VisualDirectorIn(displayText="Texto educativo para apoiar visualmente.")
        with patch.object(server, "_find_script", return_value={"id": "script-visual"}), patch.object(
            server, "_scene_plan", return_value=None
        ):
            with self.assertRaises(server.HTTPException) as raised:
                server.direct_visual_plan("script-visual", payload)
        self.assertEqual(raised.exception.status_code, 409)

    def test_visual_director_cache_avoids_new_paid_call(self) -> None:
        cached = {
            "ok": True,
            "provider": "claude",
            "visualPlan": {"scriptId": "script-visual", "scenes": []},
        }
        payload = server.VisualDirectorIn(displayText="Texto educativo para apoiar visualmente.")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.object(
            server, "_find_script", return_value={"id": "script-visual", "titulo": "Visual"}
        ), patch.object(
            server,
            "_scene_plan",
            return_value={"scriptId": "script-visual", "scenes": [{"id": "scene-1", "order": 1}]},
        ), patch.object(
            server,
            "_production_profile",
            return_value={"avatarMode": "single", "avatarId": "look-only"},
        ), patch.object(server, "_ai_cache_get", return_value=cached) as cache_get, patch.object(
            server, "_record_anthropic_usage"
        ) as record_usage:
            result = server.direct_visual_plan("script-visual", payload)
        self.assertEqual(result, cached)
        self.assertEqual(cache_get.call_args.args[0], "visual-plan.direct")
        self.assertEqual(cache_get.call_args.args[1]["designSystemVersion"], server.VIDEO_VISUAL_DESIGN_SYSTEM_VERSION)
        record_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
