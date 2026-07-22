from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api import server


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


class StableIdTests(unittest.TestCase):
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
            jobs_file.write_text(json.dumps([{"id": "v-1", "scriptId": "s-0"}]), encoding="utf-8")
            original_jobs = server.VIDEO_JOBS
            server.VIDEO_JOBS = jobs_file
            try:
                changed = server._migrate_video_job_script_ids([{"id": "s-permanente"}])
                jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
                self.assertEqual(changed, 1)
                self.assertEqual(jobs[0]["scriptId"], "s-permanente")
            finally:
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


if __name__ == "__main__":
    unittest.main()
