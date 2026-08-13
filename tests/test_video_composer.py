from __future__ import annotations

import json
from array import array
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api import server
from api.services import video_composer
from api.services.video_composer import (
    CompositionScene,
    TimedOverlay,
    TimedVideoOverlay,
    compose_video,
)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class VideoComposerTests(unittest.TestCase):
    def _mock_video(
        self, path: Path, color: str, *, duration: float = 0.7, frequency: int = 900
    ) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x240:d={duration}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:duration={duration}",
                "-shortest",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def _sample_rgb(self, path: Path, seconds: float) -> tuple[int, int, int]:
        process = subprocess.run(
            [
                "ffmpeg",
                "-ss",
                str(seconds),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=1:1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        )
        return tuple(process.stdout[:3])  # type: ignore[return-value]

    def _audio_frequency(self, path: Path, duration: float) -> float:
        process = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-f",
                "s16le",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        )
        samples = array("h")
        samples.frombytes(process.stdout)
        crossings = sum(
            1
            for previous, current in zip(samples, samples[1:])
            if (previous < 0 <= current) or (previous >= 0 > current)
        )
        return crossings / (2 * duration)

    def _mock_image(self, path: Path, color: str) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1080x1920:d=1",
                "-frames:v",
                "1",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def test_composes_mock_scenes_with_slide_overlay_and_captions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_one = root / "scene-one.mp4"
            scene_two = root / "scene-two.mp4"
            slide = root / "slide.png"
            overlay = root / "overlay.png"
            captions = root / "scene-one.srt"
            output = root / "final.mp4"
            self._mock_video(scene_one, "blue")
            self._mock_video(scene_two, "yellow")
            self._mock_image(slide, "red")
            self._mock_image(overlay, "green")
            captions.write_text(
                "1\n00:00:00,000 --> 00:00:00,500\nFala da cena\n",
                encoding="utf-8",
            )

            result = compose_video(
                [
                    CompositionScene(
                        "scene-1",
                        scene_one,
                        slide_path=slide,
                        slide_duration_seconds=0.3,
                        overlay_paths=(overlay,),
                        captions_path=captions,
                    ),
                    CompositionScene("scene-2", scene_two),
                ],
                output,
            )

            self.assertTrue(output.is_file())
            self.assertEqual(result["cutPolicy"], "hard_cut")
            self.assertEqual(result["sceneCount"], 2)
            self.assertEqual(result["segmentCount"], 3)
            self.assertEqual(
                [segment["kind"] for segment in result["segments"]],
                ["avatar", "video_slide", "avatar"],
            )
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((stream["width"], stream["height"]), (1080, 1920))

    def test_can_show_slide_during_avatar_audio_without_extra_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_one = root / "scene-one.mp4"
            scene_two = root / "scene-two.mp4"
            slide = root / "slide.png"
            output = root / "final.mp4"
            self._mock_video(scene_one, "blue")
            self._mock_video(scene_two, "yellow")
            self._mock_image(slide, "red")

            result = compose_video(
                [
                    CompositionScene(
                        "scene-1",
                        scene_one,
                        slide_path=slide,
                        slide_mode="during",
                        visual_start_seconds=0.1,
                        slide_duration_seconds=0.35,
                    ),
                    CompositionScene("scene-2", scene_two),
                ],
                output,
            )

            self.assertTrue(output.is_file())
            self.assertEqual(result["segmentCount"], 2)
            self.assertEqual(
                result["segments"][0]["visualOverlay"],
                {
                    "kind": "video_slide",
                    "startSeconds": 0.1,
                    "durationSeconds": 0.35,
                    "animation": "fade",
                    "audioSource": "avatar",
                },
            )
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            self.assertLess(duration, 1.8)

    def test_mocked_technical_silence_trim_keeps_hard_cut_audio_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_one = root / "scene-one.mp4"
            scene_two = root / "scene-two.mp4"
            output = root / "final.mp4"
            self._mock_video(scene_one, "blue", frequency=440)
            self._mock_video(scene_two, "yellow", frequency=660)

            with patch.object(
                video_composer,
                "_technical_silence_padding",
                side_effect=[(0.1, 0.1), (0.1, 0.1)],
            ) as silence_detector:
                result = compose_video(
                    [
                        CompositionScene("scene-1", scene_one, trim_technical_silence=True),
                        CompositionScene("scene-2", scene_two, trim_technical_silence=True),
                    ],
                    output,
                    transition_style="hard_cut",
                )

            self.assertTrue(output.is_file())
            self.assertEqual(silence_detector.call_count, 2)
            self.assertEqual(result["cutPolicy"], "hard_cut")
            self.assertEqual(
                [segment["technicalSilenceTrim"] for segment in result["segments"]],
                [
                    {"leadingSeconds": 0.1, "trailingSeconds": 0.1},
                    {"leadingSeconds": 0.1, "trailingSeconds": 0.1},
                ],
            )

    def test_composes_two_scenes_with_smooth_transition_and_no_slide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_one = root / "scene-one.mp4"
            scene_two = root / "scene-two.mp4"
            output = root / "final.mp4"
            self._mock_video(scene_one, "blue")
            self._mock_video(scene_two, "yellow")

            result = compose_video(
                [
                    CompositionScene("scene-1", scene_one),
                    CompositionScene("scene-2", scene_two),
                ],
                output,
                transition_style="smooth",
            )

            self.assertTrue(output.is_file())
            self.assertEqual(result["cutPolicy"], "smooth")
            self.assertEqual(result["segmentCount"], 2)
            self.assertEqual(len(result["transitions"]), 1)
            self.assertEqual(result["transitions"][0]["style"], "smooth")
            self.assertNotIn("visualOverlay", result["segments"][0])

    def test_fade_dark_uses_a_short_fade_through_black(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(video_composer, "_probe_duration", return_value=1.0), patch.object(
                video_composer, "_run"
            ) as run:
                transitions = video_composer._transition_segments(
                    [root / "scene-one.mp4", root / "scene-two.mp4"],
                    root / "final.mp4",
                    style="dip_to_black",
                    ffmpeg="ffmpeg",
                )

            command = run.call_args.args[0]
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("transition=fadeblack", filters)
            self.assertEqual(transitions[0]["style"], "dip_to_black")
            self.assertEqual(transitions[0]["durationSeconds"], 0.25)

    def test_timed_overlay_keeps_original_duration_and_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            overlay = root / "overlay.png"
            output = root / "preview.mp4"
            self._mock_video(source, "blue")
            self._mock_image(overlay, "green")

            compose_video(
                [
                    CompositionScene(
                        "post-production",
                        source,
                        timed_overlays=(TimedOverlay(overlay, 0.15, 0.5),),
                    )
                ],
                output,
            )

            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                    "-show_entries", "format=duration", "-of", "json", str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            self.assertEqual({stream["codec_type"] for stream in metadata["streams"]}, {"video", "audio"})
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 0.7, delta=0.15)

    def test_full_screen_shots_keep_base_narration_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "narration.mp4"
            first_shot = root / "shot-01.mp4"
            second_shot = root / "shot-02.mp4"
            output = root / "story.mp4"
            self._mock_video(narration, "blue", duration=2.4, frequency=900)
            self._mock_video(first_shot, "red", duration=1.2, frequency=250)
            self._mock_video(second_shot, "green", duration=1.2, frequency=350)

            manifest = compose_video(
                [
                    CompositionScene(
                        "story-mode",
                        narration,
                        timed_video_overlays=(
                            TimedVideoOverlay(first_shot, 0, 1.2, "shot-01"),
                            TimedVideoOverlay(second_shot, 1.2, 2.4, "shot-02"),
                        ),
                    )
                ],
                output,
            )

            overlays = manifest["segments"][0]["timedVideoOverlays"]
            self.assertEqual([overlay["shotId"] for overlay in overlays], ["shot-01", "shot-02"])
            self.assertTrue(all(overlay["generatedAudioMuted"] for overlay in overlays))
            first_rgb = self._sample_rgb(output, 0.5)
            second_rgb = self._sample_rgb(output, 1.7)
            self.assertGreater(first_rgb[0], first_rgb[1])
            self.assertGreater(second_rgb[1], second_rgb[0])
            self.assertAlmostEqual(self._audio_frequency(output, 2.4), 900, delta=80)

    def test_two_camera_final_output_has_no_music_and_keeps_the_verified_cut_policy(self) -> None:
        with tempfile.TemporaryDirectory(dir=server.ROOT / "data") as temporary:
            root = Path(temporary)
            original_database = server.OPERATIONAL_DB
            original_composed_videos = server.COMPOSED_VIDEO_OUTPUTS
            original_script_exports = server.SCRIPT_EXPORTS
            server.OPERATIONAL_DB = root / "operations.db"
            server.COMPOSED_VIDEO_OUTPUTS = root / "composed_videos"
            server.SCRIPT_EXPORTS = root / "Exports" / "roteiro"
            try:
                script_id = "script-two-camera-compose"
                avatar_set = server._save_avatar_set(
                    name="Dr. Teste",
                    voice_id="voice-fixed",
                    looks=[
                        {"avatarId": "look-standing", "role": "standing", "label": "Em pé"},
                        {"avatarId": "look-seated", "role": "seated", "label": "Sentado"},
                    ],
                )
                server._save_production_profile(
                    {
                        "scriptId": script_id,
                        "avatarId": "look-standing",
                        "primaryAvatarId": "look-standing",
                        "avatarSetId": avatar_set["id"],
                        "avatarMode": "set",
                        "voiceId": "voice-fixed",
                        "speechMode": "natural",
                        "generationMode": "direct",
                        "musicTrackId": "must-be-ignored",
                    }
                )
                server._save_scene_plan(
                    script_id,
                    [
                        {"id": "scene-1", "text": "Abertura.", "lookRole": "standing"},
                        {"id": "scene-2", "text": "Explicação.", "lookRole": "seated"},
                    ],
                )
                for index, (scene_id, avatar_id, color) in enumerate(
                    (
                        ("scene-1", "look-standing", "blue"),
                        ("scene-2", "look-seated", "yellow"),
                    ),
                    start=1,
                ):
                    path = root / f"{scene_id}.mp4"
                    self._mock_video(path, color)
                    server._job_store().upsert(
                        "video",
                        {
                            "id": f"sv-two-camera-{index}",
                            "scriptId": script_id,
                            "status": "pronto",
                            "provider": "heygen",
                            "progresso": 100,
                            "criadoEm": f"2026-08-11T12:00:0{index}+00:00",
                            "atualizadoEm": f"2026-08-11T12:01:0{index}+00:00",
                            "isScene": True,
                            "sceneBatchId": "batch-two-camera",
                            "sceneId": scene_id,
                            "sceneOrder": index,
                            "finalSpeechHash": server.hash_text("Abertura. Explicação."),
                            "productionSettings": {"avatarId": avatar_id},
                            "outputPath": str(path.relative_to(server.ROOT)),
                        },
                    )

                with patch.object(
                    server,
                    "_find_script",
                    return_value={"textoFalado": "Abertura. Explicação.", "outroText": ""},
                ):
                    result = server._compose_final_video_if_ready(
                        script_id, raise_when_not_ready=True
                    )

                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result["transitionStyle"], "hard_cut")
                self.assertIsNone(result["backgroundMusic"])
                self.assertEqual(result["continuity"]["mode"], "two_camera_locked")
                self.assertFalse(result["continuity"]["backgroundMusic"])
                self.assertTrue(result["continuity"]["technicalSilenceTrim"])
                self.assertEqual(result["composition"]["cutPolicy"], "hard_cut")
                self.assertEqual(result["sourceSceneJobs"], ["sv-two-camera-1", "sv-two-camera-2"])
                self.assertEqual(result["exportVersion"], "1.1")
                export_directory = server.ROOT / result["exportPath"]
                self.assertTrue((export_directory / "video-final.mp4").is_file())
                self.assertEqual(len(list((export_directory / "tomadas").glob("*.mp4"))), 2)
            finally:
                server.OPERATIONAL_DB = original_database
                server.COMPOSED_VIDEO_OUTPUTS = original_composed_videos
                server.SCRIPT_EXPORTS = original_script_exports

    def test_server_composes_ready_scene_jobs_into_one_local_final_job(self) -> None:
        with tempfile.TemporaryDirectory(dir=server.ROOT / "data") as temporary:
            root = Path(temporary)
            original_database = server.OPERATIONAL_DB
            original_video_slides = server.VIDEO_SLIDE_OUTPUTS
            original_composed_videos = server.COMPOSED_VIDEO_OUTPUTS
            original_script_exports = server.SCRIPT_EXPORTS
            server.OPERATIONAL_DB = root / "operations.db"
            server.VIDEO_SLIDE_OUTPUTS = root / "video_slides"
            server.COMPOSED_VIDEO_OUTPUTS = root / "composed_videos"
            server.SCRIPT_EXPORTS = root / "Exports" / "roteiro"
            try:
                script_id = "script-compose"
                server._save_production_profile(
                    {
                        "scriptId": script_id,
                        "avatarId": "look-1",
                        "voiceId": "voice-1",
                        "speechMode": "natural",
                        "generationMode": "direct",
                    }
                )
                server._save_scene_plan(
                    script_id,
                    [
                        {"id": "scene-1", "text": "Cena um.", "lookRole": "primary"},
                        {"id": "scene-2", "text": "Cena dois.", "lookRole": "secondary"},
                        {"id": "scene-3", "text": "Cena três.", "lookRole": "primary"},
                    ],
                )
                scene_paths = []
                for index, color in enumerate(("blue", "yellow", "green"), start=1):
                    path = root / f"scene-{index}.mp4"
                    self._mock_video(path, color)
                    scene_paths.append(path)
                    server._job_store().upsert(
                        "video",
                        {
                            "id": f"sv-{index}",
                            "scriptId": script_id,
                            "status": "pronto",
                            "provider": "heygen",
                            "progresso": 100,
                            "criadoEm": f"2026-08-07T00:00:0{index}+00:00",
                            "atualizadoEm": f"2026-08-07T00:00:1{index}+00:00",
                            "isScene": True,
                            "sceneId": f"scene-{index}",
                            "sceneOrder": index,
                            "finalSpeechHash": server.hash_text(
                                "Cena um. Cena dois. Cena três."
                            ),
                            "outputPath": str(path.relative_to(server.ROOT)),
                        },
                    )
                slide_root = server._video_slide_output_dir(script_id)
                slide_root.mkdir(parents=True, exist_ok=True)
                slide_one = slide_root / "slide-1.png"
                slide_two = slide_root / "slide-2.png"
                self._mock_image(slide_one, "red")
                self._mock_image(slide_two, "purple")
                server._save_visual_plan(
                    script_id,
                    {
                        "scriptId": script_id,
                        "designSystemVersion": server.VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
                        "promptVersion": server.VISUAL_DIRECTOR_PROMPT_VERSION,
                        "scenes": [
                            {
                                "sceneId": "scene-1",
                                "visual": {
                                    "type": "full_slide",
                                    "layout": "big_statement",
                                    "headline": "Primeiro apoio",
                                    "body": "",
                                    "purpose": "Apoiar a fala",
                                    "startRatio": 0.25,
                                    "durationSeconds": 1.0,
                                    "motionPreset": "fade",
                                },
                            },
                            {
                                "sceneId": "scene-2",
                                "visual": {
                                    "type": "comparison",
                                    "layout": "myth_fact",
                                    "headline": "Segundo apoio",
                                    "body": "",
                                    "purpose": "Apoiar a fala",
                                    "startRatio": 0.35,
                                    "durationSeconds": 1.0,
                                    "motionPreset": "fade_zoom",
                                },
                            },
                            {
                                "sceneId": "scene-3",
                                "visual": {
                                    "type": "none",
                                    "layout": "",
                                    "headline": "",
                                    "body": "",
                                    "purpose": "",
                                    "startRatio": 0,
                                    "durationSeconds": 0,
                                    "motionPreset": "none",
                                },
                            },
                        ],
                    },
                )
                server._save_video_slide_render(
                    script_id,
                    {
                        "width": 1080,
                        "height": 1920,
                        "scale": 1,
                        "sceneCount": 3,
                        "renderedCount": 2,
                        "assets": [
                            {
                                "sceneId": "scene-1",
                                "index": 1,
                                "type": "full_slide",
                                "layout": "big_statement",
                                "headline": "Primeiro apoio",
                                "body": "",
                                "assetPath": slide_one.name,
                            },
                            {
                                "sceneId": "scene-2",
                                "index": 2,
                                "type": "comparison",
                                "layout": "myth_fact",
                                "headline": "Segundo apoio",
                                "body": "",
                                "assetPath": slide_two.name,
                            },
                            {
                                "sceneId": "scene-3",
                                "index": 3,
                                "type": "none",
                                "layout": "",
                                "headline": "",
                                "body": "",
                                "assetPath": None,
                            },
                        ],
                    },
                )

                with patch.object(
                    server,
                    "_find_script",
                    return_value={
                        "textoFalado": "Cena um. Cena dois. Cena três.",
                        "outroText": "",
                    },
                ):
                    result = server._compose_final_video_if_ready(
                        script_id, raise_when_not_ready=True
                    )

                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result["provider"], "local")
                self.assertTrue(result["isComposed"])
                self.assertEqual(result["status"], "pronto")
                self.assertEqual(result["sceneCount"], 3)
                self.assertEqual(result["visualCount"], 0)
                self.assertEqual(result["transitionStyle"], "hard_cut")
                self.assertEqual(result["sourceSceneJobs"], ["sv-1", "sv-2", "sv-3"])
                output_path = server.ROOT / result["outputPath"]
                self.assertTrue(output_path.is_file())
                self.assertEqual(result["composition"]["segmentCount"], 4)
                self.assertEqual(result["composition"]["cutPolicy"], "hard_cut")
                self.assertNotIn("visualOverlay", result["composition"]["segments"][0])
                self.assertNotIn("visualOverlay", result["composition"]["segments"][1])
                self.assertNotIn("visualOverlay", result["composition"]["segments"][2])
                self.assertEqual(
                    result["composition"]["segments"][3]["kind"],
                    "medical_end_card",
                )
                self.assertEqual(result["exportVersion"], "1.1")
            finally:
                server.OPERATIONAL_DB = original_database
                server.VIDEO_SLIDE_OUTPUTS = original_video_slides
                server.COMPOSED_VIDEO_OUTPUTS = original_composed_videos
                server.SCRIPT_EXPORTS = original_script_exports


if __name__ == "__main__":
    unittest.main()
