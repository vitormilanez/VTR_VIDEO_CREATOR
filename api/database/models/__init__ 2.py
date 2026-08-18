"""Registro central dos modelos usados pelo metadata Alembic."""

from api.database.base import Base
from api.database.models.access import (
    AuditEvent,
    Organization,
    OrganizationMembership,
    OrganizationSetting,
    ProviderConnection,
    UserProfile,
)
from api.database.models.content import (
    Idea,
    Script,
    ScriptEditorState,
    ScriptReview,
    ScriptVersion,
    Trend,
)
from api.database.models.identity import (
    AvatarIdentity,
    AvatarLook,
    AvatarSet,
    AvatarSetLook,
    Voice,
)
from api.database.models.migration import LegacyIdMap, LegacyImportRun
from api.database.models.operations import (
    AIResponseCache,
    AIUsage,
    Job,
    JobEvent,
    ProviderCapability,
)
from api.database.models.production import (
    AssetVariant,
    MediaAsset,
    ProductionProfile,
    ScenePlan,
    StoryCritique,
    StoryProject,
    StoryShot,
    StoryShotGeneration,
    StoryVersion,
    VideoSlideRender,
    VisualPack,
    VisualPlan,
)
from api.database.models.publishing import CalendarPost, PerformanceMetric, SocialAccount

__all__ = [
    "AIResponseCache",
    "AIUsage",
    "AssetVariant",
    "AuditEvent",
    "AvatarIdentity",
    "AvatarLook",
    "AvatarSet",
    "AvatarSetLook",
    "Base",
    "CalendarPost",
    "Idea",
    "Job",
    "JobEvent",
    "LegacyIdMap",
    "LegacyImportRun",
    "MediaAsset",
    "Organization",
    "OrganizationMembership",
    "OrganizationSetting",
    "PerformanceMetric",
    "ProductionProfile",
    "ProviderCapability",
    "ProviderConnection",
    "ScenePlan",
    "Script",
    "ScriptEditorState",
    "ScriptReview",
    "ScriptVersion",
    "SocialAccount",
    "StoryCritique",
    "StoryProject",
    "StoryShot",
    "StoryShotGeneration",
    "StoryVersion",
    "Trend",
    "UserProfile",
    "VideoSlideRender",
    "VisualPack",
    "VisualPlan",
    "Voice",
]
