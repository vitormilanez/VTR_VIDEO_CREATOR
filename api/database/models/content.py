from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
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


class Trend(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "trends"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_trends_organization_id_id"),
        UniqueConstraint("organization_id", "legacy_id", name="uq_trends_organization_legacy"),
        CheckConstraint("viral_potential BETWEEN 0 AND 10", name="trend_viral_potential"),
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="trend_priority"),
        CheckConstraint("status IN ('new', 'analyzing', 'discarded')", name="trend_status"),
        Index("ix_trends_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_trends_org_priority", "organization_id", "priority"),
    )

    legacy_id: Mapped[str | None] = mapped_column(String(120))
    trend_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtheme: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(240))
    reference_url: Mapped[str | None] = mapped_column(Text)
    trend_signal: Mapped[str | None] = mapped_column(Text)
    audience_pain: Mapped[str | None] = mapped_column(Text)
    viral_potential: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'new'"))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Idea(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "ideas"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ideas_organization_id_id"),
        UniqueConstraint("organization_id", "legacy_id", name="uq_ideas_organization_legacy"),
        ForeignKeyConstraint(
            ["organization_id", "trend_id"],
            ["trends.organization_id", "trends.id"],
            ondelete="RESTRICT",
            name="fk_ideas_org_trend",
        ),
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="idea_priority"),
        CheckConstraint(
            "status IN ('new', 'analyzing', 'approved', 'discarded')",
            name="idea_status",
        ),
        Index("ix_ideas_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_ideas_org_trend", "organization_id", "trend_id"),
    )

    legacy_id: Mapped[str | None] = mapped_column(String(120))
    trend_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    family: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'educational'"))
    hook: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    angle: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    content_type: Mapped[str | None] = mapped_column(String(80))
    audience_pain: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    origin_url: Mapped[str | None] = mapped_column(Text)
    compliance_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'new'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Script(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "scripts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_scripts_organization_id_id"),
        UniqueConstraint("organization_id", "legacy_id", name="uq_scripts_organization_legacy"),
        ForeignKeyConstraint(
            ["organization_id", "idea_id"],
            ["ideas.organization_id", "ideas.id"],
            ondelete="RESTRICT",
            name="fk_scripts_org_idea",
        ),
        CheckConstraint(
            "risk IN ('low', 'medium', 'high')",
            name="script_risk",
        ),
        CheckConstraint(
            "status IN ('awaiting_validation', 'in_review', 'clinically_approved', 'rejected')",
            name="script_status",
        ),
        Index("ix_scripts_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_scripts_org_idea", "organization_id", "idea_id"),
    )

    legacy_id: Mapped[str | None] = mapped_column(String(120))
    idea_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    category: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'educational'"))
    theme: Mapped[str] = mapped_column(String(500), nullable=False, server_default=text("''"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    conflict: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    simple_explanation: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    turn: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    cta: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    medical_care: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    risk: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'medium'"))
    suggested_format: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'Reels'"))
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'awaiting_validation'")
    )
    approver_name: Mapped[str | None] = mapped_column(String(240))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_asset_url: Mapped[str | None] = mapped_column(Text)
    editorial_tone: Mapped[str | None] = mapped_column(String(40))
    spoken_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    outro_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    generation_provider: Mapped[str | None] = mapped_column(String(80))
    generation_flow_version: Mapped[str | None] = mapped_column(String(100))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScriptVersion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "script_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_script_versions_org_id_id"),
        UniqueConstraint(
            "organization_id", "script_id", "revision", name="uq_script_versions_revision"
        ),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_script_versions_org_script",
        ),
        CheckConstraint("revision > 0", name="script_version_positive_revision"),
        Index("ix_script_versions_org_script", "organization_id", "script_id", "revision"),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    final_speech: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    final_speech_hash: Mapped[str | None] = mapped_column(String(128))
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'1'"))
    generation_provider: Mapped[str | None] = mapped_column(String(80))
    generation_flow_version: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ScriptReview(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "script_reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_script_reviews_org_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "script_version_id"],
            ["script_versions.organization_id", "script_versions.id"],
            ondelete="CASCADE",
            name="fk_script_reviews_org_version",
        ),
        CheckConstraint(
            "status IN ('open', 'approved', 'reopened', 'rejected')",
            name="script_review_status",
        ),
        Index("ix_script_reviews_org_version", "organization_id", "script_version_id"),
    )

    script_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    review_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'medical'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ScriptEditorState(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    """Compatibilidade transitória com o editor atual durante o cutover."""

    __tablename__ = "script_editor_states"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_script_editor_states_org_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_script_editor_states_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_script_editor_states_org_script",
        ),
        CheckConstraint("duration_seconds > 0", name="script_editor_duration"),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("45"))
    human_review_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    title_choice: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'current'"))
    suggested_title: Mapped[str | None] = mapped_column(Text)
    schema_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    technical_error: Mapped[str | None] = mapped_column(Text)
    previous_script: Mapped[str | None] = mapped_column(Text)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    script_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    final_speech_hash: Mapped[str | None] = mapped_column(String(128))
    approved_script_revision: Mapped[int | None] = mapped_column(Integer)
    approved_final_speech_hash: Mapped[str | None] = mapped_column(String(128))
    approval_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("''"))
