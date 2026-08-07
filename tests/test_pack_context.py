from __future__ import annotations

import unittest
from unittest.mock import patch

from api import server
from api.services.pack_context import build_pack_context, identity_key, pack_identity
from tests.test_pack_design import sample_pack


class PackContextTests(unittest.TestCase):
    def test_identity_key_changes_when_avatar_set_changes(self) -> None:
        profile = {
            "avatarMode": "set",
            "avatarSetId": "set-1",
            "primaryAvatarId": "avatar-close",
            "avatarId": "avatar-close",
            "voiceId": "voice-fixed",
            "speechMode": "natural",
            "generationMode": "direct",
        }
        avatar_set = {
            "id": "set-1",
            "voiceId": "voice-fixed",
            "looks": [
                {"role": "close", "avatarId": "avatar-close"},
                {"role": "front", "avatarId": "avatar-front"},
            ],
        }
        changed = {**profile, "primaryAvatarId": "avatar-front", "avatarId": "avatar-front"}
        self.assertNotEqual(identity_key(pack_identity(profile, avatar_set)), identity_key(pack_identity(changed, avatar_set)))

    def test_context_contains_idea_script_performance_design_and_compliance(self) -> None:
        context = build_pack_context(
            script={"id": "script-1", "ideaId": "idea-1", "tema": "peso", "textoFalado": "Fala"},
            profile={"avatarMode": "single", "avatarId": "avatar-1", "voiceId": "voice-1", "speechMode": "natural"},
            avatar_set=None,
            design_system={"version": "pack-v1"},
            compliance_rules=[{"titulo": "regra"}],
        )
        self.assertEqual(context["version"], "pack-context-v1")
        self.assertEqual(context["idea"]["ideaId"], "idea-1")
        self.assertEqual(context["performance"]["displayText"], "Fala")
        self.assertEqual(context["designSystem"]["version"], "pack-v1")
        self.assertEqual(context["compliance"][0]["titulo"], "regra")
        self.assertTrue(context["identityKey"])

    def test_pack_endpoint_marks_identity_stale_without_calling_claude(self) -> None:
        with patch.object(server, "_find_script", return_value={"id": "script-1"}), patch.object(
            server,
            "_get_visual_pack",
            return_value={"schemaVersion": server.PACK_SCHEMA_VERSION, "sourceIdentityKey": "old-key"},
        ), patch.object(server, "_production_profile", return_value={"avatarId": "avatar-1"}), patch.object(
            server,
            "_pack_generation_context",
            return_value=({"identityKey": "new-key"}, {}),
        ):
            response = server.get_pack("script-1")
        self.assertTrue(response["outdatedAvatar"])
        self.assertTrue(response["outdatedIdentity"])

    def test_pack_generation_cache_key_contains_full_context(self) -> None:
        payload = server.PackIn(scriptId="script-1", titulo="Pack", tema="peso")
        cached = {
            "ok": True,
            "provider": "claude",
            "pack": {
                **sample_pack(),
                "avatarAsset": {
                    "avatarId": "avatar-1",
                    "avatarName": "Principal",
                    "cachedAssetPath": "data/avatar.jpg",
                },
            },
        }
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.object(
            server, "_find_script", return_value={"id": "script-1", "tema": "peso", "textoFalado": "Fala"}
        ), patch.object(
            server,
            "_pack_generation_context",
            return_value=(
                {
                    "identityKey": "identity-key",
                    "identity": {"primaryAvatarId": "avatar-1"},
                    "idea": {"ideaId": "idea-1"},
                    "script": {"textoFalado": "Fala"},
                    "performance": {"displayText": "Fala"},
                    "designSystem": {"version": server.PACK_SCHEMA_VERSION},
                    "compliance": [],
                },
                {},
            ),
        ), patch.object(server, "_ai_cache_get", return_value=cached) as cache_get, patch.object(
            server, "_save_visual_pack"
        ):
            response = server.generate_pack(payload)
        self.assertEqual(response["pack"]["sourceIdentityKey"], "identity-key")
        cache_payload = cache_get.call_args.args[1]
        self.assertEqual(cache_payload["context"]["idea"]["ideaId"], "idea-1")
        self.assertEqual(cache_payload["identityKey"], "identity-key")
        self.assertEqual(cache_payload["slideCount"], server.PACK_SLIDE_COUNT)

    def test_pack_endpoint_returns_old_six_slide_pack_already_migrated(self) -> None:
        old_pack = sample_pack()
        old_pack["schemaVersion"] = "institute-carousel-v1"
        old_pack["carousel"] = old_pack["carousel"][:6]
        old_pack["slides"] = old_pack["carousel"]
        with patch.object(server, "_find_script", return_value={"id": "script-1"}), patch.object(
            server, "_get_visual_pack", return_value=old_pack
        ), patch.object(server, "_production_profile", return_value={"avatarId": "avatar-1"}), patch.object(
            server,
            "_pack_generation_context",
            return_value=({"identityKey": old_pack.get("sourceIdentityKey")}, {}),
        ):
            response = server.get_pack("script-1")
        self.assertFalse(response["outdatedPackSchema"])
        self.assertFalse(response["outdatedAvatar"])
        self.assertEqual(len(response["pack"]["carousel"]), server.PACK_SLIDE_COUNT)
        self.assertEqual(response["requiredSlideCount"], server.PACK_SLIDE_COUNT)

    def test_pack_endpoint_migrates_old_six_slide_pack_and_saves_without_ai(self) -> None:
        old_pack = sample_pack()
        old_pack["schemaVersion"] = "institute-carousel-v1"
        old_pack["carousel"] = [
            old_pack["carousel"][0],
            old_pack["carousel"][1],
            old_pack["carousel"][4],
            old_pack["carousel"][3],
            old_pack["carousel"][5],
            old_pack["carousel"][6],
        ]
        old_pack["slides"] = old_pack["carousel"]
        old_pack["sourceAvatarId"] = "avatar-1"
        with patch.object(server, "_find_script", return_value={"id": "script-1"}), patch.object(
            server, "_get_visual_pack", return_value=old_pack
        ), patch.object(server, "_production_profile", return_value=None), patch.object(
            server, "_save_visual_pack", side_effect=lambda script_id, pack: pack
        ) as save_pack:
            response = server.get_pack("script-1")

        self.assertEqual(len(response["pack"]["carousel"]), server.PACK_SLIDE_COUNT)
        self.assertFalse(response["outdatedPackSchema"])
        self.assertEqual(response["pack"]["schemaVersion"], server.PACK_SCHEMA_VERSION)
        save_pack.assert_called_once()


if __name__ == "__main__":
    unittest.main()
