from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api import cut_service, server
from api.job_store import JobStore


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


class FakeRadarClient:
    def __init__(self) -> None:
        self.values = [server.RADAR_HEADERS.copy()]

    def get_values(self, _range_name: str) -> list[list[str]]:
        return self.values

    def append_rows(self, _range_name: str, rows: list[list[object]]) -> dict:
        self.values.extend([[str(value) for value in row] for row in rows])
        return {"updates": {"updatedRows": len(rows)}}

    def update_values(self, range_name: str, _rows: list[list[object]]) -> dict:
        return {"updatedRange": range_name}


class StableIdTests(unittest.TestCase):
    def test_final_narration_compliance_warns_but_does_not_block_production(self) -> None:
        text = server._validate_final_narration(
            {"hook": "Conteudo educativo"},
            (
                "Tome 5 mg todos os dias para ter resultado certo. "
                "Esse texto ainda precisa de revisao medica antes de publicar. "
                "Mesmo assim, o sistema deve permitir teste interno sem enviar a decisao "
                "como orientacao final para o paciente."
            ),
            10,
        )
        self.assertIn("Tome 5 mg", text)
        self.assertIn(server.MANDATORY_VIDEO_OUTRO, text)

    def test_final_narration_compliance_accepts_safe_educational_text(self) -> None:
        text = server._validate_final_narration(
            {
                "hook": (
                    "Cada pessoa precisa de avaliacao individual. O conteudo serve para explicar "
                    "o tema com calma, sem substituir consulta e sem transformar informacao em "
                    "orientacao personalizada."
                )
            },
            None,
            10,
        )
        self.assertIn(server.MANDATORY_VIDEO_OUTRO, text)

    def test_final_narration_blocks_placeholder_script(self) -> None:
        with self.assertRaises(server.HTTPException) as raised:
            server._validate_final_narration(
                {"hook": "Conteudo educativo"},
                "Hook educativo sugerido — revise antes de aprovar. Rascunho: virada educativa reforcando avaliacao individual.",
                10,
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("antes do HeyGen", raised.exception.detail)

    def test_article_fallback_does_not_reuse_cancer_ideas_for_skin_article(self) -> None:
        payload = server.ArticleIdeasIn(
            article=(
                "Importar artigo\nCole artigo, resumo, abstract, link ou DOI\n3387/50000\n"
                "Tirzepatida, emagrecimento e pele: o que precisamos conversar além da balança\n"
                "Quando a perda de peso e rápida, a pele nem sempre acompanha no mesmo ritmo. "
                "Pode aparecer flacidez, rosto cansado, sulcos mais visíveis e dúvidas sobre "
                "acompanhamento dermatológico. Não porque a medicação esteja envelhecendo a pele, "
                "mas porque a gordura que sumiu também sustentava tecidos por baixo. "
                "Acompanhamento nutricional, preservação de massa muscular e cuidado dermatológico "
                "podem fazer parte do processo.\n"
                "Link, DOI ou PubMed\nhttps://doi.org/... ou PMID...\n"
                "O que a IA entendeu\nCanetas reduzem risco de câncer? Calma."
            ),
            familia="comportamento",
            prioridade="alta",
        )
        result = server._manual_article_analysis(payload)
        titles = " ".join(idea["titulo"] for idea in result["ideas"]).lower()
        self.assertIn("pele", result["analysis"]["achadoPrincipal"].lower())
        self.assertIn("pele", titles)
        self.assertNotIn("câncer", titles)
        self.assertNotIn("cancer", titles)

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
            returned_groups, looks, from_cache = server._private_avatar_library("heygen")

        self.assertEqual(returned_groups, groups)
        self.assertFalse(from_cache)
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

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_extracts_voice_from_avatar_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "avatar.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=160x90:d=0.5",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=0.5",
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            audio = server._voice_from_video(
                server.AvatarMediaIn(
                    name=source.name,
                    mimeType="video/mp4",
                    data=base64.b64encode(source.read_bytes()).decode("ascii"),
                )
            )

        self.assertEqual(audio["media_type"], "audio/x-wav")
        self.assertGreater(len(base64.b64decode(audio["data"])), 44)

    def test_large_avatar_video_uses_direct_asset_upload(self) -> None:
        media = server.AvatarMediaIn(
            name="avatar.mp4",
            mimeType="video/mp4",
            data=base64.b64encode(b"video-content").decode("ascii"),
        )
        responses = [
            {
                "data": {
                    "asset_id": "asset-pending",
                    "upload_url": "https://uploads.example.test/avatar",
                    "upload_headers": {"Content-Type": "video/mp4"},
                }
            },
            {"data": {"asset_id": "asset-ready", "status": "processing"}},
        ]
        with (
            patch.object(server, "_run_heygen_json", side_effect=responses) as run,
            patch.object(server.requests, "put") as put,
        ):
            put.return_value.status_code = 200
            result = server._avatar_file_payload(
                "heygen",
                media,
                allowed_mime_types={"video/mp4"},
                inline_max_bytes=4,
            )

        self.assertEqual(result, {"type": "asset_id", "asset_id": "asset-ready"})
        self.assertEqual(run.call_count, 2)
        put.assert_called_once_with(
            "https://uploads.example.test/avatar",
            data=b"video-content",
            headers={"Content-Type": "video/mp4"},
            timeout=300,
        )

    def test_digital_twin_uses_native_voice_from_video(self) -> None:
        media = server.AvatarMediaIn(
            name="avatar.mp4",
            mimeType="video/mp4",
            data=base64.b64encode(b"video-content").decode("ascii"),
        )
        responses = [
            {
                "data": {
                    "group_id": "group-native",
                    "id": "avatar-native",
                    "default_voice_id": "voice-native",
                }
            },
            {"data": {"consent_url": "https://app.heygen.com/consent/native"}},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "operations.db")
            with (
                patch.object(server, "_heygen_cli", return_value="heygen"),
                patch.object(server, "_run_heygen_json", side_effect=responses) as run,
                patch.object(server, "_job_store", return_value=store),
            ):
                result = server.create_heygen_avatar(
                    server.AvatarCreateIn(
                        name="Avatar nativo",
                        creationType="digital_twin",
                        media=[media],
                        cloneVoice=True,
                        voiceSource="video",
                        consentAccepted=True,
                    )
                )

        self.assertEqual(result["job"]["voiceId"], "voice-native")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[1], ["avatar", "create"])
        self.assertEqual(
            run.call_args_list[1].args[1],
            ["avatar", "consent", "create", "group-native"],
        )
        self.assertEqual(run.call_args_list[1].kwargs["payload"], {})

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

    def test_cut_projects_are_persisted_in_operational_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "operations.db")
            project = {
                "id": "c-1",
                "status": "fila",
                "createdAt": "2026-07-23T12:00:00+00:00",
                "updatedAt": "2026-07-23T12:00:00+00:00",
            }
            store.upsert("cut", project)
            self.assertEqual(store.get("cut", "c-1"), project)
            self.assertEqual(store.list("cut"), [project])

    def test_cut_reservation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "operations.db")
            first = {
                "id": "c-primeiro",
                "status": "fila",
                "createdAt": "2026-07-23T12:00:00+00:00",
                "updatedAt": "2026-07-23T12:00:00+00:00",
            }
            reserved, state = store.reserve("cut", first, idempotency_key="cut:request-123")
            duplicate, duplicate_state = store.reserve(
                "cut",
                {**first, "id": "c-segundo"},
                idempotency_key="cut:request-123",
            )
            self.assertEqual(state, "created")
            self.assertEqual(duplicate_state, "duplicate")
            self.assertEqual(reserved["id"], duplicate["id"])
            self.assertEqual(len(store.list("cut")), 1)

    def test_operational_store_migrates_schema_to_accept_cuts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "operations.db"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE operational_jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('video', 'avatar')),
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    script_id TEXT,
                    remote_session_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO operational_jobs VALUES (
                    'v-existente', 'video', 'pronto', NULL, 's-1', NULL,
                    '{"id":"v-existente","status":"pronto"}',
                    '2026-07-23T10:00:00+00:00', '2026-07-23T10:00:00+00:00'
                )
                """
            )
            connection.commit()
            connection.close()

            store = JobStore(database)
            store.upsert(
                "cut",
                {
                    "id": "c-novo",
                    "status": "fila",
                    "createdAt": "2026-07-23T12:00:00+00:00",
                    "updatedAt": "2026-07-23T12:00:00+00:00",
                },
            )
            self.assertEqual(store.get("video", "v-existente")["status"], "pronto")
            self.assertEqual(store.get("cut", "c-novo")["status"], "fila")

    def test_cut_project_requires_one_source_and_valid_duration(self) -> None:
        with self.assertRaises(server.HTTPException) as no_source:
            server.create_cut_project(server.CutCreateIn(requestId="request-1"))
        self.assertEqual(no_source.exception.status_code, 400)

        payload = server.CutCreateIn(
            requestId="request-2",
            uploadId="upload-1",
            sourceName="entrevista.mp4",
            clipCount=3,
            minDuration=20,
            maxDuration=10,
        )
        with self.assertRaises(server.HTTPException) as invalid_duration:
            server.create_cut_project(payload)
        self.assertEqual(invalid_duration.exception.status_code, 422)

    def test_cut_project_rejects_non_youtube_url(self) -> None:
        payload = server.CutCreateIn(
            requestId="request-youtube-invalid",
            youtubeUrl="https://youtube.com.evil.example/watch?v=123",
        )
        with self.assertRaises(server.HTTPException) as invalid_url:
            server.create_cut_project(payload)
        self.assertEqual(invalid_url.exception.status_code, 422)

    def test_youtube_download_is_limited_to_one_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "source.mp4"
            destination.write_bytes(b"video")
            completed = subprocess.CompletedProcess([], 0, "", "")
            with patch.object(cut_service, "_run_process", return_value=completed) as run:
                cut_service._download_youtube(
                    "job-test",
                    "https://www.youtube.com/watch?v=abc123",
                    destination,
                    analysis_start=600,
                    analysis_end=1200,
                )
            command = run.call_args.args[1]
            self.assertIn("--no-playlist", command)
            self.assertIn("duration <= 7200", command)
            self.assertIn("2G", command)
            self.assertIn("--download-sections", command)
            self.assertIn("*600.000-1200.000", command)

    def test_cut_selection_works_without_anthropic_credentials(self) -> None:
        transcript = {
            "duration": 50,
            "segments": [
                {
                    "start": index * 5,
                    "end": (index + 1) * 5,
                    "text": f"Por que este ponto importante numero {index} merece atencao?",
                }
                for index in range(10)
            ],
        }
        with patch.dict(
            "os.environ",
            {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""},
        ):
            clips, mode = cut_service._suggest_clips(
                transcript,
                count=5,
                min_duration=15,
                max_duration=45,
            )
        self.assertEqual(mode, "local")
        self.assertEqual(len(clips), 5)
        self.assertTrue(all(0 <= clip["start"] < clip["end"] <= 50 for clip in clips))
        starts = sorted(float(clip["start"]) for clip in clips)
        self.assertTrue(all(right - left >= 5 for left, right in zip(starts, starts[1:])))

    def test_automatic_cut_duration_uses_natural_speech_boundaries(self) -> None:
        transcript = {
            "duration": 80,
            "segments": [
                {
                    "start": index * 8,
                    "end": (index + 1) * 8 - (0.8 if index % 2 else 0),
                    "text": f"Esta e a ideia importante numero {index} com contexto claro.",
                }
                for index in range(10)
            ],
        }
        clips = cut_service._local_clip_suggestions(
            transcript,
            count=3,
            min_duration=18,
            max_duration=75,
            auto_duration=True,
        )
        natural_ends = {round(float(segment["end"]), 3) for segment in transcript["segments"]}
        self.assertEqual(len(clips), 3)
        self.assertTrue(all(round(float(clip["end"]), 3) in natural_ends for clip in clips))
        self.assertTrue(all(float(clip["end"] - clip["start"]) >= 18 for clip in clips))
        self.assertTrue(all(clip["reason"].endswith(".") for clip in clips))

    def test_automatic_cut_expands_bad_start_for_context(self) -> None:
        transcript = {
            "duration": 48,
            "segments": [
                {
                    "start": 0,
                    "end": 8,
                    "text": "Vou explicar uma coisa importante sobre fome e rotina.",
                },
                {
                    "start": 8,
                    "end": 16,
                    "text": "Beleza? Porque o problema aparece quando voce muda tudo por poucos dias.",
                },
                {
                    "start": 16,
                    "end": 24,
                    "text": "Por isso o resultado depende de consistencia e acompanhamento.",
                },
            ],
        }
        clips = cut_service._local_clip_suggestions(
            transcript,
            count=1,
            min_duration=18,
            max_duration=40,
            auto_duration=True,
        )
        self.assertEqual(clips[0]["start"], 0)
        self.assertIn("Vou explicar", clips[0]["caption"])

    def test_automatic_cut_count_can_skip_weak_video(self) -> None:
        transcript = {
            "duration": 30,
            "segments": [
                {
                    "start": index * 5,
                    "end": (index + 1) * 5,
                    "text": f"Continuação genérica do assunto sem gancho numero {index}.",
                }
                for index in range(6)
            ],
        }
        clips = cut_service._local_clip_suggestions(
            transcript,
            count=None,
            min_duration=18,
            max_duration=75,
            auto_duration=True,
        )
        self.assertEqual(clips, [])

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

    def test_manual_trend_is_persisted_and_mapped(self) -> None:
        client = FakeRadarClient()
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot.json"
            snapshot.write_text(
                json.dumps({"updated_at": "", "sheets": {"radar": []}}),
                encoding="utf-8",
            )
            original_snapshot = server.SNAPSHOT
            server.SNAPSHOT = snapshot
            try:
                with patch(
                    "integrations.google_sheets_rest_client.GoogleSheetsRestClient",
                    return_value=client,
                ):
                    created = server.append_trend(
                        server.TrendIn(
                            id="t-estavel",
                            titulo="Fome noturna",
                            fonte="Cadastro manual",
                            potencial=7,
                            prioridade="alta",
                        )
                    )["trend"]
                    self.assertEqual(created["id"], "t-estavel")
                    self.assertEqual(created["titulo"], "Fome noturna")
                    self.assertEqual(created["potencial"], 7)
                    self.assertEqual(created["prioridade"], "alta")
                    self.assertEqual(created["status"], "novo")
                    persisted = json.loads(snapshot.read_text(encoding="utf-8"))
                    self.assertEqual(persisted["sheets"]["radar"][0]["ID"], "t-estavel")
                    self.assertEqual(
                        persisted["sheets"]["radar"][0]["Fonte"], "Cadastro manual"
                    )
            finally:
                server.SNAPSHOT = original_snapshot

    def test_pack_compliance_blocks_sensational_tone(self) -> None:
        result = server._pack_compliance(
            {"hook": "Voce nao vai acreditar no que a ciencia descobriu!"}
        )
        self.assertTrue(result["blocked"])
        self.assertTrue(any("sensacionalista" in issue.lower() for issue in result["issues"]))

    def test_pack_compliance_blocks_self_diagnosis_suggestion(self) -> None:
        result = server._pack_compliance(
            {"hook": "Voce tem resistencia a insulina e nem sabe."}
        )
        self.assertTrue(result["blocked"])
        self.assertTrue(any("autodiagn" in issue.lower() for issue in result["issues"]))

    def test_pack_compliance_allows_clean_educational_text(self) -> None:
        result = server._pack_compliance(
            {"hook": "Cada pessoa precisa de avaliacao individual antes de qualquer tratamento."}
        )
        self.assertFalse(result["blocked"])
        self.assertEqual(result["issues"], [])

    def test_attach_calendar_links_matches_by_link_post(self) -> None:
        calendar_posts = [
            {
                "id": "p-1",
                "link": "https://instagram.com/p/abc",
                "scriptId": "s-1",
                "videoJobId": "v-1",
                "formato": "Reel",
            },
            {"id": "p-2", "link": None, "scriptId": "s-2", "videoJobId": None, "formato": "Reel"},
        ]
        performance = [
            {"id": "m-0", "link": "https://instagram.com/p/abc"},
            {"id": "m-1", "link": None},
            {"id": "m-2", "link": "https://instagram.com/p/nao-existe"},
        ]
        result = server._attach_calendar_links(performance, calendar_posts)
        self.assertEqual(result[0]["calendarPostId"], "p-1")
        self.assertEqual(result[0]["scriptId"], "s-1")
        self.assertEqual(result[0]["videoJobId"], "v-1")
        self.assertEqual(result[0]["formatoSugerido"], "Reel")
        self.assertIsNone(result[1]["calendarPostId"])
        self.assertIsNone(result[2]["calendarPostId"])

    def test_hunt_trends_returns_partial_result_when_sync_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot.json"
            snapshot.write_text(
                json.dumps({"updated_at": "", "sheets": {"radar": []}}),
                encoding="utf-8",
            )
            original_snapshot = server.SNAPSHOT
            server.SNAPSHOT = snapshot
            calls: list[str] = []

            def fake_run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
                calls.append(args[0])
                if len(calls) == 1:
                    return subprocess.CompletedProcess(
                        args, 0, stdout="tendencias capturadas", stderr=""
                    )
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="token expirado")

            try:
                with patch.object(server, "_run", side_effect=fake_run):
                    result = server.hunt_trends()
            finally:
                server.SNAPSHOT = original_snapshot

            self.assertTrue(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["failedStep"], "sync_sheets")
            self.assertIn("token expirado", result["detail"])
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
