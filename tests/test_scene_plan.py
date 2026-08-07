from __future__ import annotations

import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
