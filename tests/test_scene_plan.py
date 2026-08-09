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

    def test_generation_plan_refreshes_stale_avatar_ids_from_current_set(self) -> None:
        old_set = server._save_avatar_set(
            name="Looks antigos",
            voice_id="voice-1",
            looks=[
                {"avatarId": "old-close", "role": "close", "label": "Close"},
                {"avatarId": "old-front", "role": "front", "label": "Frontal"},
            ],
        )
        server._save_production_profile(
            {
                "scriptId": "script-refresh",
                "avatarId": "old-close",
                "primaryAvatarId": "old-close",
                "avatarSetId": old_set["id"],
                "avatarMode": "set",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )
        server._save_scene_plan(
            "script-refresh",
            [
                {"id": "scene-1", "text": "Abertura", "lookRole": "close"},
                {"id": "scene-2", "text": "Explicação", "lookRole": "front"},
            ],
        )
        current_set = server._save_avatar_set(
            name="Looks atuais",
            voice_id="voice-1",
            looks=[
                {"avatarId": "current-close", "role": "close", "label": "Close"},
                {"avatarId": "current-front", "role": "front", "label": "Frontal"},
            ],
        )
        server._save_production_profile(
            {
                "scriptId": "script-refresh",
                "avatarId": "current-close",
                "primaryAvatarId": "current-close",
                "avatarSetId": current_set["id"],
                "avatarMode": "set",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )

        with patch.object(server, "_find_script", return_value={"id": "script-refresh"}):
            response = server.get_scene_generation_plan("script-refresh")

        avatar_ids = [request["avatarId"] for request in response["generation"]["requests"]]
        self.assertEqual(avatar_ids, ["current-close", "current-front"])
        self.assertEqual(
            [scene["avatarId"] for scene in server._scene_plan("script-refresh")["scenes"]],
            ["current-close", "current-front"],
        )

    def test_ready_scene_jobs_require_same_batch_and_expected_avatars(self) -> None:
        scene_plan = {
            "scenes": [
                {"id": "scene-1", "avatarId": "current-close"},
                {"id": "scene-2", "avatarId": "current-front"},
            ]
        }

        def save_job(
            job_id: str,
            scene_id: str,
            avatar_id: str,
            batch_id: str,
            updated_at: str,
        ) -> None:
            server._job_store().upsert(
                "video",
                {
                    "id": job_id,
                    "scriptId": "script-batch",
                    "status": "pronto",
                    "provider": "heygen",
                    "progresso": 100,
                    "criadoEm": updated_at,
                    "atualizadoEm": updated_at,
                    "isScene": True,
                    "sceneBatchId": batch_id,
                    "sceneId": scene_id,
                    "productionSettings": {"avatarId": avatar_id},
                },
            )

        save_job("old-1", "scene-1", "old-close", "old-batch", "2026-08-09T09:00:00+00:00")
        save_job("old-2", "scene-2", "old-front", "old-batch", "2026-08-09T09:00:01+00:00")
        save_job("new-1", "scene-1", "current-close", "new-batch", "2026-08-09T10:00:00+00:00")

        self.assertIsNone(server._scene_jobs_ready("script-batch", scene_plan))

        save_job("new-2", "scene-2", "current-front", "new-batch", "2026-08-09T10:00:01+00:00")
        ready = server._scene_jobs_ready("script-batch", scene_plan)
        self.assertIsNotNone(ready)
        self.assertEqual([job["id"] for job in ready or []], ["new-1", "new-2"])

    def test_production_profile_persists_cinematic_prompt(self) -> None:
        profile = server._save_production_profile(
            {
                "scriptId": "script-cinematic",
                "avatarId": "look-only",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "cinematic",
                "cinematicPrompt": "Gui andando pela cidade com apoios discretos no fundo.",
                "voiceMood": "upbeat",
            }
        )

        self.assertEqual(
            profile["cinematicPrompt"],
            "Gui andando pela cidade com apoios discretos no fundo.",
        )
        self.assertEqual(
            server._production_profile("script-cinematic")["cinematicPrompt"],
            "Gui andando pela cidade com apoios discretos no fundo.",
        )
        self.assertEqual(server._production_profile("script-cinematic")["voiceMood"], "upbeat")

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

    def test_visual_plan_edit_is_persisted_and_compliance_is_checked(self) -> None:
        server._save_production_profile(
            {
                "scriptId": "script-edit-visual",
                "avatarId": "look-only",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )
        server._save_scene_plan(
            "script-edit-visual",
            [{"id": "scene-1", "text": "Explicação", "lookRole": "primary"}],
        )
        with patch.object(server, "_find_script", return_value={"id": "script-edit-visual"}):
            result = server.save_script_visual_plan(
                "script-edit-visual",
                server.VisualPlanIn(
                    scenes=[
                        server.VisualPlanSceneIn(
                            sceneId="scene-1",
                            visual=server.VisualPlanVisualIn(
                                type="full_slide",
                                layout="big_statement",
                                headline="Não é um motivo só",
                                body="O contexto importa",
                                purpose="reforçar a ideia central",
                            ),
                        )
                    ]
                ),
            )
        self.assertEqual(result["visualPlan"]["scenes"][0]["visual"]["layout"], "big_statement")
        self.assertEqual(server._get_visual_plan("script-edit-visual"), result["visualPlan"])

    def test_visual_plan_requires_one_support_before_each_next_scene(self) -> None:
        server._save_production_profile(
            {
                "scriptId": "script-visual-count",
                "avatarId": "look-only",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )
        server._save_scene_plan(
            "script-visual-count",
            [
                {"id": "scene-1", "text": "Primeira explicação.", "lookRole": "primary"},
                {"id": "scene-2", "text": "Segunda explicação.", "lookRole": "secondary"},
                {"id": "scene-3", "text": "Fechamento médico.", "lookRole": "primary"},
            ],
        )
        with patch.object(server, "_find_script", return_value={"id": "script-visual-count"}):
            with self.assertRaises(server.HTTPException) as raised:
                server.save_script_visual_plan(
                    "script-visual-count",
                    server.VisualPlanIn(
                        scenes=[
                            server.VisualPlanSceneIn(
                                sceneId="scene-1",
                                visual=server.VisualPlanVisualIn(type="none"),
                            ),
                            server.VisualPlanSceneIn(
                                sceneId="scene-2",
                                visual=server.VisualPlanVisualIn(
                                    type="comparison",
                                    layout="myth_fact",
                                    headline="Pesquisa não é aprovação",
                                    body="Cada indicação precisa de evidência própria.",
                                    purpose="Preparar o próximo corte",
                                ),
                            ),
                            server.VisualPlanSceneIn(
                                sceneId="scene-3",
                                visual=server.VisualPlanVisualIn(type="none"),
                            ),
                        ]
                    ),
                )
        self.assertEqual(raised.exception.status_code, 422)

    def test_visual_plan_for_three_scenes_keeps_two_supports_and_avatar_close(self) -> None:
        server._save_production_profile(
            {
                "scriptId": "script-visual-close",
                "avatarId": "look-only",
                "voiceId": "voice-1",
                "speechMode": "natural",
                "generationMode": "direct",
            }
        )
        server._save_scene_plan(
            "script-visual-close",
            [
                {"id": "scene-1", "text": "Primeira explicação.", "lookRole": "primary"},
                {"id": "scene-2", "text": "Segunda explicação.", "lookRole": "secondary"},
                {"id": "scene-3", "text": "Fechamento médico.", "lookRole": "primary"},
            ],
        )
        with patch.object(server, "_find_script", return_value={"id": "script-visual-close"}):
            result = server.save_script_visual_plan(
                "script-visual-close",
                server.VisualPlanIn(
                    scenes=[
                        server.VisualPlanSceneIn(
                            sceneId="scene-1",
                            visual=server.VisualPlanVisualIn(
                                type="statistic",
                                layout="number_stat",
                                headline="Mercado em expansão",
                                body="Apoia a primeira fala.",
                                purpose="Contextualizar",
                            ),
                        ),
                        server.VisualPlanSceneIn(
                            sceneId="scene-2",
                            visual=server.VisualPlanVisualIn(
                                type="comparison",
                                layout="myth_fact",
                                headline="Pesquisa não é aprovação",
                                body="Apoia a segunda fala.",
                                purpose="Contrastar",
                            ),
                        ),
                        server.VisualPlanSceneIn(
                            sceneId="scene-3",
                            visual=server.VisualPlanVisualIn(
                                type="quote",
                                layout="doctor_quote",
                                headline="Converse com seu médico",
                                body="Este visual seria descartado.",
                                purpose="Fechar",
                            ),
                        ),
                    ]
                ),
            )
        visuals = [scene["visual"]["type"] for scene in result["visualPlan"]["scenes"]]
        self.assertEqual(visuals, ["statistic", "comparison", "none"])


if __name__ == "__main__":
    unittest.main()
