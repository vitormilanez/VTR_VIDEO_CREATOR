from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.services.local_video_kit import (
    _detect_flat_horizontal_bars,
    _kit_documents,
)


ROOT = Path(__file__).resolve().parents[1]


class LocalVideoKitTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
