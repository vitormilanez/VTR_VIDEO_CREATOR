from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.services.local_video_captions import (
    caption_cues,
    caption_document,
    write_caption_timeline,
)
from api.services.local_video_kit import (
    _detect_flat_horizontal_bars,
    _kit_documents,
    _motion_filter,
    _motion_profile,
    _outro_tail_seconds,
    _section_transition,
    _section_timing,
    _voice_filters,
)


ROOT = Path(__file__).resolve().parents[1]


class LocalVideoKitTests(unittest.TestCase):
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
        self.assertEqual(_outro_tail_seconds({"outroTailSeconds": 4.5}), 4.5)
        self.assertEqual(_outro_tail_seconds({"outroTailSeconds": -2}), 0.0)
        self.assertEqual(_outro_tail_seconds({"outroTailSeconds": 200}), 120.0)

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


if __name__ == "__main__":
    unittest.main()
