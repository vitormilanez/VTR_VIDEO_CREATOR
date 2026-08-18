from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base, OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class LegacyImportRun(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "legacy_import_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_legacy_import_runs_org_id_id"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'rolled_back')",
            name="legacy_import_run_status",
        ),
        Index("ix_legacy_import_runs_org_started", "organization_id", "started_at"),
    )

    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'running'"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)


class LegacyIdMap(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "legacy_id_map"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_legacy_id_map_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "source_system",
            "entity_type",
            "source_key",
            name="uq_legacy_id_map_source_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "import_run_id"],
            ["legacy_import_runs.organization_id", "legacy_import_runs.id"],
            ondelete="CASCADE",
            name="fk_legacy_id_map_org_run",
        ),
        Index("ix_legacy_id_map_org_target", "organization_id", "target_table", "target_id"),
    )

    import_run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
