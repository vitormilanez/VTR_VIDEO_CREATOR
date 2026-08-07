from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from api.video_slides import render_video_slides, video_slide_html


class VideoSlidesTests(unittest.TestCase):
    def test_html_is_vertical_and_escapes_copy(self) -> None:
        scene = {
            "sceneId": "scene-1",
            "visual": {
                "type": "full_slide",
                "layout": "big_statement",
                "headline": "Contexto < importa",
                "body": "Texto complementar",
                "purpose": "reforçar",
            },
        }
        html = video_slide_html(scene, index=1, total=2)
        self.assertIn("width: 1080px", html)
        self.assertIn("height: 1920px", html)
        self.assertIn("Contexto &lt; importa", html)
        self.assertNotIn("Contexto < importa", html)

    def test_renderer_skips_none_and_generates_1080x1920_png(self) -> None:
        plan = {
            "scenes": [
                {
                    "sceneId": "scene-1",
                    "visual": {
                        "type": "full_slide",
                        "layout": "big_statement",
                        "headline": "Uma ideia",
                        "body": "Apoio curto",
                        "purpose": "clareza",
                    },
                },
                {
                    "sceneId": "scene-2",
                    "visual": {"type": "none", "layout": "", "headline": "", "body": "", "purpose": ""},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = render_video_slides(Path(temporary), plan)
            self.assertEqual(result["width"], 1080)
            self.assertEqual(result["height"], 1920)
            self.assertEqual(result["renderedCount"], 1)
            png = Path(temporary) / "scene-01.png"
            raw = png.read_bytes()
            self.assertEqual(raw[:8], bytes.fromhex("89504e470d0a1a0a"))
            self.assertEqual(struct.unpack(">II", raw[16:24]), (1080, 1920))
            self.assertIsNone(result["assets"][1]["assetPath"])


if __name__ == "__main__":
    unittest.main()
