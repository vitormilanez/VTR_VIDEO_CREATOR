from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertEqual(context["version"], "pack-context-v2")
        self.assertEqual(context["idea"]["ideaId"], "idea-1")
        self.assertEqual(context["performance"]["displayText"], "Fala")
        self.assertEqual(context["designSystem"]["version"], "pack-v1")
        self.assertEqual(context["compliance"][0]["titulo"], "regra")
        self.assertTrue(context["identityKey"])

    def test_context_carries_the_full_linked_idea_and_a_seven_slide_brief(self) -> None:
        context = build_pack_context(
            script={
                "id": "script-1",
                "ideaId": "idea-1",
                "titulo": "Genetica e obesidade",
                "hook": "O risco nao depende de um gene isolado.",
                "dorConflito": "A manchete parece determinista.",
                "explicacaoSimples": "Genes e ambiente interagem ao longo da vida.",
                "virada": "Predisposicao nao significa destino.",
                "cta": "Converse com seu medico.",
            },
            idea={
                "id": "idea-1",
                "titulo": "A heranca genetica precisa de contexto",
                "angulo": "Explicar o resultado sem culpar a mae.",
                "publicoDor": "Familias com historico de obesidade.",
                "linkOrigem": "https://example.test/estudo",
            },
            profile={"avatarId": "avatar-1", "voiceId": "voice-1"},
            avatar_set=None,
            design_system={"version": "pack-v2"},
            compliance_rules=[],
        )

        self.assertEqual(context["idea"]["angulo"], "Explicar o resultado sem culpar a mae.")
        self.assertEqual(context["idea"]["linkOrigem"], "https://example.test/estudo")
        self.assertEqual(len(context["narrativeBrief"]["slidePlan"]), 7)
        self.assertEqual(context["narrativeBrief"]["slidePlan"][3]["sourceText"], script_text := "Genes e ambiente interagem ao longo da vida.")
        self.assertEqual(script_text, context["script"]["explicacaoSimples"])

    def test_pack_schema_is_anthropic_compatible_and_local_contract_enforces_slide_count(self) -> None:
        slides_schema = server._PACK_SCHEMA["properties"]["slides"]

        self.assertNotIn("minItems", slides_schema)
        self.assertNotIn("maxItems", slides_schema)
        self.assertNotIn("maxLength", server._PACK_FIELDS_SCHEMA["properties"]["quote"])
        self.assertNotIn("maxLength", server._PACK_ITEM_SCHEMA["properties"]["text"])
        self.assertEqual(server._PACK_FIELD_MAX_LENGTHS["quote"], 90)
        self.assertEqual(server._PACK_FIELD_MAX_LENGTHS["body"], 320)
        pack = sample_pack()
        pack["slides"] = pack["slides"][:-1]
        pack["carousel"] = pack["carousel"][:-1]
        self.assertTrue(any("esperado: 7" in error for error in server.validate_pack_contract(pack)))

    def test_grounding_rejects_percentage_missing_from_idea_and_script(self) -> None:
        source_text = server._pack_text(sample_pack())
        pack = sample_pack()
        pack["slides"][0]["fields"]["headline"] = "Genes explicam 79% do risco"
        context = {
            "idea": {"titulo": "Genetica e obesidade"},
            "script": {"textoFalado": source_text},
            "performance": {},
            "narrativeBrief": {},
        }

        errors = server._pack_grounding_errors(pack, context)

        self.assertTrue(any("79%" in error for error in errors))
        context["script"]["textoFalado"] += " O estudo relatou 79% para esta amostra."
        self.assertEqual(server._pack_grounding_errors(pack, context), [])

    def test_grounding_accepts_approximate_marker_and_percentage_spacing(self) -> None:
        pack = sample_pack()
        pack["slides"][0]["fields"]["statistic"] = "~13%"
        authorized_copy = server._pack_text(pack).replace("~13%", "cerca de 13 %")
        context = {
            "idea": {"titulo": "Peso, fome e metabolismo"},
            "script": {"textoFalado": authorized_copy},
            "performance": {},
            "narrativeBrief": {},
        }

        self.assertEqual(server._pack_grounding_errors(pack, context), [])

    def test_grounding_rejects_an_off_topic_slide(self) -> None:
        pack = sample_pack()
        context = {
            "idea": {"titulo": "Peso, fome e metabolismo"},
            "script": {"textoFalado": server._pack_text(pack)},
            "performance": {},
            "narrativeBrief": {},
        }
        pack["slides"][3]["fields"] = server.empty_fields()
        pack["slides"][3]["fields"].update(
            headline="Como escolher uma camera",
            body="Lentes claras ajudam a fotografar paisagens durante a noite.",
        )

        errors = server._pack_grounding_errors(pack, context)

        self.assertTrue(any("slide 4: texto sem ligacao clara" in error for error in errors))

    def test_generation_uses_local_copy_repair_if_claude_repeats_length_error(self) -> None:
        payload = server.PackIn(scriptId="script-1", titulo="Pack", tema="peso")
        draft = sample_pack()
        draft.pop("carousel")
        draft["slides"][1]["fields"]["body"] = "A" * 117
        draft["slides"][5]["fields"]["quote"] = "Uma orientação contextualizada " + ("segura " * 14)
        message = SimpleNamespace(content=[SimpleNamespace(text=json.dumps(draft, ensure_ascii=False))])
        client = MagicMock()
        client.messages.create.side_effect = [message, message]
        context = {
            "version": "pack-context-v2",
            "identityKey": "identity-key",
            "identity": {"primaryAvatarId": "avatar-1"},
            "idea": {"id": "idea-1", "titulo": "Peso e contexto"},
            "script": {"id": "script-1", "textoFalado": server._pack_text(draft)},
            "performance": {"displayText": server._pack_text(draft)},
            "narrativeBrief": {"slidePlan": []},
            "designSystem": {"version": server.PACK_SCHEMA_VERSION},
            "compliance": [],
        }
        avatar_asset = {
            "avatarId": "avatar-1",
            "avatarName": "Principal",
            "cachedAssetPath": "data/avatar.jpg",
        }

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.object(
            server, "_find_script", return_value=context["script"]
        ), patch.object(
            server, "_pack_generation_context", return_value=(context, {})
        ), patch.object(server, "_ai_cache_get", return_value=None), patch.object(
            server, "_recent_pack_context", return_value=[]
        ), patch.object(
            server, "_find_pack_avatar_asset", return_value=avatar_asset
        ), patch.object(server, "_record_anthropic_usage"), patch.object(
            server, "_save_visual_pack"
        ), patch.object(server, "_ai_cache_put"), patch(
            "anthropic.Anthropic", return_value=client
        ):
            response = server.generate_pack(payload)

        self.assertTrue(response["ok"])
        self.assertEqual(client.messages.create.call_count, 2)
        self.assertEqual(server.validate_pack_contract(response["pack"]), [])
        self.assertLessEqual(len(response["pack"]["carousel"][1]["fields"]["body"]), 110)
        self.assertLessEqual(len(response["pack"]["carousel"][5]["fields"]["quote"]), 90)

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
        payload = server.PackIn(
            scriptId="script-1",
            titulo="Pack",
            tema="peso",
            family="storytelling",
            themeId="modernist-red",
        )
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
                    "script": {"textoFalado": server._pack_text(sample_pack())},
                    "performance": {"displayText": server._pack_text(sample_pack())},
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
        self.assertNotIn("family", cache_payload["request"])
        self.assertNotIn("themeId", cache_payload["request"])
        self.assertEqual(response["pack"]["family"], "storytelling")
        self.assertEqual(response["pack"]["themeId"], "modernist-red")

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
        self.assertEqual(response["pack"]["family"], "didatico")
        self.assertEqual(response["pack"]["themeId"], "ocean-deep")
        save_pack.assert_called_once()

    def test_pack_presentation_is_saved_without_calling_claude(self) -> None:
        pack = sample_pack()
        pack["sourceAvatarId"] = "avatar-1"
        with patch.object(server, "_find_script", return_value={"id": "script-1"}), patch.object(
            server, "_get_visual_pack", return_value=pack
        ), patch.object(
            server, "_save_visual_pack", side_effect=lambda _script_id, value: value
        ) as save_pack, patch.object(server, "_record_anthropic_usage") as record_usage:
            response = server.update_pack_presentation(
                "script-1",
                server.PackPresentationIn(family="editorial", themeId="modernist-red"),
            )

        self.assertEqual(response["pack"]["family"], "editorial")
        self.assertEqual(response["pack"]["themeId"], "modernist-red")
        self.assertEqual(response["pack"]["designPlan"]["family"], "editorial")
        self.assertEqual(response["pack"]["designPlan"]["themeId"], "modernist-red")
        save_pack.assert_called_once()
        record_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
