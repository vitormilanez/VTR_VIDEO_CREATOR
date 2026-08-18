from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
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


class MediaAsset(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_media_assets_organization_id_id"),
        UniqueConstraint(
            "organization_id", "storage_bucket", "storage_key", name="uq_media_assets_storage_key"
        ),
        CheckConstraint("byte_size >= 0", name="media_asset_byte_size"),
        CheckConstraint(
            "status IN ('pending', 'uploading', 'ready', 'error', 'archived')",
            name="media_asset_status",
        ),
        Index("ix_media_assets_org_kind_created", "organization_id", "kind", "created_at"),
        Index("ix_media_assets_org_sha256", "organization_id", "sha256"),
    )

    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetVariant(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "asset_variants"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_asset_variants_organization_id_id"),
        UniqueConstraint(
            "organization_id", "media_asset_id", "variant", name="uq_asset_variants_asset_variant"
        ),
        ForeignKeyConstraint(
            ["organization_id", "media_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="CASCADE",
            name="fk_asset_variants_org_asset",
        ),
        CheckConstraint("byte_size >= 0", name="asset_variant_byte_size"),
    )

    media_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ProductionProfile(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "production_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_production_profiles_org_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_production_profiles_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_production_profiles_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_set_id"],
            ["avatar_sets.organization_id", "avatar_sets.id"],
            ondelete="RESTRICT",
            name="fk_production_profiles_org_avatar_set",
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_look_id"],
            ["avatar_looks.organization_id", "avatar_looks.id"],
            ondelete="RESTRICT",
            name="fk_production_profiles_org_avatar_look",
        ),
        ForeignKeyConstraint(
            ["organization_id", "voice_id"],
            ["voices.organization_id", "voices.id"],
            ondelete="RESTRICT",
            name="fk_production_profiles_org_voice",
        ),
        ForeignKeyConstraint(
            ["organization_id", "music_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_production_profiles_org_music",
        ),
        CheckConstraint("position_count > 0", name="production_profile_position_count"),
        CheckConstraint(
            "music_volume >= 0 AND music_volume <= 1",
            name="production_profile_music_volume",
        ),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    avatar_set_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    avatar_look_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    voice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    speech_mode: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'natural'"))
    generation_mode: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'avatar'"))
    avatar_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'single'"))
    position_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    music_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    music_volume: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.12"))
    cinematic_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    voice_mood: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'confident'"))
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ScenePlan(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "scene_plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_scene_plans_organization_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_scene_plans_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_scene_plans_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "script_version_id"],
            ["script_versions.organization_id", "script_versions.id"],
            ondelete="RESTRICT",
            name="fk_scene_plans_org_script_version",
            use_alter=True,
        ),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    script_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'1'"))


class VisualPlan(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "visual_plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_visual_plans_organization_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_visual_plans_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_visual_plans_org_script",
        ),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'1'"))


class VisualPack(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "visual_packs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_visual_packs_organization_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_visual_packs_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_visual_packs_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_avatar_look_id"],
            ["avatar_looks.organization_id", "avatar_looks.id"],
            ondelete="RESTRICT",
            name="fk_visual_packs_org_avatar_look",
        ),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pack: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_avatar_look_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'1'"))


class VideoSlideRender(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "video_slide_renders"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_video_slide_renders_org_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_video_slide_renders_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_video_slide_renders_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "output_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_video_slide_renders_org_output_asset",
        ),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    render: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class StoryProject(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "story_projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_story_projects_organization_id_id"),
        UniqueConstraint("organization_id", "script_id", name="uq_story_projects_script"),
        ForeignKeyConstraint(
            ["organization_id", "script_id"],
            ["scripts.organization_id", "scripts.id"],
            ondelete="CASCADE",
            name="fk_story_projects_org_script",
        ),
        ForeignKeyConstraint(
            ["organization_id", "active_story_version_id"],
            ["story_versions.organization_id", "story_versions.id"],
            ondelete="RESTRICT",
            name="fk_story_projects_org_active_version",
            use_alter=True,
        ),
        Index("ix_story_projects_org_status", "organization_id", "status"),
    )

    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    active_story_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    production_tier: Mapped[str] = mapped_column(String(40), nullable=False)
    story_brief: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class StoryVersion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "story_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_story_versions_organization_id_id"),
        UniqueConstraint(
            "organization_id", "story_project_id", "story_revision", name="uq_story_versions_revision"
        ),
        UniqueConstraint(
            "organization_id", "request_fingerprint", name="uq_story_versions_request_fingerprint"
        ),
        ForeignKeyConstraint(
            ["organization_id", "story_project_id"],
            ["story_projects.organization_id", "story_projects.id"],
            ondelete="CASCADE",
            name="fk_story_versions_org_project",
        ),
        ForeignKeyConstraint(
            ["organization_id", "active_critique_id"],
            ["story_critiques.organization_id", "story_critiques.id"],
            ondelete="RESTRICT",
            name="fk_story_versions_org_active_critique",
            use_alter=True,
        ),
        CheckConstraint("story_revision > 0", name="story_version_positive_revision"),
        Index("ix_story_versions_org_project", "organization_id", "story_project_id"),
    )

    story_project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    story_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    script_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    final_speech_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    script_contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    story_contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_capabilities_version: Mapped[str] = mapped_column(String(80), nullable=False)
    story_bible: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    character_bible: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    visual_bible: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    shot_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    story_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    active_critique_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    story_bible_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    budget_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    budget_approval: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class StoryCritique(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "story_critiques"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_story_critiques_organization_id_id"),
        UniqueConstraint(
            "organization_id", "story_version_id", "critique_revision", name="uq_story_critiques_revision"
        ),
        UniqueConstraint(
            "organization_id", "request_fingerprint", name="uq_story_critiques_request_fingerprint"
        ),
        ForeignKeyConstraint(
            ["organization_id", "story_version_id"],
            ["story_versions.organization_id", "story_versions.id"],
            ondelete="CASCADE",
            name="fk_story_critiques_org_version",
        ),
    )

    story_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    critique_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    critique: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    critique_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class StoryShot(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    __tablename__ = "story_shots"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_story_shots_organization_id_id"),
        UniqueConstraint(
            "organization_id", "story_version_id", "shot_key", name="uq_story_shots_version_key"
        ),
        ForeignKeyConstraint(
            ["organization_id", "story_version_id"],
            ["story_versions.organization_id", "story_versions.id"],
            ondelete="CASCADE",
            name="fk_story_shots_org_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_story_shots_org_asset",
        ),
        ForeignKeyConstraint(
            ["organization_id", "thumbnail_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_story_shots_org_thumbnail",
        ),
        ForeignKeyConstraint(
            ["organization_id", "current_generation_id"],
            ["story_shot_generations.organization_id", "story_shot_generations.id"],
            ondelete="RESTRICT",
            name="fk_story_shots_org_current_generation",
            use_alter=True,
        ),
        CheckConstraint("shot_order >= 0", name="story_shot_order"),
        Index("ix_story_shots_org_version_order", "organization_id", "story_version_id", "shot_order"),
    )

    story_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    shot_key: Mapped[str] = mapped_column(String(120), nullable=False)
    shot_order: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    continuity_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    controls: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    shot_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    remote_job_id: Mapped[str | None] = mapped_column(String(240))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    quality_status: Mapped[str | None] = mapped_column(String(40))
    current_generation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    thumbnail_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class StoryShotGeneration(
    UUIDPrimaryKeyMixin,
    OrganizationOwnedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "story_shot_generations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_story_shot_generations_org_id_id"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_story_shot_generations_idempotency"
        ),
        ForeignKeyConstraint(
            ["organization_id", "story_shot_id"],
            ["story_shots.organization_id", "story_shots.id"],
            ondelete="CASCADE",
            name="fk_story_shot_generations_org_shot",
        ),
        ForeignKeyConstraint(
            ["organization_id", "story_version_id"],
            ["story_versions.organization_id", "story_versions.id"],
            ondelete="CASCADE",
            name="fk_story_shot_generations_org_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "avatar_look_id"],
            ["avatar_looks.organization_id", "avatar_looks.id"],
            ondelete="RESTRICT",
            name="fk_story_shot_generations_org_avatar_look",
        ),
        ForeignKeyConstraint(
            ["organization_id", "output_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            ondelete="RESTRICT",
            name="fk_story_shot_generations_org_output_asset",
        ),
        CheckConstraint("duration_seconds >= 0", name="story_shot_generation_duration"),
        Index("ix_story_shot_generations_org_shot", "organization_id", "story_shot_id"),
    )

    story_shot_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    story_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    shot_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    spoken_text: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_look_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    continuity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(240))
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    output_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    retry_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    error: Mapped[str | None] = mapped_column(Text)
