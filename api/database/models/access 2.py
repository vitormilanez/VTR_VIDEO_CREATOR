from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name="organization_status",
        ),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default=text("'America/Sao_Paulo'")
    )
    locale: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pt-BR'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)


class OrganizationMembership(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_memberships_organization_id_id"),
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_user"),
        CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'reviewer', 'viewer')",
            name="membership_role",
        ),
        CheckConstraint(
            "status IN ('active', 'invited', 'suspended')",
            name="membership_status",
        ),
        Index("ix_memberships_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'viewer'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )


class OrganizationSetting(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "organization_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_org_settings_organization_id_id"),
        UniqueConstraint("organization_id", "key", name="uq_org_settings_organization_key"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'1'"))


class ProviderConnection(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_provider_connections_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "provider",
            "external_account_id",
            name="uq_provider_connections_external_account",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'error', 'revoked')",
            name="provider_connection_status",
        ),
        Index(
            "uq_provider_connections_default",
            "organization_id",
            "provider",
            unique=True,
            postgresql_where=text("external_account_id IS NULL"),
        ),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    secret_ref: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_audit_events_organization_id_id"),
        Index("ix_audit_events_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
