from __future__ import annotations

import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

from api.database.config import DatabaseSettings
from api.database.models import Organization
from api.database.session import create_database
from api.repositories.content import ContentConflictError, PostgresContentRepository
from tests.test_database_foundation import ephemeral_postgres


ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("version_locations", str(ROOT / "migrations" / "revisions"))
    return config


def test_repository_import_is_idempotent_and_crud_uses_public_ids(
    ephemeral_postgres: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", ephemeral_postgres)
    config = _alembic_config()
    command.upgrade(config, "head")
    database = create_database(DatabaseSettings(url=ephemeral_postgres))
    organization_id = uuid.uuid4()
    with database.transaction() as session:
        session.add(Organization(id=organization_id, slug="repository-test", name="Repository Test"))
    repository = PostgresContentRepository(database, organization_id)
    legacy = {
        "trends": [
            {
                "id": "t-1",
                "sourceKey": "trend:1",
                "titulo": "Tendência",
                "fonte": "Teste",
                "status": "novo",
                "prioridade": "alta",
                "criadoEm": "2026-08-17T12:00:00Z",
            }
        ],
        "ideas": [
            {
                "id": "i-1",
                "sourceKey": "idea:1",
                "trendId": "t-1",
                "titulo": "Ideia",
                "status": "novo",
                "prioridade": "media",
                "criadoEm": "2026-08-17T12:00:00Z",
            }
        ],
        "scripts": [
            {
                "id": "s-1",
                "sourceKey": "script:1",
                "ideaId": "i-1",
                "titulo": "Roteiro",
                "status": "em_revisao",
                "criadoEm": "2026-08-17T12:00:00Z",
            }
        ],
        "calendarPosts": [],
        "performance": [],
    }

    first = repository.import_legacy_state(legacy)
    second = repository.import_legacy_state(legacy)
    state = repository.state()

    assert first["counts"]["scripts"]["created"] == 1
    assert second["counts"]["scripts"]["created"] == 0
    assert [item["id"] for item in state["trends"]] == ["t-1"]
    assert state["ideas"][0]["trendId"] == "t-1"
    assert state["scripts"][0]["ideaId"] == "i-1"

    updated = repository.update_script("s-1", {**state["scripts"][0], "titulo": "Revisado"})
    assert updated["titulo"] == "Revisado"
    repository.set_status("roteiros", "s-1", "aprovado_clinicamente")
    assert repository.get_script("s-1")["status"] == "aprovado_clinicamente"

    post = repository.create_calendar_post(
        {
            "id": "p-1",
            "scriptId": "s-1",
            "videoJobId": "v-local-1",
            "titulo": "Post",
            "dataAgendada": "2026-08-20T12:00:00Z",
            "canal": "instagram",
            "status": "agendado",
        }
    )
    assert post["scriptId"] == "s-1"
    assert post["videoJobId"] == "v-local-1"

    try:
        repository.delete_script("s-1")
    except ContentConflictError:
        pass
    else:
        raise AssertionError("Roteiro agendado deveria ser protegido contra exclusão.")

    database.dispose()
    command.downgrade(config, "base")
