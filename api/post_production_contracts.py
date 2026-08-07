"""Independent contracts for transcript-driven post-production."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class InteractionType(str, Enum):
    none = "none"
    caption_emphasis = "caption_emphasis"
    kinetic_text = "kinetic_text"
    progressive_list = "progressive_list"
    supporting_visual = "supporting_visual"
    cta_card = "cta_card"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TranscriptWord(BaseModel):
    index: int = Field(ge=0)
    startMs: int = Field(ge=0)
    endMs: int = Field(ge=0)
    text: str = Field(min_length=1)


class Transcript(BaseModel):
    schemaVersion: str
    normalizationVersion: str
    version: str
    modelVersion: str
    videoFingerprint: str
    language: str
    durationMs: int = Field(gt=0)
    text: str
    segments: list[dict[str, Any]]
    words: list[TranscriptWord]


class SemanticSegment(BaseModel):
    id: str
    startWordIndex: int = Field(ge=0)
    endWordIndex: int = Field(ge=0)
    spokenText: str
    reason: str
    confidence: float = Field(ge=0, le=1)


class VisualPlanEvent(BaseModel):
    id: str
    startWordIndex: int = Field(ge=0)
    endWordIndex: int = Field(ge=0)
    interactionType: InteractionType
    visualText: str = Field(default="", max_length=100)
    intensity: Literal["low", "medium", "high"] = "medium"
    assetRef: str | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    fallback: InteractionType = InteractionType.caption_emphasis


class VisualPlan(BaseModel):
    schemaVersion: str = "visual-plan-v1"
    modelVersion: str
    transcriptVersion: str
    videoFingerprint: str
    events: list[VisualPlanEvent]


class VisualTimelineEvent(VisualPlanEvent):
    startMs: int = Field(ge=0)
    endMs: int = Field(ge=0)
    spokenText: str
    reviewStatus: ReviewStatus = ReviewStatus.pending
    enabled: bool = True


class VisualTimeline(BaseModel):
    schemaVersion: str = "visual-timeline-v1"
    version: str
    transcriptVersion: str
    videoFingerprint: str
    stale: bool = False
    events: list[VisualTimelineEvent]


class PreflightFinding(BaseModel):
    code: str
    classification: Literal["BLOCKER", "WARNING", "INFO"]
    message: str
    eventId: str | None = None


class PreflightReport(BaseModel):
    ok: bool
    checkedAt: str
    findings: list[PreflightFinding]


class PostProductionJob(BaseModel):
    id: str
    kind: Literal["post_production"] = "post_production"
    videoJobId: str
    status: Literal[
        "queued", "transcribing", "planning", "preflight", "rendering_preview",
        "preview_ready", "failed", "cancelled", "stale", "needs_review",
    ]
    progresso: int = Field(ge=0, le=100)
    criadoEm: str
    atualizadoEm: str
