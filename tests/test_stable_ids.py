from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api import server


SCRIPT_HEADERS = [
    "Categoria",
    "Tema",
    "Título",
    "Hook",
    "Dor/Conflito",
    "Explicação simples",
    "Virada/Provocação",
    "CTA",
    "Cuidados médicos",
    "Risco",
    "Formato sugerido",
    "Status",
    "Aprovador",
    "Data aprovação",
    "Link doc/video",
    "ID",
]


class FakeSheetsClient:
    def __init__(self) -> None:
        self.values = [SCRIPT_HEADERS]

    def get_values(self, _range_name: str) -> list[list[str]]:
        return self.values

    def append_rows(self, _range_name: str, rows: list[list[object]]) -> dict:
        self.values.extend([[str(value) for value in row] for row in rows])
        return {"updates": {"updatedRows": len(rows)}}

    def update_values(self, range_name: str, rows: list[list[object]]) -> dict:
        if range_name.startswith("'Roteiros'!A"):
            row_number = int(range_name.split("!A", 1)[1].split(":", 1)[0])
            self.values[row_number - 1] = [str(value) for value in rows[0]]
        return {"updatedRange": range_name}


class FakeCalendarClient:
    def __init__(self) -> None:
        self.values = [server.CALENDAR_HEADERS.copy()]

    def get_values(self, _range_name: str) -> list[list[str]]:
        return self.values

    def append_rows(self, _range_name: str, rows: list[list[object]]) -> dict:
        self.values.extend([[str(value) for value in row] for row in rows])
        return {"updates": {"updatedRows": len(rows)}}

    def update_values(self, range_name: str, rows: list[list[object]]) -> dict:
        if range_name == "'Calendario'!A1:N1":
            self.values[0] = [str(value) for value in rows[0]]
        elif range_name.startswith("'Calendario'!A"):
            row_number = int(range_name.split("!A", 1)[1].split(":", 1)[0])
            self.values[row_number - 1] = [str(value) for value in rows[0]]
        return {"updatedRange": range_name}


class StableIdTests(unittest.TestCase):
    def test_final_narration_compliance_blocks_before_production(self) -> None:
        with self.assertRaises(server.HTTPException) as raised:
            server._validate_final_narration(
                {"hook": "Conteudo educativo"},
                "Tome 5 mg todos os dias para ter resultado certo.",
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("compliance final", raised.exception.detail)
        self.assertIn("dose", raised.exception.detail.lower())

    def test_final_narration_compliance_accepts_safe_educational_text(self) -> None:
        text = server._validate_final_narration(
            {"hook": "Cada pessoa precisa de avaliacao individual."},
            None,
        )
        self.assertIn(server.MANDATORY_VIDEO_OUTRO, text)

    def test_video_prompt_applies_production_preferences(self) -> None:
        prompt = server._video_prompt(
            {"hook": "GLP-1 funciona em 30s?"},
            duration_seconds=30,
            speech_mode="fiel",
            captions=False,
            optimize_pronunciation=True,
        )
        self.assertIn("approximately 30 seconds", prompt)
        self.assertIn("G L P um", prompt)
        self.assertIn("trinta segundos", prompt)
        self.assertIn("Follow the supplied script closely", prompt)
        self.assertIn("Do not add burned-in captions", prompt)
        self.assertTrue(prompt.count(server.MANDATORY_VIDEO_OUTRO) >= 2)
        self.assertIn("This must be the final sentence", prompt)

    def test_short_video_durations_are_accepted(self) -> None:
        self.assertEqual(server.VideoCreateIn(scriptId="s-1", durationSeconds=10).durationSeconds, 10)
        self.assertEqual(
            server.NaturalizeScriptIn(
                text="Texto suficiente para preparar uma fala curta e natural.",
                durationSeconds=15,
            ).durationSeconds,
            15,
        )

    def test_video_prompt_does_not_duplicate_mandatory_outro_in_script(self) -> None:
        prompt = server._video_prompt(
            {"cta": server.MANDATORY_VIDEO_OUTRO},
            optimize_pronunciation=False,
        )
        script_section = prompt.split("VOICE-OPTIMIZED SCRIPT (Portuguese):\n", 1)[1]
        self.assertEqual(script_section.count(server.MANDATORY_VIDEO_OUTRO), 1)

    def test_video_prompt_uses_reviewed_narration_text(self) -> None:
        prompt = server._video_prompt(
            {"hook": "Texto original"},
            narration_text="Texto falado revisado.",
            optimize_pronunciation=False,
        )
        self.assertIn("Texto falado revisado.", prompt)
        self.assertNotIn("Texto original", prompt)
        self.assertIn(server.MANDATORY_VIDEO_OUTRO, prompt)

    def test_removed_avatar_cannot_remain_the_default(self) -> None:
        avatars = [{"id": "avatar-atual"}]
        with patch.dict(
            "os.environ",
            {"HEYGEN_DEFAULT_AVATAR_ID": "avatar-removido"},
        ):
            self.assertEqual(server._heygen_default_avatar_id(avatars), "avatar-atual")

    def test_private_avatar_library_includes_every_look(self) -> None:
        groups = [
            {"id": "grupo-1", "name": "Pessoa 1"},
            {"id": "grupo-2", "name": "Pessoa 2"},
        ]
        responses = [
            {"data": groups},
            {"data": [{"id": "visual-1", "name": "Visual 1", "status": "completed"}]},
            {
                "data": [
                    {"id": "visual-2", "name": "Visual 2", "status": "completed"},
                    {"id": "visual-3", "name": "Visual 3", "status": "processing"},
                ]
            },
        ]
        with patch.object(server, "_run_heygen_json", side_effect=responses) as run:
            returned_groups, looks = server._private_avatar_library("heygen")

        self.assertEqual(returned_groups, groups)
        self.assertEqual([look["id"] for look in looks], ["visual-1", "visual-2", "visual-3"])
        self.assertEqual(looks[0]["group_name"], "Pessoa 1")
        self.assertEqual(looks[2]["group_id"], "grupo-2")
        self.assertEqual(run.call_count, 3)

    def test_avatar_creation_requires_explicit_consent(self) -> None:
        with self.assertRaises(server.HTTPException) as raised:
            server.create_heygen_avatar(
                server.AvatarCreateIn(
                    name="Avatar de teste",
                    creationType="prompt",
                    appearancePrompt="Apresentador profissional e acolhedor",
                )
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("autorizacao", raised.exception.detail)

    def test_existing_video_requires_explicit_new_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            jobs_file = Path(temporary) / "video_jobs.json"
            database = Path(temporary) / "operations.db"
            jobs_file.write_text(
                json.dumps([{"id": "v-existente", "scriptId": "s-1", "status": "pronto"}]),
                encoding="utf-8",
            )
            original_jobs = server.VIDEO_JOBS
            original_database = server.OPERATIONAL_DB
            server.VIDEO_JOBS = jobs_file
            server.OPERATIONAL_DB = database
            try:
                with self.assertRaises(server.HTTPException) as raised:
                    server.create_video(server.VideoCreateIn(scriptId="s-1"))
                self.assertEqual(raised.exception.status_code, 409)
                self.assertIn("ja possui um video", raised.exception.detail)
            finally:
                server.VIDEO_JOBS = original_jobs
                server.OPERATIONAL_DB = original_database

    def test_download_rejects_job_without_heygen_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            jobs_file = Path(temporary) / "video_jobs.json"
            database = Path(temporary) / "operations.db"
            jobs_file.write_text(
                json.dumps([{"id": "v-1", "videoUrl": "mock://heygen/video.mp4"}]),
                encoding="utf-8",
            )
            original_jobs = server.VIDEO_JOBS
            original_database = server.OPERATIONAL_DB
            server.VIDEO_JOBS = jobs_file
            server.OPERATIONAL_DB = database
            try:
                with self.assertRaises(server.HTTPException) as raised:
                    server.download_video("v-1")
                self.assertEqual(raised.exception.status_code, 409)
            finally:
                server.VIDEO_JOBS = original_jobs
                server.OPERATIONAL_DB = original_database

    def test_mappers_prefer_persisted_ids(self) -> None:
        scripts = server.map_scripts([{"ID": "s-permanente", "Título": "Teste"}])
        self.assertEqual(scripts[0]["id"], "s-permanente")

    def test_row_lookup_survives_reordering(self) -> None:
        values = [
            ["Título", "ID"],
            ["Segundo", "s-bbb"],
            ["Primeiro", "s-aaa"],
        ]
        self.assertEqual(server._sheet_row_number(values, "s-aaa", "s"), 3)

    def test_sheet_status_labels_round_trip(self) -> None:
        self.assertEqual(server._idea_status("Ideia gerada"), "aprovado")
        self.assertEqual(server._script_status("Em edição"), "em_revisao")
        self.assertEqual(server._script_status("Pronto"), "aprovado_clinicamente")
        self.assertEqual(server._script_status("Arquivado"), "rejeitado")

    def test_legacy_video_job_references_are_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            jobs_file = Path(temporary) / "video_jobs.json"
            database = Path(temporary) / "operations.db"
            jobs_file.write_text(json.dumps([{"id": "v-1", "scriptId": "s-0"}]), encoding="utf-8")
            original_jobs = server.VIDEO_JOBS
            original_database = server.OPERATIONAL_DB
            server.VIDEO_JOBS = jobs_file
            server.OPERATIONAL_DB = database
            try:
                changed = server._migrate_video_job_script_ids([{"id": "s-permanente"}])
                jobs = server._load_video_jobs()
                self.assertEqual(changed, 1)
                self.assertEqual(jobs[0]["scriptId"], "s-permanente")
            finally:
                server.VIDEO_JOBS = original_jobs
                server.OPERATIONAL_DB = original_database

    def test_video_reservation_is_idempotent_across_store_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            original_jobs = server.VIDEO_JOBS
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            server.VIDEO_JOBS = Path(temporary) / "missing-video-jobs.json"
            try:
                first = {
                    "id": "v-primeiro",
                    "scriptId": "s-1",
                    "status": "fila",
                    "criadoEm": "2026-07-23T10:00:00+00:00",
                    "atualizadoEm": "2026-07-23T10:00:00+00:00",
                }
                reserved, state = server._job_store().reserve_video(
                    first,
                    idempotency_key="request-stable-123",
                    force_new_version=True,
                )
                self.assertEqual(state, "created")
                reserved["submissionState"] = "submitted"
                server._job_store().upsert("video", reserved)

                duplicate, duplicate_state = server._job_store().reserve_video(
                    {**first, "id": "v-segundo"},
                    idempotency_key="request-stable-123",
                    force_new_version=True,
                )
                self.assertEqual(duplicate_state, "duplicate")
                self.assertEqual(duplicate["id"], "v-primeiro")
                self.assertEqual(len(server._load_video_jobs()), 1)

                duplicate["submissionState"] = "submission_uncertain"
                duplicate["status"] = "erro"
                duplicate["retrySafe"] = False
                server._job_store().upsert("video", duplicate)
                blocked, blocked_state = server._job_store().reserve_video(
                    {**first, "id": "v-terceiro"},
                    idempotency_key="request-different-456",
                    force_new_version=True,
                )
                self.assertEqual(blocked_state, "conflict")
                self.assertEqual(blocked["id"], "v-primeiro")
                self.assertEqual(len(server._load_video_jobs()), 1)
            finally:
                server.OPERATIONAL_DB = original_database
                server.VIDEO_JOBS = original_jobs

    def test_legacy_json_jobs_are_imported_once_into_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            original_jobs = server.VIDEO_JOBS
            database = Path(temporary) / "operations.db"
            jobs_file = Path(temporary) / "video_jobs.json"
            jobs_file.write_text(
                json.dumps([{"id": "v-legado", "status": "pronto", "scriptId": "s-1"}]),
                encoding="utf-8",
            )
            server.OPERATIONAL_DB = database
            server.VIDEO_JOBS = jobs_file
            try:
                self.assertEqual([job["id"] for job in server._load_video_jobs()], ["v-legado"])
                jobs_file.write_text("[]", encoding="utf-8")
                self.assertEqual([job["id"] for job in server._load_video_jobs()], ["v-legado"])
            finally:
                server.OPERATIONAL_DB = original_database
                server.VIDEO_JOBS = original_jobs

    def test_repeated_api_request_submits_to_heygen_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.OPERATIONAL_DB
            original_jobs = server.VIDEO_JOBS
            server.OPERATIONAL_DB = Path(temporary) / "operations.db"
            server.VIDEO_JOBS = Path(temporary) / "missing-video-jobs.json"

            def complete_submission(
                _payload: server.VideoCreateIn,
                job: dict,
            ) -> dict:
                job["submissionState"] = "submitted"
                job["remoteSessionId"] = "session-1"
                server._job_store().upsert("video", job)
                return {"ok": True, "job": job}

            payload = server.VideoCreateIn(
                scriptId="s-1",
                forceNewVersion=True,
                idempotencyKey="stable-api-request-123",
            )
            try:
                with patch.object(
                    server,
                    "_create_video_job",
                    side_effect=complete_submission,
                ) as submit:
                    first = server.create_video(payload)
                    second = server.create_video(payload)
                self.assertEqual(first["job"]["id"], second["job"]["id"])
                self.assertTrue(second["deduplicated"])
                self.assertEqual(submit.call_count, 1)
            finally:
                server.OPERATIONAL_DB = original_database
                server.VIDEO_JOBS = original_jobs

    def test_script_is_available_to_production_after_create_and_update(self) -> None:
        client = FakeSheetsClient()
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot.json"
            snapshot.write_text(
                json.dumps({"updated_at": "", "sheets": {"roteiros": []}}),
                encoding="utf-8",
            )
            original_snapshot = server.SNAPSHOT
            server.SNAPSHOT = snapshot
            try:
                with patch(
                    "integrations.google_sheets_rest_client.GoogleSheetsRestClient",
                    return_value=client,
                ):
                    created = server.append_script(
                        server.ScriptIn(
                            id="s-estavel",
                            titulo="Roteiro inicial",
                            hook="Um hook",
                        )
                    )["script"]
                    self.assertEqual(created["id"], "s-estavel")
                    self.assertEqual(server._find_script("s-estavel")["titulo"], "Roteiro inicial")

                    updated = server.update_script(
                        "s-estavel",
                        server.ScriptIn(
                            id="s-estavel",
                            titulo="Roteiro revisado",
                            hook="Hook revisado",
                        ),
                    )["script"]
                    self.assertEqual(updated["titulo"], "Roteiro revisado")
                    self.assertEqual(server._find_script("s-estavel")["hook"], "Hook revisado")
            finally:
                server.SNAPSHOT = original_snapshot

    def test_calendar_create_and_reschedule_are_persisted(self) -> None:
        client = FakeCalendarClient()
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot.json"
            snapshot.write_text(
                json.dumps({"updated_at": "", "sheets": {"calendario": []}}),
                encoding="utf-8",
            )
            original_snapshot = server.SNAPSHOT
            server.SNAPSHOT = snapshot
            try:
                with patch(
                    "integrations.google_sheets_rest_client.GoogleSheetsRestClient",
                    return_value=client,
                ):
                    created = server.append_calendar_post(
                        server.CalendarIn(
                            id="p-estavel",
                            scriptId="s-1",
                            videoJobId="v-1",
                            titulo="Post real",
                            dataAgendada="2026-07-30T12:00:00",
                            canal="instagram",
                        )
                    )["post"]
                    self.assertEqual(created["id"], "p-estavel")
                    self.assertEqual(created["scriptId"], "s-1")
                    self.assertEqual(created["videoJobId"], "v-1")

                    updated = server.update_calendar_post(
                        "p-estavel",
                        server.CalendarIn(
                            id="p-estavel",
                            scriptId="s-1",
                            videoJobId="v-1",
                            titulo="Post real",
                            dataAgendada="2026-08-02T12:00:00",
                            canal="instagram",
                            status="agendado",
                        ),
                    )["post"]
                    self.assertEqual(updated["dataAgendada"][:10], "2026-08-02")
                    self.assertEqual(client.values[1][0], "02/08/2026")
                    persisted = json.loads(snapshot.read_text(encoding="utf-8"))
                    self.assertEqual(
                        persisted["sheets"]["calendario"][0]["Video Job ID"],
                        "v-1",
                    )
            finally:
                server.SNAPSHOT = original_snapshot


if __name__ == "__main__":
    unittest.main()
