from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api import server


class AvatarSetTests(unittest.TestCase):
    def test_avatar_set_requires_two_distinct_looks(self) -> None:
        with self.assertRaises(server.HTTPException):
            server._save_avatar_set(
                name="Dr. Teste",
                voice_id="voice-1",
                looks=[
                    {"avatarId": "look-1", "role": "close", "label": "Close"},
                    {"avatarId": "look-1", "role": "front", "label": "Frontal"},
                ],
            )

    def test_avatar_set_and_profile_are_persisted_without_external_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            try:
                avatar_set = server._save_avatar_set(
                    name="Dr. Teste — duas posições",
                    voice_id="voice-1",
                    looks=[
                        {"avatarId": "look-close", "role": "close", "label": "Close"},
                        {"avatarId": "look-front", "role": "front", "label": "Frontal"},
                    ],
                )
                saved = server._save_production_profile(
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

                loaded_set = server._get_avatar_set(avatar_set["id"])
                loaded_profile = server._production_profile("script-1")
                self.assertEqual(loaded_set["looks"], avatar_set["looks"])
                self.assertEqual(saved["positionCount"], 2)
                self.assertEqual(loaded_profile["avatarMode"], "set")
                self.assertEqual(loaded_profile["avatarSetId"], avatar_set["id"])
                self.assertEqual(loaded_profile["primaryAvatarId"], "look-close")
            finally:
                server.OPERATIONAL_DB = original_database

    def test_profile_rejects_primary_look_outside_avatar_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            try:
                avatar_set = server._save_avatar_set(
                    name="Dr. Teste",
                    voice_id="voice-1",
                    looks=[
                        {"avatarId": "look-close", "role": "close", "label": "Close"},
                        {"avatarId": "look-front", "role": "front", "label": "Frontal"},
                    ],
                )
                with self.assertRaises(server.HTTPException):
                    server._save_production_profile(
                        {
                            "scriptId": "script-1",
                            "avatarId": "other-look",
                            "primaryAvatarId": "other-look",
                            "avatarSetId": avatar_set["id"],
                            "avatarMode": "set",
                            "voiceId": "voice-1",
                            "speechMode": "natural",
                            "generationMode": "direct",
                        }
                    )
            finally:
                server.OPERATIONAL_DB = original_database


if __name__ == "__main__":
    unittest.main()
