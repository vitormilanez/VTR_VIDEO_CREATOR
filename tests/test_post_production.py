from __future__ import annotations

import sqlite3
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.job_store import JobStore
from api.services.medical_identity import MEDICAL_MINIMUM_END_CARD_SECONDS
from api.services.transcript_service import normalize_transcript
from api.services.post_production import (
    analyze_post_production,
    caption_cues,
    render_preview,
    save_event_updates,
)
from api.services.visual_planner import (
    _anthropic_visual_plan,
    deterministic_visual_plan,
    normalize_visual_plan,
)
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
        self.assertEqual(transcript["normalizationVersion"], "ptbr-medical-v2")
        self.assertIn("Mounjaro", transcript["text"])
        self.assertIn("sintomas incomuns", transcript["text"])
        self.assertEqual([word["text"] for word in transcript["words"]][-2:], ["sintomas", "incomuns"])

    def test_normalizes_product_and_glp_one_terms_used_in_captions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"product-normalization")
            transcript = normalize_transcript(
                video_path=video,
                language="pt",
                duration_seconds=2,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0,
                        "end": 2,
                        "text": "A IPERA lança o SEMAV. Uma SEMA aglutida para GLP1.",
                        "words": [
                            {"start": 0, "end": 0.2, "text": "A"},
                            {"start": 0.2, "end": 0.5, "text": "IPERA"},
                            {"start": 0.5, "end": 0.8, "text": "lança"},
                            {"start": 0.8, "end": 1.0, "text": "SEMAV"},
                            {"start": 1.0, "end": 1.2, "text": "GLP1"},
                        ],
                    }
                ],
            )
        self.assertIn("Hypera lança o Semavy", transcript["text"])
        self.assertIn("semaglutida", transcript["text"])
        self.assertIn("GLP-1", transcript["text"])

    def test_plan_keeps_context_and_expands_short_event_to_readable_duration(self) -> None:
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
        self.assertEqual((event["startWordIndex"], event["endWordIndex"]), (0, 4))
        self.assertEqual(event["visualText"], "cuidado importante")
        self.assertNotEqual(event["id"], "old-id")

    def test_long_claude_range_is_capped_and_incomplete_copy_is_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"timed-plan")
            spoken_words = "A próxima geração combina dois sinais de saciedade ao mesmo tempo com clareza".split()
            transcript = normalize_transcript(
                video_path=video,
                language="pt",
                duration_seconds=8,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0,
                        "end": 8,
                        "text": " ".join(spoken_words),
                        "words": [
                            {
                                "start": index * 0.55,
                                "end": (index + 1) * 0.55,
                                "text": text,
                            }
                            for index, text in enumerate(spoken_words)
                        ],
                    }
                ],
            )
            plan = {
                "schemaVersion": "visual-plan-v1",
                "modelVersion": "fixture",
                "transcriptVersion": transcript["version"],
                "videoFingerprint": transcript["videoFingerprint"],
                "events": [
                    {
                        "id": "long",
                        "startWordIndex": 0,
                        "endWordIndex": len(spoken_words) - 1,
                        "interactionType": "comparison_card",
                        "visualText": "dois sinais de saciedade ao mesmo",
                        "intensity": "medium",
                        "reason": "fixture",
                        "confidence": 0.95,
                        "fallback": "caption_emphasis",
                    }
                ],
            }
            normalized = normalize_visual_plan(transcript, plan)
            timeline = materialize_timeline(transcript, normalized)

        event = timeline["events"][0]
        self.assertLessEqual(event["endMs"] - event["startMs"], 5000)
        self.assertEqual((event["startWordIndex"], event["endWordIndex"]), (4, 10))
        self.assertEqual(event["visualText"], "dois sinais de saciedade ao mesmo tempo")
        self.assertFalse(event["visualText"].endswith("ao mesmo"))

    def test_number_card_starts_when_the_approved_number_is_spoken(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"number-timing")
            words = "Na versão oral os participantes tiveram redução de cerca de 13 % do peso em 12 semanas".split()
            transcript = normalize_transcript(
                video_path=video,
                language="pt",
                duration_seconds=8,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0,
                        "end": 8,
                        "text": " ".join(words),
                        "words": [
                            {
                                "start": index * 0.45,
                                "end": (index + 1) * 0.45,
                                "text": text,
                            }
                            for index, text in enumerate(words)
                        ],
                    }
                ],
            )
            plan = {
                "schemaVersion": "visual-plan-v1",
                "modelVersion": "fixture",
                "transcriptVersion": transcript["version"],
                "videoFingerprint": transcript["videoFingerprint"],
                "events": [
                    {
                        "id": "number",
                        "startWordIndex": 0,
                        "endWordIndex": len(words) - 1,
                        "interactionType": "number_card",
                        "visualText": "13% peso 12 semanas",
                        "intensity": "high",
                        "reason": "fixture",
                        "confidence": 0.95,
                        "fallback": "caption_emphasis",
                    }
                ],
            }
            timeline = materialize_timeline(transcript, normalize_visual_plan(transcript, plan))

        event = timeline["events"][0]
        self.assertEqual(event["startWordIndex"], words.index("13"))
        self.assertEqual(event["startMs"], words.index("13") * 450)
        self.assertEqual(event["visualText"], "13% peso 12 semanas")
        self.assertLessEqual(event["endMs"] - event["startMs"], 5000)

    def test_supporting_visual_gets_generated_asset_and_incomplete_text_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
            plan = {
                "schemaVersion": "visual-plan-v1",
                "modelVersion": "fixture",
                "transcriptVersion": transcript["version"],
                "videoFingerprint": transcript["videoFingerprint"],
                "events": [
                    {
                        "id": "support",
                        "startWordIndex": 0,
                        "endWordIndex": 3,
                        "interactionType": "supporting_visual",
                        "visualText": "consulte seu médico e o",
                        "intensity": "medium",
                        "reason": "fixture",
                        "confidence": 1,
                        "fallback": "caption_emphasis",
                    }
                ],
            }
            normalized = normalize_visual_plan(transcript, plan)
        event = normalized["events"][0]
        self.assertFalse(event["visualText"].endswith(" o"))
        self.assertTrue(event["assetRef"].startswith("generated:"))

    def test_low_confidence_visual_is_removed_and_zero_events_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
            plan = deterministic_visual_plan(transcript)
            plan["events"][0]["confidence"] = 0.4
            plan["events"][1]["confidence"] = 0.4
            normalized = normalize_visual_plan(transcript, plan)

        self.assertEqual(normalized["events"], [])
        self.assertIn("Nenhuma intervenção", normalized["noVisualReason"])

    def test_caption_cues_are_short_word_timed_and_at_most_two_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
        cues = caption_cues(transcript)
        self.assertGreaterEqual(len(cues), 2)
        self.assertTrue(all(end - start <= 2800 for start, end, _text in cues))
        self.assertTrue(all(len(text.split()) <= 10 for _start, _end, text in cues))
        self.assertTrue(all(len(text.splitlines()) <= 2 for _start, _end, text in cues))

    def test_caption_cues_normalize_product_names_and_avoid_dangling_endings(self) -> None:
        transcript = {
            "words": [
                {"startMs": 0, "endMs": 300, "text": "A"},
                {"startMs": 300, "endMs": 600, "text": "IPERA"},
                {"startMs": 600, "endMs": 900, "text": "lança"},
                {"startMs": 900, "endMs": 1200, "text": "o"},
                {"startMs": 1200, "endMs": 1500, "text": "SEMAV"},
                {"startMs": 1500, "endMs": 1800, "text": "para"},
                {"startMs": 1800, "endMs": 2100, "text": "todo"},
                {"startMs": 2100, "endMs": 2400, "text": "mundo."},
            ]
        }
        cues = caption_cues(transcript)
        rendered = " ".join(text.replace("\n", " ") for _start, _end, text in cues)
        self.assertIn("Hypera", rendered)
        self.assertIn("Semavy", rendered)
        dangling = {" todo", " para", " não", " que"}
        self.assertFalse(
            any(
                text.replace("\n", " ").rstrip().casefold().endswith(tuple(dangling))
                for _start, _end, text in cues
            )
        )

    def test_captions_are_ready_even_when_claude_planning_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            job_id = "post-caption-first"
            directory = output_root / job_id
            directory.mkdir(parents=True)
            source = directory / "source.mp4"
            source.write_bytes(b"caption-first-video")
            transcript = normalize_transcript(
                video_path=source,
                language="pt",
                duration_seconds=2,
                model_version="fixture-v1",
                raw_segments=[
                    {
                        "start": 0.1,
                        "end": 1.8,
                        "text": "A legenda fica pronta antes do Claude.",
                        "words": [
                            {"start": 0.1, "end": 0.3, "text": "A"},
                            {"start": 0.3, "end": 0.7, "text": "legenda"},
                            {"start": 0.7, "end": 1.0, "text": "fica"},
                            {"start": 1.0, "end": 1.3, "text": "pronta"},
                            {"start": 1.3, "end": 1.5, "text": "antes"},
                            {"start": 1.5, "end": 1.6, "text": "do"},
                            {"start": 1.6, "end": 1.8, "text": "Claude."},
                        ],
                    }
                ],
            )
            (directory / "transcript.json").write_text(
                json.dumps(transcript),
                encoding="utf-8",
            )
            store = JobStore(root / "jobs.sqlite3")
            store.upsert(
                "post_production",
                {
                    "id": job_id,
                    "kind": "post_production",
                    "status": "queued",
                    "progresso": 2,
                    "requireClaude": True,
                    "criadoEm": "now",
                    "atualizadoEm": "now",
                },
            )

            with patch(
                "api.services.post_production.plan_visuals",
                side_effect=RuntimeError("Claude indisponível"),
            ):
                analyze_post_production(
                    store=store,
                    job_id=job_id,
                    output_root=output_root,
                    project_root=root,
                )

            current = store.get("post_production", job_id)
            captions = directory / "captions.srt"
            captions_exist = captions.is_file()
            captions_text = captions.read_text(encoding="utf-8")

        self.assertEqual(current["status"], "failed")
        self.assertEqual(current["captionsStatus"], "ready")
        self.assertGreater(current["captionCueCount"], 0)
        self.assertTrue(captions_exist)
        self.assertIn("legenda fica pronta", captions_text)

    def test_planner_uses_indices_and_backend_derives_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
            plan = deterministic_visual_plan(transcript)
            timeline = materialize_timeline(transcript, plan)
        self.assertNotIn("startMs", plan["events"][0])
        self.assertEqual(timeline["events"][0]["startMs"], 100)
        self.assertEqual(timeline["events"][0]["spokenText"], "Entenda este cuidado importante")
        self.assertEqual(timeline["events"][-1]["interactionType"], "cta_card")

    def test_claude_schema_uses_string_sentinel_and_receives_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = self._transcript(Path(temporary))
        captured: dict = {}
        response_payload = {
            "contentType": "educacional",
            "summary": "Resumo factual",
            "strategy": "Usar apenas um apoio relevante.",
            "noVisualReason": "",
            "events": [
                {
                    "startWordIndex": 0,
                    "endWordIndex": 3,
                    "interactionType": "supporting_visual",
                    "visualText": "cuidado importante",
                    "intensity": "medium",
                    "assetRef": "science",
                    "reason": "Esclarece o trecho.",
                    "confidence": 0.92,
                    "fallback": "caption_emphasis",
                }
            ],
        }

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    content=[SimpleNamespace(text=json.dumps(response_payload))]
                )

        fake_anthropic = types.ModuleType("anthropic")
        fake_anthropic.Anthropic = lambda: SimpleNamespace(messages=FakeMessages())
        with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            plan, _message, _model = _anthropic_visual_plan(
                transcript,
                model_name="claude-test",
            )

        asset_schema = captured["output_config"]["format"]["schema"]["properties"][
            "events"
        ]["items"]["properties"]["assetRef"]
        self.assertEqual(asset_schema["type"], "string")
        self.assertIn("none", asset_schema["enum"])
        self.assertNotIn(None, asset_schema["enum"])
        self.assertIn("0 [0.10s–0.45s]: Entenda", captured["messages"][0]["content"])
        self.assertEqual(plan["events"][0]["assetRef"], "generated:science")

    def test_stale_or_tampered_timeline_blocks_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = self._transcript(root)
            plan = normalize_visual_plan(transcript, deterministic_visual_plan(transcript))
            timeline = materialize_timeline(transcript, plan)
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
            plan = normalize_visual_plan(transcript, deterministic_visual_plan(transcript))
            timeline = materialize_timeline(transcript, plan)
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

    def test_preflight_blocks_visual_shorter_than_one_point_five_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = self._transcript(root)
            timeline = materialize_timeline(transcript, deterministic_visual_plan(transcript))
            timeline["events"][-1]["enabled"] = False
            report = preflight_timeline(
                source_path=root / "source.mp4",
                transcript_payload=transcript,
                timeline_payload=timeline,
                require_render_tools=False,
            )
        self.assertFalse(report["ok"])
        finding = next(item for item in report["findings"] if item["code"] == "event.duration")
        self.assertEqual(finding["classification"], "BLOCKER")

    def test_individual_event_type_can_be_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-1"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(transcript, normalize_visual_plan(transcript, deterministic_visual_plan(transcript)))
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

            updated = save_event_updates(
                output_root=output_root,
                job_id="post-1",
                updates=[{"id": timeline["events"][0]["id"], "interactionType": "supporting_visual"}],
            )

        self.assertEqual(updated["events"][0]["interactionType"], "supporting_visual")
        self.assertTrue(updated["events"][0]["assetRef"].startswith("generated:"))

    def test_individual_event_can_use_a_generic_visual_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-1"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(
                transcript,
                normalize_visual_plan(transcript, deterministic_visual_plan(transcript)),
            )
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

            updated = save_event_updates(
                output_root=output_root,
                job_id="post-1",
                updates=[
                    {
                        "id": timeline["events"][0]["id"],
                        "interactionType": "definition_card",
                    }
                ],
            )

        self.assertEqual(updated["events"][0]["interactionType"], "definition_card")

    def test_individual_event_appearance_is_saved_locally_without_replanning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-appearance"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(
                transcript,
                normalize_visual_plan(transcript, deterministic_visual_plan(transcript)),
            )
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

            updated = save_event_updates(
                output_root=output_root,
                job_id="post-appearance",
                updates=[
                    {
                        "id": timeline["events"][0]["id"],
                        "screenPosition": "bottom_left",
                        "backgroundColor": "#4A1F2B",
                        "backgroundOpacity": 0.55,
                    }
                ],
            )

        event = updated["events"][0]
        self.assertEqual(event["screenPosition"], "bottom_left")
        self.assertEqual(event["backgroundColor"], "#4a1f2b")
        self.assertEqual(event["backgroundOpacity"], 0.55)

    def test_individual_event_can_use_exact_manual_entry_and_exit_times(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-manual-time"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(
                transcript,
                normalize_visual_plan(transcript, deterministic_visual_plan(transcript)),
            )
            (directory / "source.mp4").write_bytes((root / "source.mp4").read_bytes())
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            selected = timeline["events"][0]
            updates = [
                {"id": event["id"], "enabled": event["id"] == selected["id"]}
                for event in timeline["events"]
            ]
            updates[0].update(startMs=250, endMs=1850)

            updated = save_event_updates(
                output_root=output_root,
                job_id="post-manual-time",
                updates=updates,
            )
            report = preflight_timeline(
                source_path=directory / "source.mp4",
                transcript_payload=transcript,
                timeline_payload=updated,
                require_render_tools=False,
            )

        changed = updated["events"][0]
        self.assertEqual((changed["startMs"], changed["endMs"]), (250, 1850))
        self.assertEqual(changed["timingSource"], "manual")
        self.assertFalse(any(item["code"] == "event.time_derivation" for item in report["findings"]))
        self.assertTrue(report["ok"])

    def test_manual_event_time_can_be_restored_from_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-reset-time"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(
                transcript,
                normalize_visual_plan(transcript, deterministic_visual_plan(transcript)),
            )
            event = timeline["events"][0]
            event.update(startMs=250, endMs=1850, timingSource="manual")
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

            updated = save_event_updates(
                output_root=output_root,
                job_id="post-reset-time",
                updates=[{"id": event["id"], "timingSource": "transcript"}],
            )

        restored = updated["events"][0]
        self.assertEqual(restored["timingSource"], "transcript")
        self.assertEqual(restored["startMs"], transcript["words"][event["startWordIndex"]]["startMs"])
        self.assertEqual(restored["endMs"], transcript["words"][event["endWordIndex"]]["endMs"])

    def test_manual_event_time_rejects_invalid_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "post-production"
            directory = output_root / "post-invalid-time"
            directory.mkdir(parents=True)
            transcript = self._transcript(root)
            timeline = materialize_timeline(
                transcript,
                normalize_visual_plan(transcript, deterministic_visual_plan(transcript)),
            )
            (directory / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
            (directory / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "entre 1,5 e 5,5"):
                save_event_updates(
                    output_root=output_root,
                    job_id="post-invalid-time",
                    updates=[{"id": timeline["events"][0]["id"], "startMs": 900, "endMs": 1200}],
                )

    def test_duplicate_upload_reuses_analysis_for_new_upload_id_and_generates_pack(self) -> None:
        from api import server

        class DuplicateStore:
            def __init__(self) -> None:
                self.job = {
                    "id": "post-1234567890abcdef",
                    "kind": "post_production",
                    "uploadId": "kit-upload-aaaaaaaaaaaaaaaa",
                    "status": "needs_review",
                    "plannerMode": "anthropic",
                    "requireClaude": True,
                    "packStatus": "failed",
                }

            def reserve(self, *_args, **_kwargs):
                return self.job, "duplicate"

            def upsert(self, _kind, job):
                self.job = dict(job)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uploads = root / "uploads"
            outputs = root / "post-production"
            uploads.mkdir()
            new_upload_id = "kit-upload-bbbbbbbbbbbbbbbb"
            (uploads / f"{new_upload_id}.mp4").write_bytes(b"same-video")
            existing = outputs / "post-1234567890abcdef"
            existing.mkdir(parents=True)
            (existing / "source.mp4").write_bytes(b"same-video")
            store = DuplicateStore()
            with (
                patch.object(server, "LOCAL_VIDEO_KIT_UPLOADS", uploads),
                patch.object(server, "POST_PRODUCTION_OUTPUTS", outputs),
                patch.object(server, "_job_store", return_value=store),
                patch.object(server, "_launch_post_production_analysis") as launch,
            ):
                response = server.create_post_production(
                    server.PostProductionCreateIn(
                        uploadId=new_upload_id,
                        sourceName="video.mp4",
                        requireClaude=True,
                        generatePack=True,
                    )
                )

        self.assertTrue(response["duplicate"])
        self.assertEqual(response["job"]["uploadId"], new_upload_id)
        self.assertEqual(response["job"]["status"], "queued")
        launch.assert_called_once_with("post-1234567890abcdef")


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
            self.assertTrue((directory / "medical-end-card.png").is_file())
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["timelineVersion"], timeline["version"])
            self.assertEqual(manifest["composition"]["segments"][-1]["kind"], "medical_end_card")
            self.assertEqual(
                manifest["composition"]["segments"][-1]["durationSeconds"],
                MEDICAL_MINIMUM_END_CARD_SECONDS,
            )
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
            self.assertAlmostEqual(
                float(metadata["format"]["duration"]),
                2 + MEDICAL_MINIMUM_END_CARD_SECONDS,
                delta=0.2,
            )
