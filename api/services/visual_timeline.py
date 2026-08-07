"""Deterministic plan materialization and preflight for visual timelines."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.post_production_contracts import (
    InteractionType,
    PreflightFinding,
    PreflightReport,
    Transcript,
    VisualPlan,
    VisualTimeline,
    VisualTimelineEvent,
)
from api.services.transcript_service import video_fingerprint


TIMELINE_SCHEMA_VERSION = "visual-timeline-v1"
MAX_VISUAL_TEXT = 80
MIN_EVENT_MS = 350
MAX_EVENT_MS = 5500
MAX_OVERLAP_MS = 250


def _dump(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


def _version(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def materialize_timeline(transcript_payload: dict[str, Any], plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Convert word indices to time. Planner-provided timestamps are never accepted."""
    transcript = Transcript.model_validate(transcript_payload)
    plan = VisualPlan.model_validate(plan_payload)
    words = transcript.words
    events: list[VisualTimelineEvent] = []
    for planned in plan.events:
        if planned.startWordIndex > planned.endWordIndex:
            raise ValueError(f"Evento {planned.id}: intervalo de palavras invertido.")
        if planned.endWordIndex >= len(words):
            raise ValueError(f"Evento {planned.id}: índice de palavra fora da transcrição.")
        selected = words[planned.startWordIndex : planned.endWordIndex + 1]
        events.append(
            VisualTimelineEvent(
                **_dump(planned),
                startMs=selected[0].startMs,
                endMs=selected[-1].endMs,
                spokenText=" ".join(word.text for word in selected),
            )
        )
    event_payload = [_dump(event) for event in events]
    return _dump(
        VisualTimeline(
            version=_version(
                {
                    "schema": TIMELINE_SCHEMA_VERSION,
                    "transcript": transcript.version,
                    "video": transcript.videoFingerprint,
                    "events": event_payload,
                }
            ),
            transcriptVersion=transcript.version,
            videoFingerprint=transcript.videoFingerprint,
            events=events,
        )
    )


def timeline_is_stale(timeline: dict[str, Any], transcript: dict[str, Any]) -> bool:
    return bool(
        timeline.get("transcriptVersion") != transcript.get("version", transcript.get("schemaVersion"))
        or timeline.get("videoFingerprint") != transcript.get("videoFingerprint")
    )


def preflight_timeline(
    *,
    source_path: Path | None,
    transcript_payload: dict[str, Any],
    timeline_payload: dict[str, Any],
    require_render_tools: bool = True,
) -> dict[str, Any]:
    findings: list[PreflightFinding] = []

    def add(code: str, classification: str, message: str, event_id: str | None = None) -> None:
        findings.append(
            PreflightFinding(
                code=code,
                classification=classification,
                message=message,
                eventId=event_id,
            )
        )

    try:
        transcript = Transcript.model_validate(transcript_payload)
    except Exception as exc:
        add("transcript.invalid", "BLOCKER", f"Contrato da transcrição inválido: {exc}")
        transcript = None
    try:
        timeline = VisualTimeline.model_validate(timeline_payload)
    except Exception as exc:
        add("timeline.invalid", "BLOCKER", f"Contrato da timeline inválido: {exc}")
        timeline = None

    if source_path is None or not source_path.is_file():
        add("video.missing", "BLOCKER", "O arquivo de vídeo original não está disponível.")
    elif source_path.stat().st_size == 0:
        add("video.empty", "BLOCKER", "O arquivo de vídeo original está vazio.")
    elif transcript:
        if video_fingerprint(source_path) != transcript.videoFingerprint:
            add("video.stale", "BLOCKER", "O arquivo de vídeo mudou após a transcrição.")
        if require_render_tools and shutil.which("ffprobe"):
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                    "-show_entries", "format=duration", "-of", "json", str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if probe.returncode != 0:
                add("video.probe", "BLOCKER", "FFprobe não conseguiu ler o vídeo original.")
            else:
                try:
                    metadata = json.loads(probe.stdout)
                    stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
                    if "video" not in stream_types:
                        add("video.stream", "BLOCKER", "A origem não contém stream de vídeo.")
                    if "audio" not in stream_types:
                        add("audio.stream", "BLOCKER", "A origem não contém áudio para preservar.")
                    media_duration = float(metadata.get("format", {}).get("duration") or 0) * 1000
                    if media_duration <= 0:
                        add("video.duration", "BLOCKER", "A duração real do vídeo é inválida.")
                    elif abs(media_duration - transcript.durationMs) > max(1500, media_duration * 0.05):
                        add("transcript.duration_mismatch", "WARNING", "Duração da transcrição difere do vídeo.")
                except (TypeError, ValueError, json.JSONDecodeError):
                    add("video.metadata", "BLOCKER", "Metadados de duração/streams inválidos.")

    if require_render_tools:
        for binary in ("ffmpeg", "ffprobe"):
            if not shutil.which(binary):
                add(f"tool.{binary}", "BLOCKER", f"{binary} não está instalado.")
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            add("tool.playwright", "BLOCKER", "Playwright não está instalado.")

    if transcript and not transcript.words:
        add("transcript.words", "BLOCKER", "A transcrição não tem palavras indexadas.")
    if transcript and transcript.durationMs <= 0:
        add("transcript.duration", "BLOCKER", "A duração da transcrição é inválida.")

    if transcript and timeline:
        stale = timeline.stale or timeline_is_stale(_dump(timeline), _dump(transcript))
        if stale:
            add("timeline.stale", "BLOCKER", "A timeline não corresponde ao vídeo/transcrição atual.")
        enabled = sorted((event for event in timeline.events if event.enabled), key=lambda item: item.startMs)
        previous: VisualTimelineEvent | None = None
        for event in enabled:
            event_id = event.id
            if event.startWordIndex > event.endWordIndex or event.endWordIndex >= len(transcript.words):
                add("event.word_range", "BLOCKER", "Intervalo de palavras inválido.", event_id)
                continue
            expected_start = transcript.words[event.startWordIndex].startMs
            expected_end = transcript.words[event.endWordIndex].endMs
            if event.startMs != expected_start or event.endMs != expected_end:
                add("event.time_derivation", "BLOCKER", "Tempos não correspondem aos índices de palavras.", event_id)
            if event.endMs <= event.startMs or event.endMs - event.startMs < MIN_EVENT_MS:
                add("event.duration", "BLOCKER", "Duração visual insuficiente ou invertida.", event_id)
            elif event.endMs - event.startMs > MAX_EVENT_MS:
                add("event.long_duration", "WARNING", "Evento permanece mais de 5,5 segundos na tela.", event_id)
            if event.endMs > transcript.durationMs + 250:
                add("event.out_of_bounds", "BLOCKER", "Evento ultrapassa a duração da transcrição.", event_id)
            if len(event.visualText) > MAX_VISUAL_TEXT:
                add("event.text_length", "WARNING", f"Texto visual excede {MAX_VISUAL_TEXT} caracteres.", event_id)
            if event.interactionType == InteractionType.supporting_visual and not event.assetRef:
                add("event.asset", "WARNING", "Apoio visual sem asset usará o fallback.", event_id)
            if event.interactionType == InteractionType.cta_card and not event.visualText.strip():
                add("event.cta", "WARNING", "CTA sem texto visual.", event_id)
            if previous and event.startMs < previous.endMs:
                overlap = previous.endMs - event.startMs
                classification = "BLOCKER" if overlap > MAX_OVERLAP_MS else "WARNING"
                add("event.overlap", classification, f"Sobreposição de {overlap} ms.", event_id)
            previous = event
        duration_minutes = max(transcript.durationMs / 60000, 0.1)
        if len(enabled) / duration_minutes > 10:
            add("timeline.density", "WARNING", "Densidade visual acima de 10 eventos por minuto.")
        if not any(event.interactionType == InteractionType.cta_card for event in enabled):
            add("timeline.cta", "INFO", "Nenhum CTA visual foi planejado.")
        add("safe_area.caption", "INFO", "Legendas reservadas acima da área de controles (250 px).")
        add("medical.safety", "INFO", "Textos visuais derivam somente da fala; revise conteúdo médico antes de publicar.")

    ok = not any(finding.classification == "BLOCKER" for finding in findings)
    return _dump(
        PreflightReport(
            ok=ok,
            checkedAt=datetime.now(timezone.utc).isoformat(),
            findings=findings,
        )
    )
