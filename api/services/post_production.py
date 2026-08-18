"""Lifecycle for transcript-driven automatic post-production jobs."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from api.job_store import JobStore
from api.services.local_video_kit import render_medical_end_card
from api.services.medical_identity import MEDICAL_MINIMUM_END_CARD_SECONDS
from api.services.post_production_overlays import render_overlay
from api.services.transcript_service import (
    TRANSCRIPT_SCHEMA_VERSION,
    TRANSCRIPT_NORMALIZATION_VERSION,
    normalize_ptbr_medical_text,
    transcribe_video_to_file,
    video_fingerprint,
)
from api.services.video_composer import CompositionScene, TimedOverlay, compose_video
from api.services.visual_planner import generated_asset_ref, plan_visuals
from api.services.visual_timeline import materialize_timeline, preflight_timeline, timeline_is_stale


DESIGN_VERSION = "post-production-design-v3-medical-end-card"
RENDER_CONFIG_VERSION = "vertical-1080x1920-v3-medical-end-card"
MAX_CAPTION_WORDS = 10
MAX_CAPTION_CHARS = 64
MAX_CAPTION_MS = 2800
MIN_MANUAL_VISUAL_MS = 1500
MAX_MANUAL_VISUAL_MS = 5500
_CAPTION_DANGLING_ENDS = {
    "a", "as", "com", "da", "de", "do", "e", "em", "não", "no", "o", "os",
    "para", "por", "que", "se", "sem", "seu", "sua", "todo", "toda", "um", "uma",
}


class PostProductionCancelled(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def idempotency_key(source_path: Path) -> str:
    payload = ":".join(
        (
            video_fingerprint(source_path),
            TRANSCRIPT_SCHEMA_VERSION,
            "visual-timeline-v1",
            RENDER_CONFIG_VERSION,
            DESIGN_VERSION,
        )
    )
    return f"post-production:{hashlib.sha256(payload.encode()).hexdigest()}"


def job_directory(output_root: Path, job_id: str) -> Path:
    return output_root / job_id


def artifact_path(output_root: Path, job_id: str, name: str) -> Path:
    return job_directory(output_root, job_id) / name


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _update(store: JobStore, job_id: str, **patch: Any) -> dict[str, Any]:
    job = store.get("post_production", job_id)
    if not job:
        raise RuntimeError("Job de pós-produção não encontrado.")
    if job.get("status") == "cancelled":
        raise PostProductionCancelled("Job cancelado.")
    job.update(patch, atualizadoEm=now_iso())
    store.upsert("post_production", job)
    return job


def analyze_post_production(
    *,
    store: JobStore,
    job_id: str,
    output_root: Path,
    project_root: Path | None = None,
    cache_get: Callable[[str, Any], dict[str, Any] | None] | None = None,
    cache_put: Callable[[str, Any, dict[str, Any]], None] | None = None,
    record_usage: Callable[[str, str, Any], None] | None = None,
) -> None:
    directory = job_directory(output_root, job_id)
    resolved_project_root = project_root or output_root.parent.parent
    source = directory / "source.mp4"
    transcript_path = directory / "transcript.json"
    timeline_path = directory / "timeline.json"
    try:
        _update(
            store,
            job_id,
            status="transcribing",
            progresso=12,
            etapa="Transcrevendo áudio e sincronizando legendas",
        )
        if transcript_path.is_file():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if (
                transcript.get("videoFingerprint") != video_fingerprint(source)
                or transcript.get("normalizationVersion") != TRANSCRIPT_NORMALIZATION_VERSION
            ):
                transcript = transcribe_video_to_file(
                    source,
                    transcript_path,
                    project_root=resolved_project_root,
                )
        else:
            transcript = transcribe_video_to_file(
                source,
                transcript_path,
                project_root=resolved_project_root,
            )

        captions_path = directory / "captions.srt"
        caption_count = _write_captions(transcript, captions_path)
        _update(
            store,
            job_id,
            status="planning",
            progresso=48,
            etapa="Claude analisando a transcrição temporizada",
            captionsStatus="ready",
            captionsPath=str(captions_path),
            captionCueCount=caption_count,
            transcriptPath=str(transcript_path),
        )
        plan, planner_mode = plan_visuals(
            transcript,
            require_claude=bool((store.get("post_production", job_id) or {}).get("requireClaude")),
            cache_get=cache_get,
            cache_put=cache_put,
            record_usage=record_usage,
        )
        timeline = materialize_timeline(transcript, plan)
        _write_json(directory / "visual-plan.json", plan)
        _write_json(timeline_path, timeline)

        _update(store, job_id, status="preflight", progresso=72, etapa="Executando preflight")
        report = preflight_timeline(
            source_path=source,
            transcript_payload=transcript,
            timeline_payload=timeline,
        )
        _write_json(directory / "preflight.json", report)
        if not report["ok"]:
            _update(
                store,
                job_id,
                status="failed",
                progresso=72,
                etapa="Preflight bloqueou a prévia",
                erro="Corrija os blockers antes de renderizar.",
                plannerMode=planner_mode,
            )
            return
        _update(
            store,
            job_id,
            status="needs_review",
            progresso=80,
            etapa="Plano visual pronto para revisão",
            plannerMode=planner_mode,
            transcriptPath=str(transcript_path),
            timelinePath=str(timeline_path),
        )
    except PostProductionCancelled:
        return
    except Exception as exc:
        _update(store, job_id, status="failed", etapa="Falha na análise", erro=str(exc)[-1200:])


def load_artifacts(output_root: Path, job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = job_directory(output_root, job_id)
    try:
        transcript = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
        timeline = json.loads((directory / "timeline.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Transcrição ou timeline ainda não está disponível.") from exc
    return transcript, timeline


def save_event_updates(
    *,
    output_root: Path,
    job_id: str,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    transcript, timeline = load_artifacts(output_root, job_id)
    by_id = {str(update.get("id")): update for update in updates}
    allowed_interactions = {
        "none",
        "caption_emphasis",
        "kinetic_text",
        "progressive_list",
        "supporting_visual",
        "cta_card",
        "definition_card",
        "number_card",
        "comparison_card",
        "quote_card",
        "evidence_card",
    }
    allowed_positions = {
        "top_left",
        "top_center",
        "top_right",
        "center_left",
        "center",
        "center_right",
        "bottom_left",
        "bottom_center",
        "bottom_right",
    }
    for event in timeline.get("events", []):
        update = by_id.get(str(event.get("id")))
        if not update:
            continue
        if "enabled" in update:
            event["enabled"] = bool(update["enabled"])
        if "visualText" in update:
            event["visualText"] = str(update["visualText"]).strip()[:100]
        if update.get("interactionType") in allowed_interactions:
            event["interactionType"] = update["interactionType"]
            if update["interactionType"] == "supporting_visual":
                event["assetRef"] = generated_asset_ref(
                    str(event.get("spokenText") or ""),
                    str(event.get("visualText") or ""),
                )
        if update.get("reviewStatus") in {"pending", "approved", "rejected"}:
            event["reviewStatus"] = update["reviewStatus"]
        if update.get("screenPosition") in allowed_positions:
            event["screenPosition"] = update["screenPosition"]
        if "backgroundColor" in update:
            color = str(update["backgroundColor"]).strip().lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", color):
                raise RuntimeError("A cor do visual precisa usar o formato hexadecimal #RRGGBB.")
            event["backgroundColor"] = color
        if "backgroundOpacity" in update:
            opacity = float(update["backgroundOpacity"])
            if opacity < 0.15 or opacity > 1:
                raise RuntimeError("A opacidade do visual precisa ficar entre 15% e 100%.")
            event["backgroundOpacity"] = round(opacity, 2)
        if update.get("timingSource") == "transcript":
            words = transcript.get("words") or []
            start_index = int(event.get("startWordIndex") or 0)
            end_index = int(event.get("endWordIndex") or 0)
            if start_index < 0 or end_index < start_index or end_index >= len(words):
                raise RuntimeError("Não foi possível restaurar o tempo original deste visual.")
            event["startMs"] = int(words[start_index].get("startMs") or 0)
            event["endMs"] = int(words[end_index].get("endMs") or 0)
            event["timingSource"] = "transcript"
        elif "startMs" in update or "endMs" in update:
            start_ms = int(update.get("startMs", event.get("startMs") or 0))
            end_ms = int(update.get("endMs", event.get("endMs") or 0))
            duration_ms = end_ms - start_ms
            if duration_ms < MIN_MANUAL_VISUAL_MS or duration_ms > MAX_MANUAL_VISUAL_MS:
                raise RuntimeError("O visual precisa durar entre 1,5 e 5,5 segundos.")
            if start_ms < 0 or end_ms > int(transcript.get("durationMs") or 0) + 250:
                raise RuntimeError("O tempo do visual precisa ficar dentro da duração do vídeo.")
            event["startMs"] = start_ms
            event["endMs"] = end_ms
            event["timingSource"] = "manual"
    # Material source cannot be edited here; stale is recalculated on every save.
    timeline["stale"] = timeline_is_stale(timeline, transcript)
    version_payload = json.dumps(timeline["events"], ensure_ascii=False, sort_keys=True).encode()
    timeline["version"] = f"sha256:{hashlib.sha256(version_payload).hexdigest()}"
    _write_json(artifact_path(output_root, job_id, "timeline.json"), timeline)
    return timeline


def run_preflight(*, output_root: Path, job_id: str) -> dict[str, Any]:
    transcript, timeline = load_artifacts(output_root, job_id)
    report = preflight_timeline(
        source_path=artifact_path(output_root, job_id, "source.mp4"),
        transcript_payload=transcript,
        timeline_payload=timeline,
    )
    _write_json(artifact_path(output_root, job_id, "preflight.json"), report)
    return report


def _srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _balanced_caption_lines(text: str) -> str:
    words = text.split()
    if len(text) <= 28 or len(words) < 3:
        return text
    candidates = []
    for split in range(1, len(words)):
        left = " ".join(words[:split])
        right = " ".join(words[split:])
        candidates.append((max(len(left), len(right)), abs(len(left) - len(right)), left, right))
    _, _, left, right = min(candidates)
    return f"{left}\n{right}"


def caption_cues(transcript: dict[str, Any]) -> list[tuple[int, int, str]]:
    """Build short, word-timed cues suitable for a vertical two-line caption."""
    cues: list[tuple[int, int, str]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(str(word.get("text") or "").strip() for word in current).strip()
        text = normalize_ptbr_medical_text(text)
        if text:
            cues.append(
                (
                    int(current[0].get("startMs") or 0),
                    int(current[-1].get("endMs") or current[0].get("startMs") or 0),
                    _balanced_caption_lines(text),
                )
            )
        current.clear()

    for raw_word in transcript.get("words", []):
        word = dict(raw_word)
        word_text = str(word.get("text") or "").strip()
        if not word_text:
            continue
        if current:
            candidate = " ".join([*(str(item.get("text") or "") for item in current), word_text])
            duration = int(word.get("endMs") or 0) - int(current[0].get("startMs") or 0)
            if (
                len(current) >= MAX_CAPTION_WORDS
                or len(candidate) > MAX_CAPTION_CHARS
                or duration > MAX_CAPTION_MS
            ):
                carry: list[dict[str, Any]] = []
                while len(current) > 2:
                    last_key = str(current[-1].get("text") or "").strip(".,:;!? ").casefold()
                    if last_key not in _CAPTION_DANGLING_ENDS:
                        break
                    carry.insert(0, current.pop())
                flush()
                if carry:
                    current.extend(carry)
        current.append(word)
        if len(current) >= 3 and word_text.endswith((".", "?", "!")):
            flush()
    flush()
    return cues


def _write_captions(transcript: dict[str, Any], destination: Path) -> int:
    cues = caption_cues(transcript)
    blocks = []
    for index, (start, end, text) in enumerate(cues, start=1):
        blocks.append(f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}")
    destination.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return len(cues)


def render_preview(*, store: JobStore, job_id: str, output_root: Path) -> dict[str, Any]:
    directory = job_directory(output_root, job_id)
    source = directory / "source.mp4"
    transcript, timeline = load_artifacts(output_root, job_id)
    report = run_preflight(output_root=output_root, job_id=job_id)
    if not report["ok"]:
        raise RuntimeError("O preflight contém blockers; a prévia não pode ser renderizada.")
    _update(store, job_id, status="rendering_preview", progresso=86, etapa="Renderizando prévia")
    overlays: list[TimedOverlay] = []
    manifest_events: list[dict[str, Any]] = []
    for index, event in enumerate(timeline.get("events", []), start=1):
        if not event.get("enabled") or event.get("interactionType") == "none":
            continue
        overlay_path = render_overlay(event, directory / "overlays" / f"{index:02d}-{event['id']}.png")
        overlays.append(
            TimedOverlay(
                path=overlay_path,
                start_seconds=float(event["startMs"]) / 1000,
                end_seconds=float(event["endMs"]) / 1000,
            )
        )
        manifest_events.append(event)
    captions = directory / "captions.srt"
    _write_captions(transcript, captions)
    end_card = render_medical_end_card(
        directory / "medical-end-card.png",
        project_root=Path(__file__).resolve().parents[2],
    )
    preview = directory / "preview.mp4"
    composition = compose_video(
        [
            CompositionScene(
                scene_id=job_id,
                video_path=source,
                timed_overlays=tuple(overlays),
                captions_path=captions,
            )
        ],
        preview,
        end_card_path=end_card,
        end_card_duration_seconds=MEDICAL_MINIMUM_END_CARD_SECONDS,
    )
    manifest = {
        "schemaVersion": "post-production-manifest-v1",
        "jobId": job_id,
        "sourcePath": str(source),
        "previewPath": str(preview),
        "videoFingerprint": transcript["videoFingerprint"],
        "transcriptVersion": transcript["version"],
        "timelineVersion": timeline["version"],
        "renderConfigVersion": RENDER_CONFIG_VERSION,
        "designVersion": DESIGN_VERSION,
        "events": manifest_events,
        "composition": composition,
    }
    _write_json(directory / "manifest.json", manifest)
    return _update(
        store,
        job_id,
        status="preview_ready",
        progresso=100,
        etapa="Prévia pronta",
        previewPath=str(preview),
        manifestPath=str(directory / "manifest.json"),
    )
