from __future__ import annotations

import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, create_engine, text
from sqlalchemy.exc import DBAPIError

from api.database.config import DatabaseSettings, normalize_database_url
from api.database.models import Base
from api.database.tenant import OrganizationRole, TenantContext


ROOT = Path(__file__).resolve().parent.parent
CORE_TABLES = {
    "organizations",
    "user_profiles",
    "organization_memberships",
    "organization_settings",
    "provider_connections",
    "trends",
    "ideas",
    "scripts",
    "script_versions",
    "script_reviews",
    "avatar_identities",
    "avatar_looks",
    "voices",
    "avatar_sets",
    "avatar_set_looks",
    "production_profiles",
    "media_assets",
    "jobs",
    "job_events",
    "calendar_posts",
    "performance_metrics",
    "legacy_import_runs",
    "legacy_id_map",
}


def test_database_url_normalization_uses_psycopg3() -> None:
    assert normalize_database_url("postgres://user:pass@db.example/app?sslmode=require") == (
        "postgresql+psycopg://user:pass@db.example/app?sslmode=require"
    )
    assert normalize_database_url("postgresql+psycopg://user@localhost/app") == (
        "postgresql+psycopg://user@localhost/app"
    )
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_database_url("sqlite:///tmp/app.db")


def test_database_settings_are_opt_in() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert DatabaseSettings.from_env(required=False) is None
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            DatabaseSettings.from_env(required=True)


def test_tenant_context_enforces_roles() -> None:
    tenant = TenantContext(uuid.uuid4(), uuid.uuid4(), OrganizationRole.EDITOR)
    tenant.require_write()
    tenant.require_any(OrganizationRole.OWNER, OrganizationRole.EDITOR)

    reviewer = TenantContext(uuid.uuid4(), uuid.uuid4(), OrganizationRole.REVIEWER)
    with pytest.raises(PermissionError, match="reviewer"):
        reviewer.require_write()


def test_metadata_contains_the_multitenant_domain() -> None:
    assert CORE_TABLES <= set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 39


def test_every_tenant_table_has_ownership_and_tenant_unique_id() -> None:
    tenant_tables = [
        table for table in Base.metadata.sorted_tables if "organization_id" in table.columns
    ]
    assert len(tenant_tables) == 37

    for table in tenant_tables:
        organization_column = table.c.organization_id
        assert organization_column.nullable is False, table.name
        assert any(foreign_key.target_fullname == "organizations.id" for foreign_key in organization_column.foreign_keys), table.name
        assert any(
            isinstance(constraint, UniqueConstraint)
            and [column.name for column in constraint.columns] == ["organization_id", "id"]
            for constraint in table.constraints
        ), table.name


def test_cross_tenant_foreign_keys_include_organization_id() -> None:
    for table in Base.metadata.sorted_tables:
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            referred_table = constraint.referred_table
            if referred_table.name == "organizations" or "organization_id" not in referred_table.c:
                continue
            local_columns = {column.name for column in constraint.columns}
            remote_columns = {element.column.name for element in constraint.elements}
            assert "organization_id" in local_columns, constraint.name
            assert "organization_id" in remote_columns, constraint.name


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def ephemeral_postgres(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    createdb = shutil.which("createdb")
    if not initdb or not pg_ctl or not createdb or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("PostgreSQL local não disponível para o teste de migration.")

    data_dir = tmp_path_factory.mktemp("postgres-data")
    port = _available_port()
    subprocess.run(
        [initdb, "-D", str(data_dir), "-A", "trust", "-U", "postgres"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            pg_ctl,
            "-D",
            str(data_dir),
            "-l",
            str(data_dir / "postgres.log"),
            "-o",
            f"-p {port} -k /tmp",
            "-w",
            "start",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        subprocess.run(
            [
                createdb,
                "-h",
                "/tmp",
                "-p",
                str(port),
                "-U",
                "postgres",
                "ai_video_creator_test",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        yield (
            "postgresql+psycopg://postgres@/ai_video_creator_test"
            f"?host=/tmp&port={port}"
        )
    finally:
        subprocess.run(
            [pg_ctl, "-D", str(data_dir), "-m", "fast", "-w", "stop"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def test_baseline_migration_matches_metadata_and_enforces_rls(
    ephemeral_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", ephemeral_postgres)
    config = _alembic_config()
    command.upgrade(config, "head")
    engine = create_engine(ephemeral_postgres, poolclass=sa.pool.NullPool)
    organization_a = "00000000-0000-0000-0000-000000000001"
    organization_b = "00000000-0000-0000-0000-000000000002"
    user_a = "10000000-0000-0000-0000-000000000001"
    user_b = "10000000-0000-0000-0000-000000000002"
    trend_a = "20000000-0000-0000-0000-000000000001"
    trend_b = "20000000-0000-0000-0000-000000000002"

    try:
        with engine.begin() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": True},
            )
            assert compare_metadata(migration_context, Base.metadata) == []
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class "
                    "WHERE relnamespace = 'public'::regnamespace AND relrowsecurity"
                )
            ) == 39
            assert connection.scalar(
                text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
            ) == 151

            connection.exec_driver_sql("CREATE ROLE app_runtime NOLOGIN")
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public, app TO app_runtime")
            connection.exec_driver_sql(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_runtime"
            )
            connection.exec_driver_sql("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_runtime")
            connection.execute(
                text(
                    "INSERT INTO organizations(id, slug, name) VALUES "
                    "(:organization_a, 'tenant-a', 'Tenant A'), "
                    "(:organization_b, 'tenant-b', 'Tenant B')"
                ),
                {"organization_a": organization_a, "organization_b": organization_b},
            )
            connection.execute(
                text(
                    "INSERT INTO user_profiles(id, email) VALUES "
                    "(:user_a, 'a@example.test'), (:user_b, 'b@example.test')"
                ),
                {"user_a": user_a, "user_b": user_b},
            )
            connection.execute(
                text(
                    "INSERT INTO organization_memberships(organization_id, user_id, role) VALUES "
                    "(:organization_a, :user_a, 'editor'), "
                    "(:organization_b, :user_b, 'editor')"
                ),
                {
                    "organization_a": organization_a,
                    "organization_b": organization_b,
                    "user_a": user_a,
                    "user_b": user_b,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO trends(id, organization_id, title) VALUES "
                    "(:trend_a, :organization_a, 'Trend A'), "
                    "(:trend_b, :organization_b, 'Trend B')"
                ),
                {
                    "organization_a": organization_a,
                    "organization_b": organization_b,
                    "trend_a": trend_a,
                    "trend_b": trend_b,
                },
            )

        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO ideas(organization_id, trend_id, title) "
                        "VALUES (:organization_a, :trend_b, 'Cross-tenant')"
                    ),
                    {"organization_a": organization_a, "trend_b": trend_b},
                )

        with engine.begin() as connection:
            connection.exec_driver_sql("SET ROLE app_runtime")
            connection.execute(
                text("SELECT set_config('app.user_id', :user_id, false)"),
                {"user_id": user_a},
            )
            connection.execute(
                text("SELECT set_config('app.organization_id', :organization_id, false)"),
                {"organization_id": organization_a},
            )
            assert connection.scalar(text("SELECT count(*) FROM organizations")) == 1
            assert connection.scalar(text("SELECT count(*) FROM trends")) == 1
            connection.execute(
                text("INSERT INTO trends(organization_id, title) VALUES (:organization_id, 'Allowed')"),
                {"organization_id": organization_a},
            )

        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.exec_driver_sql("SET ROLE app_runtime")
                connection.execute(
                    text("SELECT set_config('app.user_id', :user_id, false)"),
                    {"user_id": user_a},
                )
                connection.execute(
                    text("SELECT set_config('app.organization_id', :organization_id, false)"),
                    {"organization_id": organization_a},
                )
                connection.execute(
                    text("INSERT INTO trends(organization_id, title) VALUES (:organization_id, 'Denied')"),
                    {"organization_id": organization_b},
                )
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    verification_engine = create_engine(ephemeral_postgres, poolclass=sa.pool.NullPool)
    try:
        with verification_engine.connect() as connection:
            remaining = connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "AND table_name <> 'alembic_version'"
                )
            )
            assert remaining == 0
    finally:
        verification_engine.dispose()
