from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
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


class SocialAccount(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_social_accounts_organization_id_id"),
        UniqueConstraint(
            "organization_id", "provider", "external_account_id", name="uq_social_accounts_external"
        ),
        ForeignKeyConstraint(
            ["organization_id", "provider_connection_id"],
            ["provider_connections.organization_id", "provider_connections.id"],
            ondelete="RESTRICT",
            name="fk_social_accounts_org_connection",
        ),
        CheckConstraint(
            "status IN ('active', 'error', 'revoked', 'archived')",
            name="social_account_status",
        ),
    )

    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(240), nullable=False)
    username: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class CalendarPost(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "calendar_posts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_calendar_posts_organization_id_id"),
        UniqueConstraint("organization_id", "legacy_id", name="uq_calendar_posts_org_legacy"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="RESTRICT",
            name="fk_calendar_posts_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            ondelete="RESTRICT",
            name="fk_calendar_posts_org_job",
        ),
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            ondelete="RESTRICT",
            name="fk_calendar_posts_org_social_account",
        ),
        CheckConstraint(
            "status IN ('pending', 'scheduled', 'published', 'failed', 'cancelled')",
            name="calendar_post_status",
        ),
        Index("ix_calendar_posts_org_scheduled", "organization_id", "scheduled_at"),
        Index("ix_calendar_posts_org_status", "organization_id", "status", "scheduled_at"),
    )

    legacy_id: Mapped[str | None] = mapped_column(String(120))
    script_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    theme: Mapped[str | None] = mapped_column(String(500))
    content_format: Mapped[str | None] = mapped_column(String(80))
    responsible: Mapped[str | None] = mapped_column(String(240))
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class PerformanceMetric(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "performance_metrics"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_performance_metrics_org_id_id"),
        UniqueConstraint(
            "organization_id", "calendar_post_id", "observed_at", name="uq_performance_metrics_observation"
        ),
        ForeignKeyConstraint(
            ["organization_id", "calendar_post_id"],
            ["calendar_posts.organization_id", "calendar_posts.id"],
            ondelete="CASCADE",
            name="fk_performance_metrics_org_post",
        ),
        CheckConstraint(
            "views >= 0 AND likes >= 0 AND comments >= 0 AND shares >= 0 "
            "AND saves >= 0 AND new_followers >= 0 AND clicks >= 0 AND leads >= 0",
            name="performance_metrics_nonnegative",
        ),
        Index("ix_performance_metrics_org_observed", "organization_id", "observed_at"),
        Index("ix_performance_metrics_org_post", "organization_id", "calendar_post_id"),
    )

    calendar_post_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    likes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    retention_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 3), nullable=False, server_default=text("0")
    )
    comments: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    shares: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    saves: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    new_followers: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    leads: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    score_note: Mapped[str | None] = mapped_column(Text)
    learning: Mapped[str | None] = mapped_column(Text)
    source_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
