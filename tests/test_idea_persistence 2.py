from api import server


def test_iso_preserves_full_iso_timestamp() -> None:
    assert server._iso("2026-08-07T20:03:29.473Z") == "2026-08-07T20:03:29.473000+00:00"
    assert server._iso("2026-08-11T15:20:45.201850+00:00") == "2026-08-11T15:20:45.201850+00:00"


def test_iso_archives_missing_legacy_dates() -> None:
    assert server._iso(None) == "1970-01-01T00:00:00+00:00"


def test_idea_dedupe_key_normalizes_repeated_imports() -> None:
    first = server._idea_dedupe_key(
        "A caneta emagrece, mas a pele acompanha?",
        "Quando o peso cai rápido",
        "PubMed: https://pubmed.ncbi.nlm.nih.gov/41850421/",
    )
    repeated = server._idea_dedupe_key(
        "  A CANETA EMAGRECE, MAS A PELE ACOMPANHA? ",
        "quando o peso cai rapido",
        "pubmed: https://pubmed.ncbi.nlm.nih.gov/41850421/",
    )

    assert first == repeated
