from __future__ import annotations

from api.services.legacy_import import normalize_snapshot


def test_normalize_snapshot_creates_stable_ids_and_repairs_positional_links() -> None:
    snapshot = {
        "source": "test",
        "updated_at": "2026-08-17T12:00:00Z",
        "sheets": {
            "radar": [
                {
                    "Tema": "Metabolismo",
                    "Sinal de tendência": "Estudo novo",
                    "Link referência": "https://example.test/study",
                    "Data": "17/08/2026",
                }
            ],
            "ideias": [{"ID": "i-1", "Tema": "Explicação", "Trend ID": "t-0"}],
            "roteiros": [{"ID": "s-1", "Título": "Roteiro", "Idea ID": "i-1"}],
            "calendario": [],
            "performance": [],
        },
    }

    first, report = normalize_snapshot(snapshot)
    second, _ = normalize_snapshot(snapshot)

    assert first["trends"][0]["id"] == second["trends"][0]["id"]
    assert first["trends"][0]["id"].startswith("t-")
    assert first["ideas"][0]["trendId"] == first["trends"][0]["id"]
    assert first["scripts"][0]["ideaId"] == "i-1"
    assert report["warnings"] == []


def test_normalize_snapshot_reports_orphan_relations() -> None:
    state, report = normalize_snapshot(
        {
            "sheets": {
                "radar": [],
                "ideias": [{"ID": "i-1", "Trend ID": "t-missing"}],
                "roteiros": [{"ID": "s-1", "Idea ID": "i-missing"}],
                "calendario": [],
                "performance": [],
            }
        }
    )

    assert state["ideas"][0]["trendId"] == "t-missing"
    assert len(report["warnings"]) == 2
