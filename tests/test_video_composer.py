from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from api.services.video_composer import CompositionScene, compose_video


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class VideoComposerTests(unittest.TestCase):
    def _mock_video(self, path: Path, color: str) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x240:d=0.7",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=900:duration=0.7",
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


if __name__ == "__main__":
    unittest.main()
