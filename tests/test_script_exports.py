from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from api.services.script_exports import archive_script_generation


class ScriptExportTests(unittest.TestCase):
    def test_versions_are_sequential_and_idempotent_for_the_same_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_video = root / "first.mp4"
            second_video = root / "second.mp4"
            first_video.write_bytes(b"first-version")
            second_video.write_bytes(b"second-version")

            first = archive_script_generation(
                root / "Exports" / "roteiro",
                script_id="s-123",
                script_title="A caneta emagrece, mas a pele acompanha?",
                generation_id="v-first",
                final_video=first_video,
            )
            repeated = archive_script_generation(
                root / "Exports" / "roteiro",
                script_id="s-123",
                script_title="A caneta emagrece, mas a pele acompanha?",
                generation_id="v-first",
                final_video=first_video,
            )
            second = archive_script_generation(
                root / "Exports" / "roteiro",
                script_id="s-123",
                script_title="Título atualizado sem trocar a pasta do roteiro",
                generation_id="v-second",
                final_video=second_video,
            )

            self.assertEqual(first.version, "1.1")
            self.assertEqual(repeated.version, "1.1")
            self.assertEqual(first.directory, repeated.directory)
            self.assertEqual(second.version, "1.2")
            self.assertEqual(first.directory.parent, second.directory.parent)
            index = json.loads((first.directory.parent / "VERSOES.json").read_text())
            self.assertEqual(
                index["generations"],
                {"v-first": "1.1", "v-second": "1.2"},
            )

    def test_archive_copies_all_mock_artifacts_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final_video = root / "final.mp4"
            scene_one = root / "scene-one.mp4"
            scene_two = root / "scene-two.mp4"
            thumbnail = root / "thumbnail.jpg"
            final_video.write_bytes(b"final")
            scene_one.write_bytes(b"scene-one")
            scene_two.write_bytes(b"scene-two")
            thumbnail.write_bytes(b"thumbnail")

            result = archive_script_generation(
                root / "Exports" / "roteiro",
                script_id="s-mock",
                script_title="Roteiro com duas câmeras",
                generation_id="vc-mock",
                final_video=final_video,
                source_videos=[
                    ("cena em pé", scene_one),
                    ("cena sentada", scene_two),
                ],
                captions=[
                    (
                        "video-final",
                        "1\n00:00:00,000 --> 00:00:01,000\nTexto de teste",
                    )
                ],
                local_assets=[("thumbnail", thumbnail)],
                script_payload={
                    "id": "s-mock",
                    "titulo": "Roteiro com duas câmeras",
                    "textoFalado": "Texto de teste",
                },
                job_payload={
                    "id": "vc-mock",
                    "productionSettings": {
                        "displayText": "Texto de teste",
                        "spokenText": "Texto de teste",
                    },
                },
                generated_at="2026-08-11T17:30:00+00:00",
            )

            self.assertEqual((result.directory / "video-final.mp4").read_bytes(), b"final")
            self.assertEqual(
                (result.directory / "tomadas" / "01-cena-em-pe.mp4").read_bytes(),
                b"scene-one",
            )
            self.assertEqual(
                (result.directory / "tomadas" / "02-cena-sentada.mp4").read_bytes(),
                b"scene-two",
            )
            self.assertIn(
                "Texto de teste",
                (result.directory / "legendas" / "video-final.srt").read_text(),
            )
            self.assertEqual(
                (result.directory / "arquivos" / "thumbnail.jpg").read_bytes(),
                b"thumbnail",
            )
            self.assertEqual(
                (result.directory / "roteiro" / "fala-final.txt").read_text(),
                "Texto de teste\n",
            )
            manifest = json.loads(
                (result.directory / "metadados-da-geracao.json").read_text()
            )
            self.assertTrue(manifest["sourceFilesPreserved"])
            self.assertEqual(manifest["version"], "1.1")

            # O arquivo de entrega é cópia: os mocks de origem continuam intactos.
            self.assertEqual(final_video.read_bytes(), b"final")
            self.assertEqual(scene_one.read_bytes(), b"scene-one")
            self.assertEqual(scene_two.read_bytes(), b"scene-two")


if __name__ == "__main__":
    unittest.main()
