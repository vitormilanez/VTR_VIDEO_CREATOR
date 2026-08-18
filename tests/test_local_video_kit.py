from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api.services.local_video_captions import (
    caption_cues,
    caption_document,
    write_caption_timeline,
)
from api.services.local_video_kit import (
    CLAUDE_MIDNIGHT_MODELS,
    _claude_midnight_data,
    _claude_midnight_timing,
    _claude_midnight_visual_filter,
    _detect_flat_horizontal_bars,
    _five_stack_data,
    _five_stack_timing,
    _five_stack_visual_filter,
    _generic_visual_events,
    _insert_visual_filter,
    _kit_documents,
    _motion_filter,
    _motion_profile,
    _outro_tail_seconds,
    _section_enabled,
    _section_transition,
    _section_timing,
    _validate_visual_intervals,
    _voice_filters,
)
from api.services.medical_identity import (
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_MINIMUM_END_CARD_SECONDS,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
)
from api.services.post_production_overlays import overlay_document


ROOT = Path(__file__).resolve().parents[1]


class LocalVideoKitTests(unittest.TestCase):
    def test_source_upload_does_not_start_post_production(self) -> None:
        from api import server

        received = AsyncMock(
            return_value={
                "uploadId": "kit-upload-1234567890abcdef",
                "filename": "consulta.mp4",
                "size": 2048,
                "path": Path("/tmp/consulta.mp4"),
            }
        )
        with (
            patch.object(server, "_receive_local_video_kit_upload", received),
            patch.object(server, "create_post_production") as create_analysis,
        ):
            request = object()
            response = asyncio.run(server.upload_local_video_kit_source(request))

        received.assert_awaited_once_with(request, prefix="kit-upload")
        create_analysis.assert_not_called()
        self.assertEqual(
            response,
            {
                "ok": True,
                "uploadId": "kit-upload-1234567890abcdef",
                "filename": "consulta.mp4",
                "size": 2048,
            },
        )

    def test_generic_visual_events_keep_only_safe_claude_suggestions(self) -> None:
        events = _generic_visual_events(
            {
                "visualEvents": [
                    {
                        "id": "definition 1",
                        "enabled": True,
                        "interactionType": "definition_card",
                        "visualText": "Uma definição clara",
                        "startMs": 2000,
                        "endMs": 5400,
                        "screenPosition": "bottom_left",
                        "backgroundColor": "#4A1F2B",
                        "backgroundOpacity": 0.55,
                    },
                    {
                        "id": "disabled",
                        "enabled": False,
                        "interactionType": "number_card",
                        "startMs": 6000,
                        "endMs": 9000,
                    },
                ]
            },
            12,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], "definition-1")
        self.assertEqual(events[0]["interactionType"], "definition_card")
        self.assertEqual((events[0]["start"], events[0]["end"]), (2.0, 5.4))
        self.assertEqual(events[0]["screenPosition"], "bottom_left")
        self.assertEqual(events[0]["backgroundColor"], "#4a1f2b")
        self.assertEqual(events[0]["backgroundOpacity"], 0.55)

    def test_overlay_document_applies_local_position_color_and_opacity(self) -> None:
        document = overlay_document(
            {
                "interactionType": "caption_emphasis",
                "visualText": "Informação importante",
                "screenPosition": "bottom_left",
                "backgroundColor": "#4A1F2B",
                "backgroundOpacity": 0.55,
            }
        )

        self.assertIn("position-bottom_left", document)
        self.assertIn("justify-content:flex-start;align-items:flex-end", document)
        self.assertIn("rgba(74,31,43,0.55)", document)

    def test_overlapping_visual_models_are_rejected_before_ffmpeg(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "se sobrepõem"):
            _validate_visual_intervals(
                [
                    ("Definição", 2.0, 5.0),
                    ("Comparação", 4.0, 7.0),
                ]
            )

    def test_caption_cues_are_short_synced_and_clamped_to_video(self) -> None:
        transcript = {
            "words": [
                {
                    "text": text,
                    "startMs": index * 350,
                    "endMs": (index + 1) * 350,
                }
                for index, text in enumerate(
                    "A semaglutida brasileira pode ampliar o acesso ao tratamento com segurança".split()
                )
            ]
        }

        cues = caption_cues(transcript, 3.2)

        self.assertGreaterEqual(len(cues), 2)
        self.assertTrue(all(cue["end"] <= 3.2 for cue in cues))
        self.assertTrue(all(len(cue["text"].split()) <= 8 for cue in cues))

    def test_caption_document_escapes_text_and_highlights_keywords(self) -> None:
        document = caption_document(
            "Tratamento <seguro> com semaglutida",
            {
                "captionStyle": "clean",
                "captionPosition": "upper",
                "accent": "#52d18a",
                "highlightKeywords": True,
            },
        )

        self.assertIn("class='clean position-upper'", document)
        self.assertIn("#52d18a", document)
        self.assertIn("&lt;seguro&gt;", document)
        self.assertNotIn("<seguro>", document)
        self.assertIn("<mark>semaglutida</mark>", document)

    def test_local_kit_defaults_to_modern_local_captions(self) -> None:
        from api import server

        payload = server.LocalVideoKitCreateIn(uploadId="upload-123")

        self.assertTrue(payload.includeCaptions)
        self.assertEqual(payload.captionStyle, "dynamic")
        self.assertEqual(payload.captionPosition, "safe_bottom")
        self.assertTrue(payload.highlightKeywords)
        self.assertTrue(payload.duckMusicDuringSpeech)
        self.assertEqual(payload.motionPreset, "subtle")
        self.assertTrue(payload.enhanceVoice)

    def test_subtle_motion_skips_topic_cards(self) -> None:
        profile = _motion_profile(
            {"motionPreset": "subtle"},
            30,
            blocked_intervals=[(16, 20)],
        )

        self.assertEqual(profile["preset"], "subtle")
        self.assertEqual(profile["zoom"], 1.14)
        self.assertEqual(profile["rampSeconds"], 0.7)
        self.assertEqual(profile["focusY"], 0.43)
        self.assertEqual(profile["intervals"], [(6.5, 9.1), (26.1, 28.7)])

    def test_blank_topic_card_is_disabled_even_when_switch_is_on(self) -> None:
        from api import server

        payload = server.LocalVideoKitCreateIn(
            uploadId="upload-123",
            sectionTitle="   ",
            includeSection=True,
        )
        config = server._local_video_kit_config(payload)

        self.assertFalse(_section_enabled(config))
        self.assertFalse(config["includeSection"])
        self.assertEqual(config["sectionTitle"], "")

    def test_music_library_exposes_preview_url(self) -> None:
        from api import server

        track = server._music_track_response(server.MUSIC_LIBRARY[0])

        self.assertEqual(track["url"], "/api/music-tracks/soft-focus/file")

    def test_social_motion_is_stronger_and_more_frequent(self) -> None:
        subtle = _motion_profile({"motionPreset": "subtle"}, 30)
        social = _motion_profile({"motionPreset": "social"}, 30)

        self.assertGreater(social["zoom"], subtle["zoom"])
        self.assertGreater(len(social["intervals"]), len(subtle["intervals"]))
        self.assertIn("zoompan=", _motion_filter(social))
        self.assertIn("cos(PI*", _motion_filter(social))
        self.assertIn("ih*0.430", _motion_filter(social))

    def test_motion_and_voice_can_be_disabled(self) -> None:
        motion = _motion_profile({"motionPreset": "none"}, 30)

        self.assertEqual(_motion_filter(motion), "[base_raw]null[base];")
        self.assertEqual(_voice_filters({"enhanceVoice": False}), "")
        self.assertIn("acompressor", _voice_filters({}))
        self.assertIn("alimiter", _voice_filters({}))

    def test_caption_timeline_uses_one_finite_track_with_transparent_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            blank = destination / "blank.png"
            first = destination / "caption-001.png"
            second = destination / "caption-002.png"
            blank.write_bytes(b"png")
            first.write_bytes(b"png")
            second.write_bytes(b"png")

            timeline = write_caption_timeline(
                [
                    {"start": 0.5, "end": 1.5, "path": first},
                    {"start": 2.0, "end": 3.0, "path": second},
                ],
                destination,
                total_duration=4.0,
            )
            contents = timeline.read_text(encoding="utf-8")

        self.assertTrue(contents.startswith("ffconcat version 1.0"))
        self.assertEqual(contents.count("file 'caption-"), 2)
        self.assertIn("duration 0.500000", contents)
        self.assertIn("duration 1.000000", contents)
        self.assertTrue(contents.rstrip().endswith("file 'blank.png'"))

    def test_kit_has_five_vertical_pieces_and_escapes_user_text(self) -> None:
        documents = _kit_documents(
            {
                "name": "Dr. <script>alert(1)</script>",
                "title": "Título & cuidado",
                "accent": "not-a-color",
            },
            ROOT,
        )

        self.assertEqual(
            set(documents),
            {"opening", "lowerThird", "section", "outro", "cover"},
        )
        for document, _transparent in documents.values():
            self.assertIn("width:1080px", document)
            self.assertIn("height:1920px", document)
            self.assertNotIn("<script>alert(1)</script>", document)
        self.assertIn("#c8e05a", documents["opening"][0])
        self.assertIn("Título &amp; cuidado", documents["opening"][0])
        self.assertNotIn("Ponto 01", documents["section"][0])
        self.assertIn(MEDICAL_EDUCATIONAL_DISCLAIMER, documents["outro"][0])
        self.assertIn(MEDICAL_PROFESSIONAL_IDENTIFICATION, documents["outro"][0])
        self.assertNotIn("Quer mais dicas", documents["outro"][0])

    def test_local_kit_keeps_the_identification_slide_enabled(self) -> None:
        from api import server

        config = server._local_video_kit_config(
            server.LocalVideoKitCreateIn(
                uploadId="upload-123",
                includeOutro=False,
                outroTailSeconds=0,
            )
        )

        self.assertTrue(config["includeOutro"])
        self.assertEqual(config["outroTailSeconds"], MEDICAL_MINIMUM_END_CARD_SECONDS)

    def test_letterbox_detection_excludes_flat_border_rows(self) -> None:
        width, height = 270, 480
        raw = bytearray([245] * width * height * 3)
        for y in range(164, 316):
            for x in range(width):
                offset = (y * width + x) * 3
                raw[offset : offset + 3] = bytes((38 + x % 31, 82 + y % 37, 126))
        completed = subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
            stdout=bytes(raw),
            stderr=b"",
        )

        with tempfile.TemporaryDirectory() as temporary, patch(
            "api.services.local_video_kit.subprocess.run",
            return_value=completed,
        ):
            crop = _detect_flat_horizontal_bars(
                Path(temporary) / "source.mp4",
                30.0,
                "ffmpeg",
            )

        self.assertEqual(crop, (656, 608))

    def test_section_timing_respects_start_and_duration(self) -> None:
        self.assertEqual(
            _section_timing(
                {"sectionStartSeconds": 5, "sectionDurationSeconds": 4},
                24,
            ),
            (5.0, 4.0),
        )

    def test_section_timing_clamps_to_video_duration(self) -> None:
        self.assertEqual(
            _section_timing(
                {"sectionStartSeconds": 22, "sectionDurationSeconds": 10},
                24,
            ),
            (22.0, 2.0),
        )

    def test_section_transition_defaults_to_fade(self) -> None:
        stream, position = _section_transition({}, 10.5, 12.5)
        self.assertIn("fade=t=in:st=10.500", stream)
        self.assertIn("fade=t=out:st=12.100", stream)
        self.assertEqual(position, "0:0")

    def test_section_transition_can_slide_up(self) -> None:
        stream, position = _section_transition({"sectionTransition": "slide_up"}, 10.5, 13.5)
        self.assertEqual(stream, "[3:v]format=rgba[section];")
        self.assertIn("H*(1-(t-10.500)/0.400)", position)

    def test_outro_tail_defaults_to_ten_seconds_and_is_clamped(self) -> None:
        self.assertEqual(_outro_tail_seconds({}), 10.0)
        self.assertEqual(
            _outro_tail_seconds({"outroTailSeconds": 4.5}),
            MEDICAL_MINIMUM_END_CARD_SECONDS,
        )
        self.assertEqual(
            _outro_tail_seconds({"outroTailSeconds": -2}),
            MEDICAL_MINIMUM_END_CARD_SECONDS,
        )
        self.assertEqual(_outro_tail_seconds({"outroTailSeconds": 200}), 120.0)

    def test_insert_filter_uses_selected_clip_range_on_the_main_timeline(self) -> None:
        filter_complex, output_label = _insert_visual_filter(
            [
                {
                    "sourceStartSeconds": 4,
                    "sourceEndSeconds": 7,
                    "timelineStartSeconds": 12,
                    "timelineEndSeconds": 15,
                }
            ],
            input_start=7,
        )

        self.assertIn("[7:v]trim=start=4.000:end=7.000", filter_complex)
        self.assertIn("setpts=PTS+12.000/TB", filter_complex)
        self.assertIn("between(t,12.000,15.000)", filter_complex)
        self.assertIn("repeatlast=0", filter_complex)
        self.assertEqual(output_label, "base_insert_0")

    def test_claude_five_stack_is_transparent_and_keeps_five_editable_rows(self) -> None:
        documents = _kit_documents(
            {
                "manualVisualsEnabled": True,
                "fiveStack": {
                    "enabled": True,
                    "lines": ["Um", "Dois", "Três", "Quatro", "Cinco"],
                }
            },
            ROOT,
        )

        self.assertEqual(
            [key for key in documents if key.startswith("fiveStackRow")],
            ["fiveStackRow1", "fiveStackRow2", "fiveStackRow3", "fiveStackRow4", "fiveStackRow5"],
        )
        first, transparent = documents["fiveStackRow1"]
        fifth, _ = documents["fiveStackRow5"]
        self.assertTrue(transparent)
        self.assertIn("background:transparent", first)
        self.assertIn("Um", first)
        self.assertIn("#6fe3d2", first)
        self.assertIn("#ffb84d", fifth)

    def test_claude_five_stack_staggers_over_the_main_video(self) -> None:
        stack = _five_stack_data(
            {
                "manualVisualsEnabled": True,
                "fiveStack": {"enabled": True, "startSeconds": 8, "durationSeconds": 5},
            }
        )
        self.assertEqual(stack["lines"], list(stack["lines"]))
        self.assertEqual(
            _five_stack_timing({"manualVisualsEnabled": True, "fiveStack": stack}, 30),
            (8.0, 5.0),
        )

        filter_complex, output = _five_stack_visual_filter(
            input_start=9,
            row_count=5,
            base_label="base",
            start=8,
            end=13,
        )
        self.assertIn("[9:v]format=rgba", filter_complex)
        self.assertIn("[13:v]format=rgba", filter_complex)
        self.assertIn("between(t,8.000,13.000)", filter_complex)
        self.assertIn("between(t,8.400,13.000)", filter_complex)
        self.assertEqual(output, "base_five_stack_4")

    def test_claude_midnight_models_are_transparent_and_all_editable(self) -> None:
        requested = {
            key: {"enabled": True, "fields": [f"{key}-{index}" for index in range(12)]}
            for key in CLAUDE_MIDNIGHT_MODELS
        }
        normalized = _claude_midnight_data(
            {"manualVisualsEnabled": True, "claudeInserts": requested}
        )
        documents = _kit_documents(
            {"manualVisualsEnabled": True, "claudeInserts": requested}, ROOT
        )

        self.assertEqual(set(normalized), set(CLAUDE_MIDNIGHT_MODELS))
        self.assertEqual(
            {key.removeprefix("claude") for key in documents if key.startswith("claude")},
            set(CLAUDE_MIDNIGHT_MODELS),
        )
        for key, defaults in CLAUDE_MIDNIGHT_MODELS.items():
            document, transparent = documents[f"claude{key}"]
            self.assertTrue(transparent)
            self.assertIn("background:transparent", document)
            self.assertIn("#6fe3d2", document)
            self.assertEqual(len(normalized[key]["fields"]), len(defaults["fields"]))
        self.assertIn("#07100f", documents["claudeevidenceStamp"][0])

    def test_claude_midnight_models_have_timing_and_alpha_overlay_filters(self) -> None:
        models = _claude_midnight_data(
            {
                "manualVisualsEnabled": True,
                "claudeInserts": {
                    "numberGlass": {"enabled": True, "startSeconds": 6, "durationSeconds": 4},
                    "evidenceStamp": {"enabled": True, "startSeconds": 14, "durationSeconds": 5},
                }
            }
        )
        first_start, first_duration = _claude_midnight_timing("numberGlass", models["numberGlass"], 30)
        second_start, second_duration = _claude_midnight_timing("evidenceStamp", models["evidenceStamp"], 30)
        filter_complex, output = _claude_midnight_visual_filter(
            [
                ("numberGlass", first_start, first_start + first_duration),
                ("evidenceStamp", second_start, second_start + second_duration),
            ],
            input_start=14,
            base_label="base",
        )

        self.assertEqual((first_start, first_duration), (6.0, 4.0))
        self.assertEqual((second_start, second_duration), (14.0, 5.0))
        self.assertIn("[14:v]format=rgba", filter_complex)
        self.assertIn("[15:v]format=rgba", filter_complex)
        self.assertIn("fade=t=in:st=6.000:d=0.34:alpha=1", filter_complex)
        self.assertIn("between(t,14.000,19.000)", filter_complex)
        self.assertEqual(output, "base_claude_evidenceStamp")

    def test_server_normalizes_all_claude_midnight_controls(self) -> None:
        from api import server

        payload = server.LocalVideoKitCreateIn(
            manualVisualsEnabled=True,
            claudeInserts={
                "numberGlass": {"enabled": True, "fields": [" DADO ", "12%"]},
                "evidenceStamp": {"enabled": True, "durationSeconds": 8},
            }
        )
        config = server._local_video_kit_config(payload)

        self.assertEqual(set(config["claudeInserts"]), set(CLAUDE_MIDNIGHT_MODELS))
        self.assertTrue(config["claudeInserts"]["numberGlass"]["enabled"])
        self.assertEqual(config["claudeInserts"]["numberGlass"]["fields"][:2], ["DADO", "12%"])
        self.assertEqual(config["claudeInserts"]["evidenceStamp"]["durationSeconds"], 8.0)

    def test_server_ignores_legacy_manual_models_without_explicit_opt_in(self) -> None:
        from api import server

        payload = server.LocalVideoKitCreateIn(
            claudeInserts={"mechanismBars": {"enabled": True, "fields": ["LEGADO"]}},
            fiveStack={"enabled": True, "lines": ["Um", "Dois", "Três", "Quatro", "Cinco"]},
        )

        config = server._local_video_kit_config(payload)

        self.assertFalse(config["manualVisualsEnabled"])
        self.assertFalse(config["fiveStack"]["enabled"])
        self.assertFalse(config["claudeInserts"]["mechanismBars"]["enabled"])

    def test_job_with_insert_is_validated_and_persisted_with_mocked_probe(self) -> None:
        from api import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "upload-123.mp4").write_bytes(b"main-video")
            insert_id = "kit-insert-0123456789abcdef"
            (uploads / f"{insert_id}.mp4").write_bytes(b"insert-video")
            with (
                patch.object(server, "ROOT", root),
                patch.object(server, "LOCAL_VIDEO_KIT_UPLOADS", uploads),
                patch.object(server, "LOCAL_VIDEO_KIT_JOBS", root / "jobs"),
                patch.object(server, "LOCAL_VIDEO_KIT_OUTPUTS", root / "outputs"),
                patch.object(server, "probe_duration", return_value=30.0) as probe,
                patch.object(server, "_launch_local_video_kit") as launch,
                patch.object(server.shutil, "which", return_value="/usr/bin/tool"),
            ):
                result = server.create_local_video_kit(
                    server.LocalVideoKitCreateIn(
                        uploadId="upload-123",
                        inserts=[
                            server.LocalVideoKitInsertIn(
                                id="insert-1",
                                uploadId=insert_id,
                                sourceName="apoio.mp4",
                                sourceDurationSeconds=10,
                                timelineStartSeconds=5,
                                timelineEndSeconds=8,
                                sourceStartSeconds=0,
                                sourceEndSeconds=3,
                            )
                        ],
                    )
                )

        self.assertEqual(result["job"]["config"]["inserts"][0]["uploadId"], insert_id)
        probe.assert_called_once()
        launch.assert_called_once_with(result["job"]["id"])

    def test_render_reuses_transcript_created_before_claude(self) -> None:
        from api import server

        analysis_id = "post-0123456789abcdef"
        upload_id = "kit-upload-0123456789abcdef"

        class AnalysisStore:
            def get(self, kind: str, job_id: str):
                if kind == "post_production" and job_id == analysis_id:
                    return {
                        "id": analysis_id,
                        "status": "needs_review",
                        "uploadId": upload_id,
                        "plannerMode": "anthropic",
                    }
                return None

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uploads = root / "uploads"
            post_outputs = root / "post-production"
            analysis_directory = post_outputs / analysis_id
            uploads.mkdir()
            analysis_directory.mkdir(parents=True)
            (uploads / f"{upload_id}.mp4").write_bytes(b"main-video")
            transcript_payload = {"version": "transcript-ready", "words": []}
            (analysis_directory / "transcript.json").write_text(
                json.dumps(transcript_payload),
                encoding="utf-8",
            )
            (analysis_directory / "timeline.json").write_text(
                json.dumps({"version": "timeline-ready", "events": []}),
                encoding="utf-8",
            )
            with (
                patch.object(server, "ROOT", root),
                patch.object(server, "LOCAL_VIDEO_KIT_UPLOADS", uploads),
                patch.object(server, "LOCAL_VIDEO_KIT_JOBS", root / "jobs"),
                patch.object(server, "LOCAL_VIDEO_KIT_OUTPUTS", root / "outputs"),
                patch.object(server, "POST_PRODUCTION_OUTPUTS", post_outputs),
                patch.object(server, "_job_store", return_value=AnalysisStore()),
                patch.object(
                    server,
                    "run_post_production_preflight",
                    return_value={"ok": True, "findings": []},
                ),
                patch.object(server, "_launch_local_video_kit") as launch,
                patch.object(server.shutil, "which", return_value="/usr/bin/tool"),
            ):
                result = server.create_local_video_kit(
                    server.LocalVideoKitCreateIn(
                        uploadId=upload_id,
                        analysisJobId=analysis_id,
                    )
                )
                reused = (
                    root / "jobs" / result["job"]["id"] / "transcript.json"
                ).read_text(encoding="utf-8")

        self.assertTrue(result["job"]["transcriptReused"])
        self.assertEqual(json.loads(reused), transcript_payload)
        launch.assert_called_once_with(result["job"]["id"])

    def test_repeated_source_range_is_rejected(self) -> None:
        from api import server

        with tempfile.TemporaryDirectory() as temporary:
            uploads = Path(temporary)
            insert_id = "kit-insert-0123456789abcdef"
            (uploads / f"{insert_id}.mp4").write_bytes(b"insert-video")
            config = {
                "inserts": [
                    {
                        "uploadId": insert_id,
                        "sourceDurationSeconds": 10,
                        "timelineStartSeconds": 2,
                        "timelineEndSeconds": 5,
                        "sourceStartSeconds": 0,
                        "sourceEndSeconds": 3,
                    },
                    {
                        "uploadId": insert_id,
                        "sourceDurationSeconds": 10,
                        "timelineStartSeconds": 8,
                        "timelineEndSeconds": 11,
                        "sourceStartSeconds": 2,
                        "sourceEndSeconds": 5,
                    },
                ]
            }
            with patch.object(server, "LOCAL_VIDEO_KIT_UPLOADS", uploads):
                with self.assertRaisesRegex(Exception, "esse trecho do clipe já foi usado"):
                    server._validate_local_video_kit_inserts(config, 30)

    def test_ready_production_video_can_be_selected_without_upload(self) -> None:
        from api import server

        class ReadyVideoStore:
            def get(self, kind: str, job_id: str) -> dict[str, str] | None:
                if kind == "video" and job_id == "v-ready":
                    return {"id": job_id, "status": "pronto", "outputPath": "produced.mp4"}
                return None

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "produced.mp4"
            source.write_bytes(b"local-video")
            with (
                patch.object(server, "ROOT", root),
                patch.object(server, "LOCAL_VIDEO_KIT_JOBS", root / "jobs"),
                patch.object(server, "LOCAL_VIDEO_KIT_OUTPUTS", root / "outputs"),
                patch.object(server, "_job_store", return_value=ReadyVideoStore()),
                patch.object(server, "_local_output_path", return_value=source),
                patch.object(server, "_launch_local_video_kit") as launch,
            ):
                result = server.create_local_video_kit(
                    server.LocalVideoKitCreateIn(
                        videoJobId="v-ready",
                        sourceName="Vídeo pronto",
                    )
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["sourceVideoJobId"], "v-ready")
        self.assertEqual(result["job"]["sourcePath"], "produced.mp4")
        launch.assert_called_once_with(result["job"]["id"])

    def test_saved_local_kit_can_be_reused_without_upload(self) -> None:
        from api import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original.mp4"
            source.write_bytes(b"local-video")
            saved_job_dir = root / "jobs" / "kit-source"
            saved_job_dir.mkdir(parents=True)
            (saved_job_dir / "job.json").write_text(
                '{"id":"kit-source","status":"pronto","sourcePath":"original.mp4"}',
                encoding="utf-8",
            )
            with (
                patch.object(server, "ROOT", root),
                patch.object(server, "LOCAL_VIDEO_KIT_JOBS", root / "jobs"),
                patch.object(server, "LOCAL_VIDEO_KIT_OUTPUTS", root / "outputs"),
                patch.object(server, "_local_output_path", return_value=source),
                patch.object(server, "_launch_local_video_kit") as launch,
            ):
                result = server.create_local_video_kit(
                    server.LocalVideoKitCreateIn(
                        sourceKitJobId="kit-source",
                        sourceName="Vídeo reaplicado",
                    )
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["sourceKitJobId"], "kit-source")
        self.assertEqual(result["job"]["sourcePath"], "original.mp4")
        launch.assert_called_once_with(result["job"]["id"])

    def test_server_restart_marks_interrupted_local_render_as_retryable(self) -> None:
        from api import server

        with tempfile.TemporaryDirectory() as temporary:
            jobs = Path(temporary) / "jobs"
            active = jobs / "kit-active"
            ready = jobs / "kit-ready"
            active.mkdir(parents=True)
            ready.mkdir(parents=True)
            (active / "job.json").write_text(
                '{"id":"kit-active","status":"processando","progresso":55}',
                encoding="utf-8",
            )
            (ready / "job.json").write_text(
                '{"id":"kit-ready","status":"pronto","progresso":100}',
                encoding="utf-8",
            )
            with patch.object(server, "LOCAL_VIDEO_KIT_JOBS", jobs):
                interrupted = server.reconcile_interrupted_local_video_kit_jobs()
                active_job = server._get_local_video_kit_job("kit-active")
                ready_job = server._get_local_video_kit_job("kit-ready")

        self.assertEqual(interrupted, 1)
        self.assertEqual(active_job["status"], "erro")
        self.assertIn("Tentar novamente", active_job["erro"])
        self.assertEqual(ready_job["status"], "pronto")


if __name__ == "__main__":
    unittest.main()
