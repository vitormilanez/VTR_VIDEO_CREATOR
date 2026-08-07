from __future__ import annotations

import sqlite3
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from api.job_store import JobStore
from api.services.transcript_service import normalize_transcript
from api.services.post_production import render_preview
from api.services.visual_planner import deterministic_visual_plan, normalize_visual_plan
from api.services.visual_timeline import materialize_timeline, preflight_timeline, timeline_is_stale


class PostProductionContractTests(unittest.TestCase):
    def _transcript(self, root: Path) -> dict:
        video = root / "source.mp4"
        video.write_bytes(b"stable-video-fixture")
        return normalize_transcript(
            video_path=video,
            language="pt",
            duration_seconds=3.2,
            model_version="fixture-v1",
            raw_segments=[
                {
                    "start": 0.1,
                    "end": 1.4,
                    "text": "Entenda este cuidado importante.",
                    "words": [
                        {"start": 0.1, "end": 0.45, "text": "Entenda"},
                        {"start": 0.46, "end": 0.75, "text": "este"},
                        {"start": 0.76, "end": 1.05, "text": "cuidado"},
                        {"start": 1.06, "end": 1.4, "text": "importante"},
                    ],
                },
                {
                    "start": 1.55,
                    "end": 3.0,
                    "text": "Salve e consulte seu médico.",
                    "words": [
                        {"start": 1.55, "end": 1.9, "text": "Salve"},
                        {"start": 1.91, "end": 2.05, "text": "e"},
                        {"start": 2.06, "end": 2.5, "text": "consulte"},
                        {"start": 2.51, "end": 2.7, "text": "seu"},
                        {"start": 2.71, "end": 3.0, "text": "médico"},
                    ],
                },
            ],
        )

    def test_transcript_has_stable_indexed_words_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
        self.assertEqual(transcript["schemaVersion"], "transcript-v1")
        self.assertTrue(transcript["videoFingerprint"].startswith("sha256:"))
        self.assertEqual([word["index"] for word in transcript["words"]], list(range(9)))
        self.assertEqual(transcript["words"][0]["startMs"], 100)
        self.assertEqual(transcript["segments"][1]["startWordIndex"], 4)
        self.assertIn("duration", transcript)  # backwards-compatible Cuts field

    def test_normalizes_medical_terms_and_merges_whisper_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"medical-normalization")
            transcript = normalize_transcript(
                video_path=video,
                language="pt",
                duration_seconds=2,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0,
                        "end": 2,
                        "text": "O monjaro e sintomas em comuns.",
                        "words": [
                            {"start": 0, "end": 0.2, "text": "O"},
                            {"start": 0.2, "end": 0.6, "text": "monjaro"},
                            {"start": 0.6, "end": 0.8, "text": "e"},
                            {"start": 0.8, "end": 1.2, "text": "sintomas"},
                            {"start": 1.2, "end": 1.4, "text": "em"},
                            {"start": 1.4, "end": 2, "text": "comuns"},
                        ],
                    }
                ],
            )
        self.assertEqual(transcript["normalizationVersion"], "ptbr-medical-v1")
        self.assertIn("Mounjaro", transcript["text"])
        self.assertIn("sintomas incomuns", transcript["text"])
        self.assertEqual([word["text"] for word in transcript["words"]][-2:], ["sintomas", "incomuns"])

    def test_plan_range_is_tightened_to_the_visual_words(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
            plan = {
                "schemaVersion": "visual-plan-v1",
                "modelVersion": "fixture",
                "transcriptVersion": transcript["version"],
                "videoFingerprint": transcript["videoFingerprint"],
                "events": [
                    {
                        "id": "old-id",
                        "startWordIndex": 0,
                        "endWordIndex": 3,
                        "interactionType": "caption_emphasis",
                        "visualText": "cuidado importante",
                        "intensity": "medium",
                        "reason": "fixture",
                        "confidence": 1,
                        "fallback": "caption_emphasis",
                    }
                ],
            }
            normalized = normalize_visual_plan(transcript, plan)
        event = normalized["events"][0]
        self.assertEqual((event["startWordIndex"], event["endWordIndex"]), (2, 3))
        self.assertNotEqual(event["id"], "old-id")

    def test_planner_uses_indices_and_backend_derives_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
            plan = deterministic_visual_plan(transcript)
            timeline = materialize_timeline(transcript, plan)
        self.assertNotIn("startMs", plan["events"][0])
        self.assertEqual(timeline["events"][0]["startMs"], 100)
        self.assertEqual(timeline["events"][0]["spokenText"], "Entenda este cuidado importante")
        self.assertEqual(timeline["events"][-1]["interactionType"], "cta_card")

    def test_stale_or_tampered_timeline_blocks_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = self._transcript(root)
            timeline = materialize_timeline(transcript, deterministic_visual_plan(transcript))
            timeline["events"][0]["startMs"] = 999
            timeline["videoFingerprint"] = "sha256:old"
            report = preflight_timeline(
                source_path=root / "source.mp4",
                transcript_payload=transcript,
                timeline_payload=timeline,
                require_render_tools=False,
            )
        self.assertFalse(report["ok"])
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("timeline.stale", codes)
        self.assertIn("event.time_derivation", codes)
        self.assertTrue(timeline_is_stale(timeline, transcript))

    def test_visual_text_warning_and_valid_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = self._transcript(root)
            timeline = materialize_timeline(transcript, deterministic_visual_plan(transcript))
            timeline["events"][0]["visualText"] = "x" * 81
            report = preflight_timeline(
                source_path=root / "source.mp4",
                transcript_payload=transcript,
                timeline_payload=timeline,
                require_render_tools=False,
            )
        self.assertTrue(report["ok"])
        warning = next(item for item in report["findings"] if item["code"] == "event.text_length")
        self.assertEqual(warning["classification"], "WARNING")


class JobStorePostProductionMigrationTests(unittest.TestCase):
    def test_migrates_old_check_and_preserves_existing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "operations.db"
            connection = sqlite3.connect(database)
            connection.execute(
                """CREATE TABLE operational_jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('video', 'avatar', 'cut')),
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    script_id TEXT,
                    remote_session_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO operational_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("cut-1", "cut", "pronto", None, None, None, '{"id":"cut-1","status":"pronto"}', "a", "a"),
            )
            connection.commit()
            connection.close()

            store = JobStore(database)
            self.assertEqual(store.get("cut", "cut-1")["status"], "pronto")
            store.upsert(
                "post_production",
                {"id": "post-1", "status": "queued", "criadoEm": "b", "atualizadoEm": "b"},
            )
            self.assertEqual(store.get("post_production", "post-1")["status"], "queued")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class PostProductionEndToEndTests(unittest.TestCase):
    def test_fixture_transcript_to_preview_without_paid_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            job_id = "post-fixture"
            directory = output_root / job_id
            directory.mkdir(parents=True)
            source = directory / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x568:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=700:duration=2", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", str(source),
                ],
                check=True,
                capture_output=True,
            )
            source_before = source.read_bytes()
            transcript = normalize_transcript(
                video_path=source,
                language="pt",
                duration_seconds=2,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0.1,
                        "end": 1.8,
                        "text": "Salve este cuidado e consulte seu médico.",
                        "words": [
                            {"start": 0.1, "end": 0.35, "text": "Salve"},
                            {"start": 0.36, "end": 0.58, "text": "este"},
                            {"start": 0.59, "end": 0.9, "text": "cuidado"},
                            {"start": 0.91, "end": 1.05, "text": "e"},
                            {"start": 1.06, "end": 1.35, "text": "consulte"},
                            {"start": 1.36, "end": 1.55, "text": "seu"},
                            {"start": 1.56, "end": 1.8, "text": "médico"},
                        ],
                    }
                ],
            )
            timeline = materialize_timeline(transcript, deterministic_visual_plan(transcript))
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            store = JobStore(root / "operations.db")
            store.upsert(
                "post_production",
                {
                    "id": job_id,
                    "kind": "post_production",
                    "videoJobId": "video-1",
                    "status": "needs_review",
                    "progresso": 80,
                    "criadoEm": "2026-08-07T00:00:00+00:00",
                    "atualizadoEm": "2026-08-07T00:00:00+00:00",
                },
            )

            job = render_preview(store=store, job_id=job_id, output_root=output_root)

            self.assertEqual(job["status"], "preview_ready")
            self.assertEqual(source.read_bytes(), source_before)
            self.assertTrue((directory / "preview.mp4").is_file())
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["timelineVersion"], timeline["version"])
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                    "-show_entries", "format=duration", "-of", "json",
                    str(directory / "preview.mp4"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            self.assertEqual({stream["codec_type"] for stream in metadata["streams"]}, {"video", "audio"})
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 2, delta=0.2)
