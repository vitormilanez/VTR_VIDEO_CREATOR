from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class AvatarIdentity(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "avatar_identities"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_avatar_identities_org_id_id"),
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_group_id",
            name="uq_avatar_identities_provider_group",
        ),
        CheckConstraint(
            "status IN ('draft', 'processing', 'ready', 'error', 'archived')",
            name="avatar_identity_status",
        ),
        Index("ix_avatar_identities_org_status", "organization_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'heygen'"))
    provider_group_id: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class Voice(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "voices"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_voices_organization_id_id"),
        UniqueConstraint(
            "organization_id", "provider", "provider_voice_id", name="uq_voices_provider_voice"
        ),
        CheckConstraint(
            "status IN ('active', 'processing', 'error', 'archived')",
            name="voice_status",
        ),
        Index("ix_voices_org_status", "organization_id", "status"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'heygen'"))
    provider_voice_id: Mapped[str] = mapped_column(String(240), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    language: Mapped[str | None] = mapped_column(String(40))
    gender: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AvatarLook(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "avatar_looks"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_avatar_looks_organization_id_id"),
        UniqueConstraint(
            "organization_id", "provider", "provider_avatar_id", name="uq_avatar_looks_provider_avatar"
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_identity_id"],
            ["avatar_identities.organization_id", "avatar_identities.id"],
            ondelete="CASCADE",
            name="fk_avatar_looks_org_identity",
        ),
        ForeignKeyConstraint(
            ["organization_id", "preview_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_avatar_looks_org_preview_asset",
        ),
        CheckConstraint(
            "status IN ('draft', 'processing', 'ready', 'error', 'archived')",
            name="avatar_look_status",
        ),
        Index("ix_avatar_looks_org_identity", "organization_id", "avatar_identity_id"),
    )

    avatar_identity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'heygen'"))
    provider_avatar_id: Mapped[str] = mapped_column(String(240), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    role_hint: Mapped[str | None] = mapped_column(String(80))
    preview_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ready'"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AvatarSet(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "avatar_sets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_avatar_sets_organization_id_id"),
        UniqueConstraint("organization_id", "name", name="uq_avatar_sets_organization_name"),
        ForeignKeyConstraint(
            ["organization_id", "voice_id"],
            ["voices.organization_id", "voices.id"],
            ondelete="RESTRICT",
            name="fk_avatar_sets_org_voice",
        ),
        ForeignKeyConstraint(
            ["organization_id", "primary_look_id"],
            ["avatar_looks.organization_id", "avatar_looks.id"],
            ondelete="RESTRICT",
            name="fk_avatar_sets_org_primary_look",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="avatar_set_status"),
    )

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    voice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    primary_look_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class AvatarSetLook(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "avatar_set_looks"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_avatar_set_looks_org_id_id"),
        UniqueConstraint(
            "organization_id", "avatar_set_id", "avatar_look_id", name="uq_avatar_set_looks_pair"
        ),
        UniqueConstraint(
            "organization_id", "avatar_set_id", "role", name="uq_avatar_set_looks_role"
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_set_id"],
            ["avatar_sets.organization_id", "avatar_sets.id"],
            ondelete="CASCADE",
            name="fk_avatar_set_looks_org_set",
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_look_id"],
            ["avatar_looks.organization_id", "avatar_looks.id"],
            ondelete="RESTRICT",
            name="fk_avatar_set_looks_org_look",
        ),
        CheckConstraint("position >= 0", name="avatar_set_look_position"),
        Index("ix_avatar_set_looks_org_set", "organization_id", "avatar_set_id", "position"),
    )

    avatar_set_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    avatar_look_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str | None] = mapped_column(String(160))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
