from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import (
    Base,
    OrganizationOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Job(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_jobs_organization_id_id"),
        UniqueConstraint(
            "organization_id", "kind", "idempotency_key", name="uq_jobs_org_kind_idempotency"
        ),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="RESTRICT",
            name="fk_jobs_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "script_version_id"],
            ["script_versions.organization_id", "script_versions.id"],
            ondelete="RESTRICT",
            name="fk_jobs_org_script_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "provider_connection_id"],
            ["provider_connections.organization_id", "provider_connections.id"],
            ondelete="RESTRICT",
            name="fk_jobs_org_provider_connection",
        ),
        CheckConstraint("attempt_count >= 0", name="job_attempt_count"),
        CheckConstraint("max_attempts > 0", name="job_max_attempts"),
        Index("ix_jobs_org_kind_created", "organization_id", "kind", "created_at"),
        Index("ix_jobs_org_status_available", "organization_id", "status", "available_at"),
        Index("ix_jobs_org_script", "organization_id", "script_id", "created_at"),
        Index(
            "uq_jobs_org_remote_session",
            "organization_id",
            "remote_session_id",
            unique=True,
            postgresql_where=text("remote_session_id IS NOT NULL"),
        ),
    )

    legacy_id: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    script_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    script_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    provider: Mapped[str | None] = mapped_column(String(80))
    external_job_id: Mapped[str | None] = mapped_column(String(240))
    remote_session_id: Mapped[str | None] = mapped_column(String(240))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    claimed_by: Mapped[str | None] = mapped_column(String(160))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))


class JobEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "job_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_job_events_organization_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            ondelete="CASCADE",
            name="fk_job_events_org_job",
        ),
        Index("ix_job_events_org_job_created", "organization_id", "job_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(60))
    next_status: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AIUsage(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ai_usage_organization_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            ondelete="RESTRICT",
            name="fk_ai_usage_org_job",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cache_read_tokens >= 0 "
            "AND cache_write_tokens >= 0",
            name="ai_usage_nonnegative_tokens",
        ),
        CheckConstraint("estimated_cost_usd >= 0", name="ai_usage_nonnegative_cost"),
        Index("ix_ai_usage_org_created", "organization_id", "created_at"),
        Index("ix_ai_usage_org_operation", "organization_id", "operation", "created_at"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 8), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AIResponseCache(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_response_cache"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ai_response_cache_org_id_id"),
        UniqueConstraint(
            "organization_id", "cache_key", name="uq_ai_response_cache_org_cache_key"
        ),
        Index("ix_ai_response_cache_org_operation", "organization_id", "operation"),
        Index("ix_ai_response_cache_expires", "expires_at"),
    )

    cache_key: Mapped[str] = mapped_column(String(180), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderCapability(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "provider_capabilities"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_provider_capabilities_org_id_id"),
        UniqueConstraint(
            "organization_id", "provider", name="uq_provider_capabilities_org_provider"
        ),
    )

    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    cli_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("''"))
    capabilities_version: Mapped[str] = mapped_column(String(80), nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
