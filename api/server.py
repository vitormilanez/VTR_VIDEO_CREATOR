#!/usr/bin/env python3
"""
API local que serve os dados reais do projeto (snapshot do Google Sheets)
no formato que o frontend (web/) espera.

Roda em http://127.0.0.1:8000

Uso:
    ../.venv/bin/python -m uvicorn api.server:app --reload --port 8000
ou:
    python api/server.py
"""
from __future__ import annotations

import base64
from email import policy
from email.parser import Parser
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, quote_plus, unquote, urlparse

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from api.cut_service import cancel_cut_job as cancel_cut_worker
from api.cut_service import prepare_cut_job, process_cut_project
from api.job_store import JobStore
from api.pack_design import (
    FALLBACK_LAYOUTS,
    FIELD_NAMES,
    PACK_LAYOUTS,
    PACK_SCHEMA_VERSION,
    PACK_SLIDE_COUNT,
    PHOTO_LIBRARY,
    empty_fields,
    normalize_slide,
    pack_slides,
    photo_asset,
    repair_pack_copy,
    slide_headline,
    validate_pack_contract,
)
from api.services.heygen_catalog import build_catalog, default_voice_id, normalize_avatar_look
from api.services.script_performance import (
    LEGACY_OUTRO,
    PERFORMANCE_SCHEMA,
    SPEECH_PRESETS,
    VOICE_MOOD_PRESETS,
    build_performance_prompt,
    display_text as performance_display_text,
    duration_word_limits,
    fit_ten_second_text,
    fit_text_to_duration,
    normalize_performance_response,
    preview_text,
    speech_speed,
    strip_known_outros,
    video_agent_word_limits,
    voice_mood_direction,
    voice_settings,
)
from api.services.script_editor import (
    DEFAULT_SPEECH_PROFILE,
    EDITOR_OUTPUT_SCHEMA,
    MEDICAL_EDITORIAL_PROMPT_VERSION,
    SCRIPT_EDITOR_CONTRACT,
    SCRIPT_EDITOR_CONTRACT_VERSION,
    build_editor_prompt,
    duration_assessment,
    editor_cache_payload,
    evaluate_generation_gate,
    hash_text,
    medical_review_status,
    normalize_editor_output,
    normalize_text as normalize_editor_text,
    post_validate_editor_output,
    title_alignment,
)
from api.services.paid_generation import request_fingerprint, validate_paid_version
from api.services.provider_capabilities import (
    heygen_cli_version,
    inspect_heygen_capabilities,
    validate_video_agent_options,
    video_agent_create_args,
)
from api.services.video_generation import (
    DIRECT_VIDEO_DURATIONS,
    direct_video_payload,
    normalize_caption_srt,
)
from api.services.scene_generation import build_scene_generation_result
from api.services.video_composer import CompositionScene, compose_video
from api.services.post_production import (
    analyze_post_production,
    idempotency_key as post_production_idempotency_key,
    load_artifacts as load_post_production_artifacts,
    render_preview as render_post_production_preview,
    run_preflight as run_post_production_preflight,
    save_event_updates as save_post_production_event_updates,
)
from api.services.transcript_service import normalize_ptbr_medical_text
from api.services.local_video_kit import render_local_kit_video
from api.services.pack_context import PACK_CONTEXT_VERSION, build_pack_context
from api.video_slides import render_video_slides
from integrations.heygen_client import load_dotenv
from integrations.google_news import resolve_google_news_url
from integrations.instagram_client import InstagramClient
from integrations.portuguese_br import prepare_script_for_heygen_voice

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(str(ROOT / ".env"))
SNAPSHOT = ROOT / "data" / "sheets_snapshot.json"
VIDEO_JOBS = ROOT / "data" / "video_jobs.json"
AVATAR_JOBS = ROOT / "data" / "avatar_jobs.json"
APP_SETTINGS = ROOT / "data" / "app_settings.json"
HEYGEN_AVATAR_CACHE = ROOT / "data" / "heygen_avatar_cache.json"
OPERATIONAL_DB = ROOT / "data" / "operations.db"
CUT_UPLOADS = ROOT / "data" / "cut_uploads"
LOCAL_VIDEO_KIT_UPLOADS = ROOT / "data" / "local_video_kit_uploads"
LOCAL_VIDEO_KIT_JOBS = ROOT / "data" / "local_video_kits"
CONTENT_VIDEOS = ROOT / "content" / "videos"
LOCAL_VIDEO_KIT_OUTPUTS = CONTENT_VIDEOS / "video feito"
PRODUCED_VIDEO_OUTPUTS = CONTENT_VIDEOS / "produzidos"
CUT_OUTPUTS = CONTENT_VIDEOS / "cortes"
POST_PRODUCTION_OUTPUTS = CONTENT_VIDEOS / "pos-producao"
PACK_AVATAR_ASSETS = ROOT / "data" / "pack_assets" / "avatars"
PACK_PHOTO_ASSETS = ROOT / "data" / "pack_assets" / "photos"
VIDEO_SLIDE_OUTPUTS = ROOT / "data" / "video_slides"
COMPOSED_VIDEO_OUTPUTS = PRODUCED_VIDEO_OUTPUTS / "composicoes"
MUSIC_TRACKS_DIR = ROOT / "data" / "music_tracks"
MANDATORY_VIDEO_OUTRO = LEGACY_OUTRO
LOGGER = logging.getLogger("uvicorn.error")
_PAID_GENERATION_LOCKS_GUARD = threading.Lock()
_PAID_GENERATION_LOCKS: dict[str, threading.RLock] = {}


def _paid_generation_lock(script_id: str) -> threading.RLock:
    """Serializa gate + reserva apenas para o mesmo roteiro neste processo."""

    with _PAID_GENERATION_LOCKS_GUARD:
        return _PAID_GENERATION_LOCKS.setdefault(script_id, threading.RLock())

# Biblioteca local: arquivos enviados pelo usuário, sem upload ou chamada paga.
# O compositor usa essas faixas apenas depois de as cenas HeyGen ficarem prontas.
MUSIC_LIBRARY: tuple[dict[str, Any], ...] = (
    {"id": "soft-focus", "file": "hitslab-soft-soft-music-333111.mp3", "name": "Soft Focus", "artist": "Hitslab", "mood": "Leve e acolhedora", "durationSeconds": 120.03},
    {"id": "growth-stage", "file": "jonasblakewood-growth-stage-vocal-322013.mp3", "name": "Growth Stage", "artist": "Jonas Blakewood", "mood": "Inspiradora com vocal", "durationSeconds": 166.03},
    {"id": "yoga-sunrise", "file": "alex-morgan-yoga-sunrise-flow-stretch-578496.mp3", "name": "Yoga Sunrise", "artist": "Alex Morgan", "mood": "Calma e otimista", "durationSeconds": 174.79},
    {"id": "calm-water", "file": "alex-morgan-calm-still-water-breathing-578483.mp3", "name": "Calm Still Water", "artist": "Alex Morgan", "mood": "Serena e discreta", "durationSeconds": 122.4},
    {"id": "cartoon-bouncy", "file": "alex-morgan-cartoon-bouncy-chase-antics-578472.mp3", "name": "Cartoon Bouncy", "artist": "Alex Morgan", "mood": "Leve e divertida", "durationSeconds": 76.58},
    {"id": "sunny-vlog", "file": "alex-morgan-vlog-sunny-travel-diary-578504.mp3", "name": "Sunny Vlog", "artist": "Alex Morgan", "mood": "Solar e descontraída", "durationSeconds": 192.62},
    {"id": "khokka-pop", "file": "kontraa-khokka-nepalese-pop-music-579826.mp3", "name": "Khokka Pop", "artist": "Kontraa", "mood": "Pop com energia", "durationSeconds": 224.88},
    {"id": "too-lost", "file": "kontraa-too-lost-trap-soul-music-579792.mp3", "name": "Too Lost", "artist": "Kontraa", "mood": "Trap soul", "durationSeconds": 157.61},
)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    reconciliation = _reconcile_incomplete_video_jobs()
    if any(reconciliation.values()):
        LOGGER.info(
            "video_job_reconciliation failed_safe=%s submission_uncertain=%s",
            reconciliation["failedSafe"],
            reconciliation["submissionUncertain"],
        )
    resume_interrupted_cut_projects()
    resume_interrupted_post_production_jobs()
    yield


app = FastAPI(title="AI Video Creator API", version="0.1.0", lifespan=_lifespan)

# Dev: o frontend roda em outra porta (vite). Liberar localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Helpers de normalizacao (colunas PT-BR do Sheets -> tipos do frontend)
# --------------------------------------------------------------------------- #
def _load_env_file() -> None:
    """Carrega variaveis locais sem sobrescrever variaveis ja definidas."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Snapshot nao encontrado em {SNAPSHOT}. "
                "Rode: python sync_sheets_snapshot.py"
            ),
        )
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _music_track(track_id: str | None) -> dict[str, Any] | None:
    normalized = str(track_id or "").strip()
    return next((track for track in MUSIC_LIBRARY if track["id"] == normalized), None)


def _music_track_path(track_id: str | None) -> Path | None:
    track = _music_track(track_id)
    if not track:
        return None
    path = MUSIC_TRACKS_DIR / str(track["file"])
    if not path.is_file():
        raise HTTPException(status_code=503, detail=f"A trilha '{track['name']}' não está disponível localmente.")
    return path


def _music_track_response(track: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": track["id"],
        "name": track["name"],
        "artist": track["artist"],
        "mood": track["mood"],
        "durationSeconds": track["durationSeconds"],
        "url": f"/api/music-tracks/{quote(str(track['id']), safe='')}/file",
    }


def _ai_db() -> sqlite3.Connection:
    """Abre o banco operacional usado para cache e medicao de chamadas de IA."""
    conn = sqlite3.connect(OPERATIONAL_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError as exc:
        # Another request may be enabling WAL while this connection opens.
        # The busy timeout protects the actual reads/writes, so this startup
        # race is safe to ignore without masking unrelated SQLite failures.
        if "database is locked" not in str(exc).lower():
            raise
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            operation TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ai_response_cache (
            cache_key TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS script_editor_states (
            script_id TEXT PRIMARY KEY,
            duration_seconds INTEGER NOT NULL DEFAULT 45,
            human_review_approved INTEGER NOT NULL DEFAULT 0,
            title_choice TEXT NOT NULL DEFAULT 'current',
            suggested_title TEXT,
            schema_valid INTEGER NOT NULL DEFAULT 1,
            technical_error TEXT,
            previous_script TEXT,
            last_result_json TEXT,
            script_revision INTEGER NOT NULL DEFAULT 0,
            final_speech_hash TEXT,
            approved_script_revision INTEGER,
            approved_final_speech_hash TEXT,
            approval_history_json TEXT NOT NULL DEFAULT '[]',
            contract_version TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS production_profiles (
            script_id TEXT PRIMARY KEY,
            avatar_id TEXT NOT NULL,
            voice_id TEXT NOT NULL,
            speech_mode TEXT NOT NULL,
            generation_mode TEXT NOT NULL,
            avatar_mode TEXT NOT NULL DEFAULT 'single',
            avatar_set_id TEXT,
            primary_avatar_id TEXT,
            position_count INTEGER NOT NULL DEFAULT 1,
            music_track_id TEXT,
            music_volume REAL NOT NULL DEFAULT 0.12,
            cinematic_prompt TEXT NOT NULL DEFAULT '',
            voice_mood TEXT NOT NULL DEFAULT 'confident',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS avatar_sets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            voice_id TEXT NOT NULL,
            looks_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scene_plans (
            script_id TEXT PRIMARY KEY,
            plan_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visual_plans (
            script_id TEXT PRIMARY KEY,
            plan_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS video_slide_renders (
            script_id TEXT PRIMARY KEY,
            render_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visual_packs (
            script_id TEXT PRIMARY KEY,
            pack_json TEXT NOT NULL,
            source_avatar_id TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_capabilities (
            provider TEXT PRIMARY KEY,
            cli_version TEXT NOT NULL,
            capabilities_version TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            checked_at TEXT NOT NULL
        );
        """
    )
    # Existing local databases predate Avatar Sets. Keep them usable without
    # requiring a destructive migration or touching the Google Sheets schema.
    for column, definition in (
        ("avatar_mode", "TEXT NOT NULL DEFAULT 'single'"),
        ("avatar_set_id", "TEXT"),
        ("primary_avatar_id", "TEXT"),
        ("position_count", "INTEGER NOT NULL DEFAULT 1"),
        ("music_track_id", "TEXT"),
        ("music_volume", "REAL NOT NULL DEFAULT 0.12"),
        ("cinematic_prompt", "TEXT NOT NULL DEFAULT ''"),
        ("voice_mood", "TEXT NOT NULL DEFAULT 'confident'"),
    ):
        try:
            conn.execute(f"ALTER TABLE production_profiles ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    for column, definition in (
        ("script_revision", "INTEGER NOT NULL DEFAULT 0"),
        ("final_speech_hash", "TEXT"),
        ("approved_script_revision", "INTEGER"),
        ("approved_final_speech_hash", "TEXT"),
        ("approval_history_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("contract_version", "TEXT NOT NULL DEFAULT ''"),
    ):
        try:
            conn.execute(f"ALTER TABLE script_editor_states ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.commit()
    return conn


def _canonical_script_speech(script: dict[str, Any] | None) -> str:
    if not script:
        return ""
    saved = str(script.get("textoFalado") or "").strip()
    if saved:
        return saved
    parts = (
        script.get("hook"),
        script.get("dorConflito"),
        script.get("explicacaoSimples"),
        script.get("virada"),
        script.get("cta"),
    )
    return "\n\n".join(str(part).strip() for part in parts if str(part or "").strip())


def _approval_history(value: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _script_editor_state(
    script_id: str,
    script: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_speech = _canonical_script_speech(script)
    current_hash = hash_text(current_speech) if current_speech else None
    legacy_fallback = False
    conn = _ai_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT script_id, duration_seconds, human_review_approved, title_choice,
                      suggested_title, schema_valid, technical_error, previous_script,
                      last_result_json, script_revision, final_speech_hash,
                      approved_script_revision, approved_final_speech_hash,
                      approval_history_json, contract_version, updated_at
               FROM script_editor_states WHERE script_id = ?""",
            (script_id,),
        ).fetchone()
        if not row:
            legacy_fallback = True
            revision = 1 if current_hash else 0
            legacy_approved = bool(
                script and script.get("status") == "aprovado_clinicamente" and current_hash
            )
            history = []
            if legacy_approved:
                history.append(
                    {
                        "actor": "legacy_script_status",
                        "timestamp": _now(),
                        "previousStatus": "unknown",
                        "nextStatus": "approved",
                        "scriptRevision": revision,
                        "finalSpeechHash": current_hash,
                        "reason": "Migração do status clínico persistido.",
                    }
                )
            conn.execute(
                """INSERT INTO script_editor_states(
                       script_id, duration_seconds, human_review_approved, title_choice,
                       suggested_title, schema_valid, technical_error, previous_script,
                       last_result_json, script_revision, final_speech_hash,
                       approved_script_revision, approved_final_speech_hash,
                       approval_history_json, contract_version, updated_at
                   ) VALUES (?, 45, ?, 'current', NULL, 1, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    script_id,
                    int(legacy_approved),
                    revision,
                    current_hash,
                    revision if legacy_approved else None,
                    current_hash if legacy_approved else None,
                    json.dumps(history, ensure_ascii=False),
                    SCRIPT_EDITOR_CONTRACT_VERSION,
                    _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM script_editor_states WHERE script_id = ?", (script_id,)
            ).fetchone()
        elif current_hash:
            revision = int(row["script_revision"] or 0)
            stored_hash = row["final_speech_hash"]
            approved = bool(row["human_review_approved"])
            approved_revision = row["approved_script_revision"]
            approved_hash = row["approved_final_speech_hash"]
            history = _approval_history(row["approval_history_json"])
            if not stored_hash:
                revision = max(1, revision)
                # Migração calculável: uma aprovação legada é vinculada à fala
                # atual uma única vez. Mudanças futuras sempre reabrem a revisão.
                if approved and (approved_revision is None or not approved_hash):
                    approved_revision = revision
                    approved_hash = current_hash
                    history.append(
                        {
                            "actor": "legacy_state_migration",
                            "timestamp": _now(),
                            "previousStatus": "approved_unversioned",
                            "nextStatus": "approved",
                            "scriptRevision": revision,
                            "finalSpeechHash": current_hash,
                            "reason": "Aprovação legada vinculada à fala recalculada.",
                        }
                    )
            elif stored_hash != current_hash:
                previous_status = "approved" if approved else "open"
                revision = max(1, revision + 1)
                approved = False
                approved_revision = None
                approved_hash = None
                history.append(
                    {
                        "actor": "system",
                        "timestamp": _now(),
                        "previousStatus": previous_status,
                        "nextStatus": "reopened",
                        "scriptRevision": revision,
                        "finalSpeechHash": current_hash,
                        "reason": "A fala final salva foi alterada.",
                    }
                )
            approval_matches = bool(
                approved
                and approved_revision == revision
                and approved_hash == current_hash
            )
            conn.execute(
                """UPDATE script_editor_states
                   SET human_review_approved=?, script_revision=?, final_speech_hash=?,
                       approved_script_revision=?, approved_final_speech_hash=?,
                       approval_history_json=?, contract_version=?, updated_at=?
                   WHERE script_id=?""",
                (
                    int(approval_matches),
                    revision,
                    current_hash,
                    approved_revision if approval_matches else None,
                    approved_hash if approval_matches else None,
                    json.dumps(history, ensure_ascii=False),
                    SCRIPT_EDITOR_CONTRACT_VERSION,
                    _now(),
                    script_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM script_editor_states WHERE script_id = ?", (script_id,)
            ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("Não foi possível inicializar o estado versionado do roteiro.")
    try:
        last_result = json.loads(str(row["last_result_json"])) if row["last_result_json"] else None
    except json.JSONDecodeError:
        last_result = None
    return {
        "scriptId": row["script_id"],
        "durationSeconds": int(row["duration_seconds"]),
        "humanReviewApproved": bool(row["human_review_approved"]),
        "titleChoice": row["title_choice"] or "current",
        "suggestedTitle": row["suggested_title"],
        "schemaValid": bool(row["schema_valid"]),
        "technicalError": row["technical_error"],
        "previousScript": row["previous_script"],
        "lastResult": last_result,
        "scriptRevision": int(row["script_revision"] or 0),
        "finalSpeechHash": row["final_speech_hash"],
        "approvedScriptRevision": row["approved_script_revision"],
        "approvedFinalSpeechHash": row["approved_final_speech_hash"],
        "approvalHistory": _approval_history(row["approval_history_json"]),
        "contractVersion": row["contract_version"] or SCRIPT_EDITOR_CONTRACT_VERSION,
        "updatedAt": row["updated_at"],
        "legacyFallback": legacy_fallback,
    }


def _save_script_editor_state(
    state: dict[str, Any],
    script: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _script_editor_state(str(state["scriptId"]), script)
    requested_approval = bool(state.get("humanReviewApproved"))
    current_hash = current.get("finalSpeechHash")
    current_revision = int(current.get("scriptRevision") or 0)
    approval_allowed = bool(requested_approval and current_hash and current_revision > 0)
    history = list(current.get("approvalHistory") or [])
    if approval_allowed != bool(current.get("humanReviewApproved")):
        history.append(
            {
                "actor": str(state.get("reviewActor") or "editor_user"),
                "timestamp": _now(),
                "previousStatus": (
                    "approved" if current.get("humanReviewApproved") else "open"
                ),
                "nextStatus": "approved" if approval_allowed else "reopened",
                "scriptRevision": current_revision,
                "finalSpeechHash": current_hash,
                "reason": state.get("reviewReason"),
            }
        )
    normalized = {
        "scriptId": str(state["scriptId"]),
        "durationSeconds": int(state.get("durationSeconds") or 45),
        "humanReviewApproved": approval_allowed,
        "titleChoice": str(state.get("titleChoice") or "current"),
        "suggestedTitle": state.get("suggestedTitle"),
        "schemaValid": bool(state.get("schemaValid", True)),
        "technicalError": state.get("technicalError"),
        "previousScript": state.get("previousScript"),
        "lastResult": state.get("lastResult"),
        "scriptRevision": current_revision,
        "finalSpeechHash": current_hash,
        "approvedScriptRevision": current_revision if approval_allowed else None,
        "approvedFinalSpeechHash": current_hash if approval_allowed else None,
        "approvalHistory": history,
        "contractVersion": SCRIPT_EDITOR_CONTRACT_VERSION,
        "updatedAt": _now(),
    }
    conn = _ai_db()
    try:
        conn.execute(
            """INSERT INTO script_editor_states(
                   script_id, duration_seconds, human_review_approved, title_choice,
                   suggested_title, schema_valid, technical_error, previous_script,
                   last_result_json, script_revision, final_speech_hash,
                   approved_script_revision, approved_final_speech_hash,
                   approval_history_json, contract_version, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(script_id) DO UPDATE SET
                   duration_seconds=excluded.duration_seconds,
                   human_review_approved=excluded.human_review_approved,
                   title_choice=excluded.title_choice,
                   suggested_title=excluded.suggested_title,
                   schema_valid=excluded.schema_valid,
                   technical_error=excluded.technical_error,
                   previous_script=excluded.previous_script,
                   last_result_json=excluded.last_result_json,
                   script_revision=excluded.script_revision,
                   final_speech_hash=excluded.final_speech_hash,
                   approved_script_revision=excluded.approved_script_revision,
                   approved_final_speech_hash=excluded.approved_final_speech_hash,
                   approval_history_json=excluded.approval_history_json,
                   contract_version=excluded.contract_version,
                   updated_at=excluded.updated_at""",
            (
                normalized["scriptId"], normalized["durationSeconds"],
                int(normalized["humanReviewApproved"]), normalized["titleChoice"],
                normalized["suggestedTitle"], int(normalized["schemaValid"]),
                normalized["technicalError"], normalized["previousScript"],
                json.dumps(normalized["lastResult"], ensure_ascii=False)
                if normalized["lastResult"] is not None else None,
                normalized["scriptRevision"], normalized["finalSpeechHash"],
                normalized["approvedScriptRevision"], normalized["approvedFinalSpeechHash"],
                json.dumps(normalized["approvalHistory"], ensure_ascii=False),
                normalized["contractVersion"],
                normalized["updatedAt"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {**normalized, "legacyFallback": False}


def _resolved_medical_review_status(
    script: dict[str, Any],
    editor_state: dict[str, Any],
    requested_status: str | None = None,
) -> str:
    """Resolve revisão sem permitir que um alerta persistido seja rebaixado."""
    approved = bool(editor_state.get("humanReviewApproved"))
    if approved:
        return "approved"
    last_result = editor_state.get("lastResult")
    persisted_required = bool(
        isinstance(last_result, dict)
        and (
            last_result.get("medicalReviewStatus") == "required"
            or bool((last_result.get("medicalSafety") or {}).get("requiresHumanReview"))
        )
    )
    if persisted_required or requested_status == "required":
        return "required"
    risk_status = medical_review_status(str(script.get("risco") or "medio"), approved=False)
    if risk_status == "required":
        return "required"
    if requested_status == "recommended" or risk_status == "recommended":
        return "recommended"
    return "not_required"


def _production_profile(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            """
            SELECT script_id, avatar_id, voice_id, speech_mode, generation_mode,
                   avatar_mode, avatar_set_id, primary_avatar_id, position_count,
                   music_track_id, music_volume, cinematic_prompt, voice_mood, updated_at
            FROM production_profiles
            WHERE script_id = ?
            """,
            (script_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "scriptId": row["script_id"],
        "avatarId": row["avatar_id"],
        "voiceId": row["voice_id"],
        "speechMode": row["speech_mode"],
        "generationMode": row["generation_mode"],
        "avatarMode": row["avatar_mode"] or "single",
        "avatarSetId": row["avatar_set_id"],
        "primaryAvatarId": row["primary_avatar_id"] or row["avatar_id"],
        "positionCount": int(row["position_count"] or 1),
        "musicTrackId": row["music_track_id"],
        "musicVolume": float(row["music_volume"] or 0.12),
        "cinematicPrompt": str(row["cinematic_prompt"] or ""),
        "voiceMood": _clean_voice_mood(row["voice_mood"]),
        "updatedAt": row["updated_at"],
    }


AVATAR_SET_ROLES = frozenset({"primary", "front", "close", "three_quarter", "standing", "wide"})


def _normalize_avatar_set_looks(looks: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    roles: set[str] = set()
    avatar_ids: set[str] = set()
    for raw in looks:
        avatar_id = str(raw.get("avatarId") or raw.get("avatar_id") or "").strip()
        role = str(raw.get("role") or "").strip()
        label = re.sub(r"\s+", " ", str(raw.get("label") or role)).strip()
        if not avatar_id:
            raise HTTPException(status_code=422, detail="Cada look do Avatar Set precisa de avatarId.")
        if role not in AVATAR_SET_ROLES:
            raise HTTPException(status_code=422, detail=f"Role de Avatar Set invalida: {role or 'vazio'}.")
        if role in roles:
            raise HTTPException(status_code=422, detail=f"O role '{role}' aparece mais de uma vez no Avatar Set.")
        roles.add(role)
        avatar_ids.add(avatar_id)
        normalized.append({"avatarId": avatar_id, "role": role, "label": label or role})
    if len(normalized) < 2 or len(avatar_ids) < 2:
        raise HTTPException(
            status_code=422,
            detail="Um Avatar Set precisa de pelo menos duas posições/looks diferentes do mesmo avatar.",
        )
    return normalized


def _avatar_set(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "voiceId": row["voice_id"],
        "looks": json.loads(str(row["looks_json"])),
        "updatedAt": row["updated_at"],
    }


def _list_avatar_sets() -> list[dict[str, Any]]:
    conn = _ai_db()
    try:
        rows = conn.execute("SELECT id, name, voice_id, looks_json, updated_at FROM avatar_sets ORDER BY name COLLATE NOCASE").fetchall()
    finally:
        conn.close()
    return [_avatar_set(row) for row in rows]


def _get_avatar_set(avatar_set_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT id, name, voice_id, looks_json, updated_at FROM avatar_sets WHERE id = ?",
            (avatar_set_id,),
        ).fetchone()
    finally:
        conn.close()
    return _avatar_set(row) if row else None


def _save_avatar_set(
    *,
    name: str,
    voice_id: str,
    looks: list[dict[str, Any]],
    avatar_set_id: str | None = None,
) -> dict[str, Any]:
    clean_name = re.sub(r"\s+", " ", name).strip()
    clean_voice_id = str(voice_id).strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Dê um nome ao Avatar Set.")
    if not clean_voice_id:
        raise HTTPException(status_code=422, detail="Avatar Set precisa de voiceId.")
    normalized_looks = _normalize_avatar_set_looks(looks)
    saved = {
        "id": avatar_set_id or f"avatar-set-{uuid.uuid4().hex[:12]}",
        "name": clean_name[:160],
        "voiceId": clean_voice_id[:160],
        "looks": normalized_looks,
        "updatedAt": _now(),
    }
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO avatar_sets(id, name, voice_id, looks_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                voice_id = excluded.voice_id,
                looks_json = excluded.looks_json,
                updated_at = excluded.updated_at
            """,
            (
                saved["id"],
                saved["name"],
                saved["voiceId"],
                json.dumps(saved["looks"], ensure_ascii=False),
                saved["updatedAt"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return saved


def _clean_cinematic_prompt(value: Any) -> str:
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]
    cleaned = "\n".join(line for line in lines if line).strip()
    return cleaned[:2000]


def _clean_voice_mood(value: Any) -> str:
    mood = str(value or "confident").strip().lower()
    return mood if mood in VOICE_MOOD_PRESETS else "confident"


def _save_production_profile(profile: dict[str, Any]) -> dict[str, Any]:
    avatar_mode = str(profile.get("avatarMode") or "single")
    if avatar_mode not in {"single", "set"}:
        raise HTTPException(status_code=422, detail="avatarMode deve ser 'single' ou 'set'.")
    avatar_set_id = str(profile.get("avatarSetId") or "").strip() or None
    primary_avatar_id = str(profile.get("primaryAvatarId") or profile.get("avatarId") or "").strip()
    if avatar_mode == "set":
        avatar_set = _get_avatar_set(avatar_set_id or "")
        if not avatar_set:
            raise HTTPException(status_code=422, detail="Avatar Set não encontrado.")
        set_avatar_ids = {look["avatarId"] for look in avatar_set["looks"]}
        if primary_avatar_id not in set_avatar_ids:
            raise HTTPException(status_code=422, detail="primaryAvatarId precisa pertencer ao Avatar Set.")
    if not primary_avatar_id:
        raise HTTPException(status_code=422, detail="Selecione um avatar principal.")
    music_track_id = str(profile.get("musicTrackId") or "").strip() or None
    if music_track_id and not _music_track(music_track_id):
        raise HTTPException(status_code=422, detail="Trilha de fundo não encontrada na biblioteca local.")
    music_volume = float(profile.get("musicVolume") or 0.12)
    if not 0.03 <= music_volume <= 0.25:
        raise HTTPException(status_code=422, detail="O volume da trilha deve estar entre 3% e 25%.")
    cinematic_prompt = _clean_cinematic_prompt(profile.get("cinematicPrompt"))
    voice_mood = _clean_voice_mood(profile.get("voiceMood"))
    saved = {
        "scriptId": str(profile["scriptId"]),
        "avatarId": primary_avatar_id,
        "voiceId": str(profile["voiceId"]),
        "speechMode": str(profile["speechMode"]),
        "generationMode": str(profile["generationMode"]),
        "avatarMode": avatar_mode,
        "avatarSetId": avatar_set_id,
        "primaryAvatarId": primary_avatar_id,
        "positionCount": 2 if avatar_mode == "set" else 1,
        "musicTrackId": music_track_id,
        "musicVolume": music_volume,
        "cinematicPrompt": cinematic_prompt,
        "voiceMood": voice_mood,
        "updatedAt": _now(),
    }
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO production_profiles(
                script_id, avatar_id, voice_id, speech_mode, generation_mode,
                avatar_mode, avatar_set_id, primary_avatar_id, position_count,
                music_track_id, music_volume, cinematic_prompt, voice_mood, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                avatar_id = excluded.avatar_id,
                voice_id = excluded.voice_id,
                speech_mode = excluded.speech_mode,
                generation_mode = excluded.generation_mode,
                avatar_mode = excluded.avatar_mode,
                avatar_set_id = excluded.avatar_set_id,
                primary_avatar_id = excluded.primary_avatar_id,
                position_count = excluded.position_count,
                music_track_id = excluded.music_track_id,
                music_volume = excluded.music_volume,
                cinematic_prompt = excluded.cinematic_prompt,
                voice_mood = excluded.voice_mood,
                updated_at = excluded.updated_at
            """,
            (
                saved["scriptId"],
                saved["avatarId"],
                saved["voiceId"],
                saved["speechMode"],
                saved["generationMode"],
                saved["avatarMode"],
                saved["avatarSetId"],
                saved["primaryAvatarId"],
                saved["positionCount"],
                saved["musicTrackId"],
                saved["musicVolume"],
                saved["cinematicPrompt"],
                saved["voiceMood"],
                saved["updatedAt"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return saved


def _resolve_scene_plan(script_id: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    profile = _production_profile(script_id)
    if not profile:
        raise HTTPException(status_code=409, detail="Salve o perfil de produção antes do Scene Plan.")
    avatar_set = _get_avatar_set(str(profile.get("avatarSetId") or "")) if profile.get("avatarMode") == "set" else None
    look_to_avatar = {
        str(look["role"]): str(look["avatarId"])
        for look in (avatar_set or {}).get("looks", [])
        if look.get("role") and look.get("avatarId")
    }
    primary_avatar_id = str(profile.get("primaryAvatarId") or profile.get("avatarId") or "")
    resolved_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        look_role = str(scene.get("lookRole") or "primary")
        avatar_id = look_to_avatar.get(look_role) or primary_avatar_id
        if not avatar_id:
            raise HTTPException(status_code=422, detail=f"Não foi possível resolver o avatar da cena {index}.")
        resolved_scenes.append(
            {
                "id": str(scene.get("id") or f"scene-{index}"),
                "order": index,
                "text": re.sub(r"\s+", " ", str(scene.get("text") or "")).strip(),
                "lookRole": look_role if look_role in AVATAR_SET_ROLES else "primary",
                "avatarId": avatar_id,
                "estimatedStart": max(0, float(scene.get("estimatedStart") or 0)),
                "estimatedEnd": max(0, float(scene.get("estimatedEnd") or 0)),
            }
        )
    return {"scriptId": script_id, "scenes": resolved_scenes, "updatedAt": _now()}


def _scene_plan(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT plan_json FROM scene_plans WHERE script_id = ?",
            (script_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(str(row["plan_json"]))


def _save_scene_plan(script_id: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    plan = _resolve_scene_plan(script_id, scenes)
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO scene_plans(script_id, plan_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                plan_json = excluded.plan_json,
                updated_at = excluded.updated_at
            """,
            (script_id, json.dumps(plan, ensure_ascii=False), plan["updatedAt"]),
        )
        conn.commit()
    finally:
        conn.close()
    return plan


def _refresh_scene_plan_avatar_bindings(script_id: str) -> dict[str, Any] | None:
    """Re-resolve persisted scene roles against the currently selected Avatar Set.

    Scene plans intentionally persist semantic roles (for example ``close`` and
    ``front``). Avatar Set edits can replace the concrete HeyGen IDs behind those
    roles, so a saved ``avatarId`` must never remain authoritative at generation
    time.
    """
    stored = _scene_plan(script_id)
    if not stored or not stored.get("scenes"):
        return stored
    resolved = _resolve_scene_plan(script_id, list(stored["scenes"]))
    stored_bindings = [
        (
            str(scene.get("id") or ""),
            str(scene.get("lookRole") or "primary"),
            str(scene.get("avatarId") or ""),
        )
        for scene in stored["scenes"]
    ]
    resolved_bindings = [
        (
            str(scene.get("id") or ""),
            str(scene.get("lookRole") or "primary"),
            str(scene.get("avatarId") or ""),
        )
        for scene in resolved["scenes"]
    ]
    if stored_bindings == resolved_bindings:
        return stored
    LOGGER.info("Scene Plan avatar bindings refreshed: script_id=%s", script_id)
    return _save_scene_plan(script_id, list(stored["scenes"]))


VIDEO_VISUAL_DESIGN_SYSTEM_VERSION = "video-vertical-v1"
VIDEO_VISUAL_TYPES = frozenset({"none", "full_slide", "overlay", "statistic", "comparison", "quote"})
VIDEO_VISUAL_MOTION_PRESETS = frozenset({"none", "fade", "soft_zoom", "fade_zoom"})
VIDEO_VISUAL_LAYOUTS = frozenset(
    {
        "hero_photo",
        "photo_split",
        "big_statement",
        "question",
        "myth_fact",
        "number_stat",
        "three_points",
        "explainer",
        "doctor_quote",
        "photo_overlay",
        "do_dont",
        "cta_photo",
    }
)


def _required_visual_support_count(scene_count: int) -> int:
    """Apoios visuais entram durante a fala antes do próximo look/cena."""
    return max(0, scene_count - 1)


def _visual_support_required(scene_index: int, scene_count: int) -> bool:
    return scene_index < _required_visual_support_count(scene_count)


def _compact_words(value: str, *, max_words: int, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" .,:;") + "…"
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip(" .,:;") + "…"
    return text


def _semantic_visual_label(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lower = text.casefold()
    if "caloria" in lower:
        return "Calorias vazias"
    if "déficit" in lower or "deficit" in lower:
        return "Déficit menor"
    if "controle" in lower or "aliment" in lower:
        return "Menos controle"
    if "prioriza" in lower and "álcool" in lower:
        return "Álcool primeiro"
    if "gordura" in lower and ("queimar" in lower or "queima" in lower):
        return "Gordura depois"
    if "desativa" in lower and "não" in lower:
        return "Não desativa"
    if "interfere" in lower:
        return "Interfere no processo"
    if "médico" in lower or "medico" in lower:
        return "Converse com médico"
    return _compact_words(text, max_words=3, max_chars=24)


def _visual_body_points(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    raw_points = re.split(r"\s*[•·;]\s*|\s+\d+[.)]\s+", text)
    points = [_semantic_visual_label(point.strip(" -–—:.")) for point in raw_points]
    return [point for point in points if point][:3]


def _compact_visual_body(value: str) -> str:
    points = _visual_body_points(value)
    if len(points) >= 2:
        return " • ".join(points)
    return _compact_words(value, max_words=8, max_chars=76)


def _fallback_visual_from_scene(scene: dict[str, Any], index: int) -> dict[str, str]:
    text = re.sub(r"\s+", " ", str(scene.get("text") or "")).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", text)[0] if text else ""
    headline = _compact_words(first_sentence, max_words=6, max_chars=54) or f"Apoio visual {index + 1}"
    body = _compact_visual_body(text[len(first_sentence):].strip() if first_sentence and len(text) > len(first_sentence) else "")
    return {
        "type": "full_slide",
        "layout": "big_statement",
        "headline": headline,
        "body": body,
        "purpose": "Apoiar visualmente a fala enquanto o áudio do avatar continua.",
    }


def _normalize_video_visual(
    visual: dict[str, Any],
    *,
    scene: dict[str, Any],
    index: int,
    scene_count: int,
    strict_required: bool = False,
) -> dict[str, str]:
    visual_type = str(visual.get("type") or "none")
    if visual_type not in VIDEO_VISUAL_TYPES:
        visual_type = "none"
    layout = str(visual.get("layout") or "")
    if layout not in VIDEO_VISUAL_LAYOUTS:
        layout = ""
    headline = _compact_words(str(visual.get("headline") or ""), max_words=7, max_chars=58)
    body = _compact_visual_body(str(visual.get("body") or ""))
    purpose = re.sub(r"\s+", " ", str(visual.get("purpose") or "")).strip()[:300]
    try:
        start_ratio = float(visual.get("startRatio", 0.65))
    except (TypeError, ValueError):
        start_ratio = 0.65
    start_ratio = max(0.15, min(0.70, start_ratio))
    try:
        duration_seconds = float(visual.get("durationSeconds", 2.5))
    except (TypeError, ValueError):
        duration_seconds = 2.5
    duration_seconds = max(1.0, min(5.0, duration_seconds))
    motion_preset = str(visual.get("motionPreset") or "fade")
    if motion_preset not in VIDEO_VISUAL_MOTION_PRESETS:
        motion_preset = "fade"
    support_required = _visual_support_required(index, scene_count)
    if support_required and (visual_type == "none" or not headline):
        if strict_required:
            raise HTTPException(
                status_code=422,
                detail=f"A cena {index + 1} precisa de um apoio visual porque há uma próxima cena/look.",
            )
        fallback = _fallback_visual_from_scene(scene, index)
        visual_type = str(fallback["type"])
        layout = str(fallback["layout"])
        headline = headline or str(fallback["headline"])
        body = body or str(fallback["body"])
        purpose = purpose or str(fallback["purpose"])
    if scene_count > 1 and not support_required and index >= _required_visual_support_count(scene_count):
        visual_type = "none"
    if visual_type == "none":
        layout = ""
        headline = ""
        body = ""
        purpose = ""
        start_ratio = 0.0
        duration_seconds = 0.0
        motion_preset = "none"
    elif not layout:
        layout = "big_statement"
    if visual_type != "none":
        _validate_production_compliance(headline, field=f"Headline visual da cena {index + 1}")
        _validate_production_compliance(body, field=f"Body visual da cena {index + 1}")
    return {
        "type": visual_type,
        "layout": layout,
        "headline": headline,
        "body": body,
        "purpose": purpose,
        "startRatio": round(start_ratio, 3),
        "durationSeconds": round(duration_seconds, 2),
        "motionPreset": motion_preset,
    }


def _get_visual_plan(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT plan_json FROM visual_plans WHERE script_id = ?",
            (script_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(str(row["plan_json"]))


def _save_visual_plan(script_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    plan = {**plan, "scriptId": script_id, "updatedAt": _now()}
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO visual_plans(script_id, plan_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                plan_json = excluded.plan_json,
                updated_at = excluded.updated_at
            """,
            (script_id, json.dumps(plan, ensure_ascii=False), plan["updatedAt"]),
        )
        conn.commit()
    finally:
        conn.close()
    return plan


def _video_slide_output_dir(script_id: str) -> Path:
    """Mantem os arquivos de preview fora do caminho controlado pelo usuario."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", script_id).strip("-") or "script"
    digest = hashlib.sha256(script_id.encode("utf-8")).hexdigest()[:12]
    return VIDEO_SLIDE_OUTPUTS / f"{safe_id}-{digest}"


def _normalize_visual_plan_for_render(script_id: str, visual_plan: dict[str, Any]) -> dict[str, Any]:
    """Garante N cenas = N-1 apoios antes de desenhar previews locais."""
    scene_plan = _scene_plan(script_id)
    if not scene_plan or not scene_plan.get("scenes"):
        return visual_plan
    submitted: dict[str, dict[str, Any]] = {}
    for item in visual_plan.get("scenes") or []:
        if not isinstance(item, dict):
            continue
        scene_id = str(item.get("sceneId") or "")
        visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
        submitted[scene_id] = visual
    scene_count = len(scene_plan["scenes"])
    visual_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scene_plan["scenes"]):
        visual_scenes.append(
            {
                "sceneId": scene["id"],
                "visual": _normalize_video_visual(
                    submitted.get(str(scene["id"]), {}),
                    scene=scene,
                    index=index,
                    scene_count=scene_count,
                    strict_required=True,
                ),
            }
        )
    return {
        **visual_plan,
        "scriptId": script_id,
        "designSystemVersion": str(
            visual_plan.get("designSystemVersion") or VIDEO_VISUAL_DESIGN_SYSTEM_VERSION
        ),
        "scenes": visual_scenes,
    }


def _get_video_slide_render(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT render_json FROM video_slide_renders WHERE script_id = ?",
            (script_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(str(row["render_json"]))


def _save_video_slide_render(script_id: str, render: dict[str, Any]) -> dict[str, Any]:
    saved = {**render, "scriptId": script_id, "updatedAt": _now()}
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO video_slide_renders(script_id, render_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                render_json = excluded.render_json,
                updated_at = excluded.updated_at
            """,
            (script_id, json.dumps(saved, ensure_ascii=False), saved["updatedAt"]),
        )
        conn.commit()
    finally:
        conn.close()
    return saved


def _video_slide_public_render(script_id: str, render: dict[str, Any] | None) -> dict[str, Any] | None:
    if not render:
        return None
    public = {**render, "assets": []}
    for asset in render.get("assets") or []:
        item = dict(asset)
        filename = str(item.get("assetPath") or "")
        if filename:
            item["url"] = (
                f"/api/scripts/{quote(script_id, safe='')}/video-slides/"
                f"{quote(filename, safe='')}"
            )
        public["assets"].append(item)
    return public


def _composed_video_output_dir(script_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", script_id).strip("-") or "script"
    digest = hashlib.sha256(script_id.encode("utf-8")).hexdigest()[:12]
    return COMPOSED_VIDEO_OUTPUTS / f"{safe_id}-{digest}"


def _local_output_path(raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = ROOT / path
    try:
        resolved = path.resolve()
        root = ROOT.resolve()
    except OSError:
        return None
    if resolved == root or root not in resolved.parents:
        return None
    return resolved if resolved.is_file() else None


def _probe_video_duration(path: Path) -> float:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr or "Não foi possível medir a duração do vídeo.")
    try:
        return float(json.loads(process.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("FFprobe não retornou uma duração válida.") from exc


def _copy_or_download_video(job: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    local_path = _local_output_path(job.get("outputPath"))
    if local_path:
        shutil.copyfile(local_path, destination)
        return destination
    video_url = str(job.get("remoteVideoUrl") or job.get("videoUrl") or "")
    parsed = urlparse(video_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (hostname == "heygen.ai" or hostname.endswith(".heygen.ai")):
        raise HTTPException(status_code=409, detail=f"Cena {job.get('sceneId') or job.get('id')} sem MP4 disponível.")
    try:
        with requests.get(video_url, stream=True, timeout=(15, 300)) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Não foi possível baixar uma cena pronta.") from exc
    return destination


def _video_archive_destination(job: dict[str, Any]) -> Path:
    try:
        script = _find_script(str(job.get("scriptId") or ""))
        title = str(script.get("titulo") or "video-produzido")
    except HTTPException:
        title = "video-produzido"
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "-", _norm(title)).strip("-")
    safe_job_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(job.get("id") or "video")).strip("-")
    return PRODUCED_VIDEO_OUTPUTS / f"{safe_title or 'video-produzido'}--{safe_job_id or 'video'}.mp4"


def _archive_completed_video(job: dict[str, Any]) -> dict[str, Any]:
    """Materializa o MP4 final em content/videos sem transformar falha de cópia em falha HeyGen."""
    if job.get("status") != "pronto" or job.get("isScene"):
        return job

    local_url = f"/api/videos/{quote(str(job.get('id') or ''), safe='')}/file"
    existing = _local_output_path(job.get("outputPath"))
    current_url = str(job.get("videoUrl") or "")
    if existing:
        if current_url.startswith("https://"):
            job["remoteVideoUrl"] = current_url
        job["localVideoUrl"] = local_url
        job["videoUrl"] = local_url
        job.pop("archiveWarning", None)
        return job

    remote_url = str(job.get("remoteVideoUrl") or current_url)
    parsed = urlparse(remote_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "heygen.ai" or hostname.endswith(".heygen.ai")
    ):
        return job

    destination = _video_archive_destination(job)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".part")
    try:
        with requests.get(remote_url, stream=True, timeout=(15, 300)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(destination)
        job["outputPath"] = str(destination.relative_to(ROOT))
        job["remoteVideoUrl"] = remote_url
        job["localVideoUrl"] = local_url
        job["videoUrl"] = local_url
        job.pop("archiveWarning", None)
        LOGGER.info("Completed video archived locally: job_id=%s path=%s", job.get("id"), destination)
    except (OSError, requests.RequestException) as exc:
        temporary.unlink(missing_ok=True)
        job["archiveWarning"] = "O vídeo está pronto, mas ainda não foi salvo em content/videos."
        LOGGER.warning("Completed video archive failed: job_id=%s detail=%s", job.get("id"), exc)
    return job


def _scene_job_batch_id(job: dict[str, Any]) -> str | None:
    explicit = str(job.get("sceneBatchId") or "").strip()
    if explicit:
        return explicit
    idempotency_key = str(job.get("idempotencyKey") or "")
    prefix = f"scene-video:{job.get('scriptId')}:{job.get('sceneId')}:"
    if idempotency_key.startswith(prefix):
        return idempotency_key[len(prefix) :] or None
    return None


def _scene_jobs_ready(script_id: str, scene_plan: dict[str, Any]) -> list[dict[str, Any]] | None:
    jobs = [job for job in _load_video_jobs() if job.get("scriptId") == script_id and job.get("isScene")]
    scenes = list(scene_plan.get("scenes") or [])
    expected_avatar_by_scene = {
        str(scene.get("id") or ""): str(scene.get("avatarId") or "")
        for scene in scenes
    }
    ready_by_batch: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for job in jobs:
        if job.get("status") != "pronto":
            continue
        scene_id = str(job.get("sceneId") or "")
        if scene_id not in expected_avatar_by_scene:
            continue
        expected_avatar = expected_avatar_by_scene[scene_id]
        actual_avatar = str((job.get("productionSettings") or {}).get("avatarId") or "")
        if expected_avatar and actual_avatar and expected_avatar != actual_avatar:
            continue
        batch_id = _scene_job_batch_id(job) or "__legacy__"
        ready_by_batch.setdefault(batch_id, {}).setdefault(scene_id, []).append(job)

    complete_batches: list[tuple[str, list[dict[str, Any]]]] = []
    for batch_id, ready_by_scene in ready_by_batch.items():
        ordered: list[dict[str, Any]] = []
        for scene in scenes:
            candidates = sorted(
                ready_by_scene.get(str(scene.get("id") or ""), []),
                key=lambda item: str(item.get("atualizadoEm") or item.get("criadoEm") or ""),
                reverse=True,
            )
            if not candidates:
                break
            ordered.append(candidates[0])
        if len(ordered) == len(scenes):
            newest = max(
                str(job.get("atualizadoEm") or job.get("criadoEm") or "")
                for job in ordered
            )
            complete_batches.append((newest, ordered))
    if not complete_batches:
        return None
    complete_batches.sort(key=lambda item: item[0], reverse=True)
    return complete_batches[0][1]


def _visual_asset_by_scene(script_id: str, visual_plan: dict[str, Any]) -> dict[str, Path]:
    render = _get_video_slide_render(script_id)
    if not render or not render.get("assets"):
        render = _save_video_slide_render(script_id, render_video_slides(_video_slide_output_dir(script_id), visual_plan))
    assets: dict[str, Path] = {}
    root = _video_slide_output_dir(script_id).resolve()
    for asset in render.get("assets") or []:
        filename = str(asset.get("assetPath") or "")
        if not filename:
            continue
        path = (root / filename).resolve()
        if root in path.parents and path.is_file():
            assets[str(asset.get("sceneId") or "")] = path
    return assets


def _composed_video_file_response(job: dict[str, Any], *, download: bool) -> FileResponse:
    path = _local_output_path(job.get("outputPath"))
    if not path:
        raise HTTPException(status_code=404, detail="Arquivo composto não encontrado.")
    try:
        script = _find_script(str(job.get("scriptId") or ""))
        base_name = str(script.get("titulo") or "video-final")
    except HTTPException:
        base_name = "video-final"
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", _norm(base_name)).strip("-") or "video-final"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{safe_name}.mp4" if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


def _compose_final_video_if_ready(script_id: str, *, raise_when_not_ready: bool = False) -> dict[str, Any] | None:
    scene_plan = _refresh_scene_plan_avatar_bindings(script_id)
    if not scene_plan or not scene_plan.get("scenes"):
        if raise_when_not_ready:
            raise HTTPException(status_code=409, detail="Salve o Scene Plan antes de compor o vídeo final.")
        return None
    scene_jobs = _scene_jobs_ready(script_id, scene_plan)
    if scene_jobs is None:
        if raise_when_not_ready:
            raise HTTPException(status_code=409, detail="Todas as cenas precisam estar prontas antes da composição final.")
        return None
    visual_plan = _get_visual_plan(script_id)
    scene_count = len(scene_plan["scenes"])
    if scene_count > 1 and (not visual_plan or not visual_plan.get("scenes")):
        if raise_when_not_ready:
            raise HTTPException(status_code=409, detail="Salve o Visual Plan antes de compor o vídeo final.")
        return None
    visual_plan = visual_plan or {"scenes": []}
    production_profile = _production_profile(script_id) or {}
    music_track_id = str(production_profile.get("musicTrackId") or "").strip() or None
    music_track = _music_track(music_track_id)
    music_volume = float(production_profile.get("musicVolume") or 0.12)
    music_path = _music_track_path(music_track_id) if music_track else None
    required_supports = _required_visual_support_count(scene_count)
    visual_by_scene = {
        str(item.get("sceneId")): item.get("visual")
        for item in visual_plan.get("scenes") or []
        if isinstance(item, dict) and isinstance(item.get("visual"), dict)
    }
    asset_by_scene = _visual_asset_by_scene(script_id, visual_plan) if required_supports else {}
    output_root = _composed_video_output_dir(script_id)
    source_ids = [str(job["id"]) for job in scene_jobs]
    composition_key = hashlib.sha256(
        json.dumps(
            {
                "scriptId": script_id,
                "sources": source_ids,
                "visualPlanUpdatedAt": visual_plan.get("updatedAt"),
                "requiredSupportSlides": required_supports,
                "musicTrackId": music_track_id,
                "musicVolume": music_volume if music_track_id else None,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:12]
    job_id = f"vc-{composition_key}"
    existing = _job_store().get("video", job_id)
    if existing and existing.get("status") == "pronto" and _local_output_path(existing.get("outputPath")):
        return existing

    now = _now()
    output_path = output_root / f"{job_id}.mp4"
    relative_output = str(output_path.relative_to(ROOT))
    job = existing or {
        "id": job_id,
        "scriptId": script_id,
        "provider": "local",
        "progresso": 0,
        "criadoEm": now,
        "sourceSceneJobs": source_ids,
        "sceneCount": scene_count,
        "visualCount": required_supports,
        "isComposed": True,
    }
    job.update(
        {
            "status": "processando",
            "progresso": 40,
            "atualizadoEm": now,
            "outputPath": relative_output,
            "videoUrl": f"/api/videos/{quote(job_id, safe='')}/file",
            "sourceSceneJobs": source_ids,
            "sceneCount": scene_count,
            "visualCount": required_supports,
            "isComposed": True,
            "submissionState": "local_composing",
        }
    )
    _job_store().upsert("video", job, idempotency_key=f"compose-final:{composition_key}")
    try:
        source_root = output_root / "sources" / job_id
        composition_scenes: list[CompositionScene] = []
        total_duration = 0.0
        for index, (scene, scene_job) in enumerate(zip(scene_plan["scenes"], scene_jobs, strict=True), start=1):
            scene_id = str(scene["id"])
            scene_path = _copy_or_download_video(scene_job, source_root / f"{index:02d}-{scene_id}.mp4")
            duration = _probe_video_duration(scene_path)
            total_duration += duration
            visual = visual_by_scene.get(scene_id) or {}
            slide_path = asset_by_scene.get(scene_id)
            slide_duration = float(visual.get("durationSeconds") or 0) if isinstance(visual, dict) else 0.0
            has_explicit_timing = isinstance(visual, dict) and "startRatio" in visual and "durationSeconds" in visual
            if index <= required_supports:
                slide_duration = min(max(1.0, slide_duration or 3.0), 5.0, max(0.3, duration))
                start_seconds = max(0.0, duration - slide_duration)
            elif has_explicit_timing:
                start_ratio = float(visual.get("startRatio") or 0.65)
                start_ratio = max(0.15, min(0.70, start_ratio))
                start_seconds = max(0.0, min(duration * start_ratio, max(0.0, duration - 0.5)))
                usable_duration = max(0.3, duration - start_seconds)
                slide_duration = min(max(1.0, slide_duration or 2.5), 5.0, usable_duration)
            else:
                slide_duration = min(3.0, max(1.0, duration))
                start_seconds = max(0.0, duration - slide_duration)
            if index <= required_supports and not slide_path:
                raise HTTPException(status_code=409, detail=f"Apoio visual da cena {index} não foi renderizado.")
            composition_scenes.append(
                CompositionScene(
                    scene_id=scene_id,
                    video_path=scene_path,
                    slide_path=slide_path if index <= required_supports else None,
                    slide_mode="during",
                    visual_start_seconds=start_seconds,
                    slide_duration_seconds=slide_duration,
                    visual_animation=str(visual.get("motionPreset") or "fade") if isinstance(visual, dict) else "fade",
                )
            )
        manifest = compose_video(
            composition_scenes,
            output_path,
            background_music_path=music_path,
            background_music_volume=music_volume,
        )
        final_duration = _probe_video_duration(output_path)
        job.update(
            {
                "status": "pronto",
                "progresso": 100,
                "submissionState": "completed",
                "atualizadoEm": _now(),
                "duracaoSegundos": round(final_duration or total_duration, 2),
                "composition": manifest,
                "backgroundMusic": _music_track_response(music_track) | {"volume": music_volume} if music_track else None,
            }
        )
    except Exception as exc:
        job.update(
            {
                "status": "erro",
                "progresso": 0,
                "erro": str(exc.detail) if isinstance(exc, HTTPException) else str(exc),
                "submissionState": "local_failed",
                "atualizadoEm": _now(),
            }
        )
        _job_store().upsert("video", job, idempotency_key=f"compose-final:{composition_key}")
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=503, detail=f"Não foi possível compor o vídeo final: {exc}") from exc
    _job_store().upsert("video", job, idempotency_key=f"compose-final:{composition_key}")
    return job


def _get_visual_pack(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT pack_json FROM visual_packs WHERE script_id = ?",
            (script_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(str(row["pack_json"]))


def _save_visual_pack(script_id: str, pack: dict[str, Any]) -> dict[str, Any]:
    source_avatar_id = str(pack.get("sourceAvatarId") or "")
    if not source_avatar_id:
        raise HTTPException(status_code=422, detail="Pack visual sem avatar de origem.")
    pack["updatedAt"] = _now()
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO visual_packs(script_id, pack_json, source_avatar_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                pack_json = excluded.pack_json,
                source_avatar_id = excluded.source_avatar_id,
                updated_at = excluded.updated_at
            """,
            (script_id, json.dumps(pack, ensure_ascii=False), source_avatar_id, pack["updatedAt"]),
        )
        conn.commit()
    finally:
        conn.close()
    return pack


def _ai_cache_key(operation: str, payload: Any) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ai_cache_get(operation: str, payload: Any, max_age_seconds: int = 86400) -> dict[str, Any] | None:
    key = _ai_cache_key(operation, payload)
    conn = _ai_db()
    try:
        row = conn.execute(
            "SELECT response_json, created_at FROM ai_response_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > max_age_seconds:
            conn.execute("DELETE FROM ai_response_cache WHERE cache_key = ?", (key,))
            conn.commit()
            return None
        return json.loads(str(row["response_json"]))
    finally:
        conn.close()


def _ai_cache_put(operation: str, payload: Any, response: dict[str, Any]) -> None:
    key = _ai_cache_key(operation, payload)
    conn = _ai_db()
    try:
        conn.execute(
            """INSERT INTO ai_response_cache(cache_key, operation, response_json, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(cache_key) DO UPDATE SET response_json=excluded.response_json,
               created_at=excluded.created_at""",
            (key, operation, json.dumps(response, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def _record_anthropic_usage(operation: str, model: str, message: Any) -> None:
    """Persiste tokens retornados pelo Claude; falhas nunca entram como custo."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return

    def number(name: str) -> int:
        value = getattr(usage, name, 0)
        return int(value or 0) if isinstance(value, (int, float)) else 0

    input_tokens = number("input_tokens")
    output_tokens = number("output_tokens")
    cache_read_tokens = number("cache_read_input_tokens")
    cache_write_tokens = number("cache_creation_input_tokens")
    input_rate = float(os.getenv("ANTHROPIC_INPUT_COST_PER_MILLION_USD", "1"))
    output_rate = float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_MILLION_USD", "5"))
    cache_read_rate = float(os.getenv("ANTHROPIC_CACHE_READ_COST_PER_MILLION_USD", "0.1"))
    cache_write_rate = float(os.getenv("ANTHROPIC_CACHE_WRITE_COST_PER_MILLION_USD", "1.25"))
    cost = (
        input_tokens * input_rate
        + output_tokens * output_rate
        + cache_read_tokens * cache_read_rate
        + cache_write_tokens * cache_write_rate
    ) / 1_000_000
    conn = _ai_db()
    try:
        conn.execute(
            """INSERT INTO ai_usage(
                created_at, operation, model, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens, estimated_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), operation, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost),
        )
        conn.commit()
    finally:
        conn.close()


def _anthropic_usage_summary() -> dict[str, Any]:
    conn = _ai_db()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS calls,
                      COALESCE(SUM(input_tokens), 0) AS input_tokens,
                      COALESCE(SUM(output_tokens), 0) AS output_tokens,
                      COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                      COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                      COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                 FROM ai_usage"""
        ).fetchone()
        return {
            "calls": int(row["calls"]),
            "inputTokens": int(row["input_tokens"]),
            "outputTokens": int(row["output_tokens"]),
            "cacheReadTokens": int(row["cache_read_tokens"]),
            "cacheWriteTokens": int(row["cache_write_tokens"]),
            "estimatedCostUsd": round(float(row["estimated_cost_usd"]), 6),
        }
    finally:
        conn.close()


def _job_store() -> JobStore:
    return JobStore(
        OPERATIONAL_DB,
        legacy_video_path=VIDEO_JOBS,
        legacy_avatar_path=AVATAR_JOBS,
    )


def _load_video_jobs() -> list[dict[str, Any]]:
    return _job_store().list("video")


def _save_video_jobs(jobs: list[dict[str, Any]]) -> None:
    _job_store().replace("video", jobs)


def _reconcile_incomplete_video_jobs(
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 900,
) -> dict[str, int]:
    """Fecha reservas locais antigas sem supor que uma submissão remota falhou.

    Uma reserva que nunca entrou em `submitting` é segura para retry. Uma
    submissão interrompida permanece incerta e bloqueia duplicação até revisão.
    Nenhuma consulta externa é feita durante esta reconciliação.
    """

    current_time = now or datetime.now(timezone.utc)
    store = _job_store()
    result = {"failedSafe": 0, "submissionUncertain": 0}
    for job in store.list("video"):
        state = str(job.get("submissionState") or "")
        if state not in {"reserved", "submitting"}:
            continue
        raw_updated = str(job.get("atualizadoEm") or job.get("criadoEm") or "")
        try:
            updated = datetime.fromisoformat(raw_updated.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except ValueError:
            updated = datetime.fromtimestamp(0, timezone.utc)
        if (current_time - updated).total_seconds() < stale_after_seconds:
            continue

        job["status"] = "erro"
        job["progresso"] = 0
        job["atualizadoEm"] = current_time.isoformat()
        if state == "reserved":
            job["retrySafe"] = True
            job["submissionState"] = "failed_safe"
            job["erro"] = "Reserva local interrompida antes do envio; uma nova tentativa é segura."
            result["failedSafe"] += 1
        else:
            job["retrySafe"] = False
            job["submissionState"] = "submission_uncertain"
            job["erro"] = "Envio interrompido; confirme o estado remoto antes de tentar novamente."
            result["submissionUncertain"] += 1
        store.upsert("video", job)
    return result


def _load_avatar_jobs() -> list[dict[str, Any]]:
    return _job_store().list("avatar")


def _save_avatar_jobs(jobs: list[dict[str, Any]]) -> None:
    _job_store().replace("avatar", jobs)


def _migrate_video_job_script_ids(scripts: list[dict[str, Any]]) -> int:
    """Converte referencias posicionais antigas (s-0, s-1...) para IDs permanentes."""
    jobs = _load_video_jobs()
    changed = 0
    for job in jobs:
        match = re.fullmatch(r"s-(\d+)", str(job.get("scriptId") or ""))
        if not match:
            continue
        index = int(match.group(1))
        if 0 <= index < len(scripts):
            job["scriptId"] = scripts[index]["id"]
            changed += 1
    if changed:
        _save_video_jobs(jobs)
    return changed


def _heygen_cli_binary() -> str:
    command = shutil.which("heygen")
    if not command:
        local_command = Path.home() / ".local" / "bin" / "heygen"
        if local_command.is_file() and os.access(local_command, os.X_OK):
            command = str(local_command)
    if not command:
        raise HTTPException(
            status_code=503,
            detail=(
                "CLI do HeyGen nao encontrado. Instale-o e autentique a conta antes de enviar "
                "videos para producao."
            ),
        )
    return command


def _heygen_cli() -> str:
    command = _heygen_cli_binary()
    if not os.getenv("HEYGEN_API_KEY"):
        raise HTTPException(status_code=503, detail="Defina HEYGEN_API_KEY no arquivo .env.")
    return command


def _saved_provider_capabilities(provider: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            """SELECT capabilities_json, checked_at
               FROM provider_capabilities WHERE provider = ?""",
            (provider,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        capabilities = json.loads(str(row["capabilities_json"]))
    except json.JSONDecodeError:
        return None
    if not isinstance(capabilities, dict):
        return None
    capabilities["checkedAt"] = row["checked_at"]
    return capabilities


def _save_provider_capabilities(capabilities: dict[str, Any]) -> dict[str, Any]:
    saved = {**capabilities, "checkedAt": _now()}
    conn = _ai_db()
    try:
        conn.execute(
            """INSERT INTO provider_capabilities(
                   provider, cli_version, capabilities_version, capabilities_json, checked_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET
                   cli_version=excluded.cli_version,
                   capabilities_version=excluded.capabilities_version,
                   capabilities_json=excluded.capabilities_json,
                   checked_at=excluded.checked_at""",
            (
                saved["provider"],
                saved["cliVersion"],
                saved["capabilitiesVersion"],
                json.dumps(capabilities, ensure_ascii=False, sort_keys=True),
                saved["checkedAt"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return saved


def _heygen_capabilities(*, refresh: bool = False) -> dict[str, Any]:
    command = _heygen_cli_binary()
    try:
        current_cli_version = heygen_cli_version(command)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cached = _saved_provider_capabilities("heygen")
    if cached and not refresh and cached.get("cliVersion") == current_cli_version:
        try:
            checked_at = datetime.fromisoformat(str(cached.get("checkedAt") or ""))
            age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
        except ValueError:
            age_seconds = 86401
        if age_seconds <= 86400:
            return cached
    try:
        inspected = inspect_heygen_capabilities(command)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível validar as capacidades do HeyGen: {exc}",
        ) from exc
    return _save_provider_capabilities(inspected)


def _read_json_output(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    raw = (proc.stdout or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Resposta invalida do HeyGen: {raw[-300:]}") from exc
    return data if isinstance(data, dict) else {"data": data}


def _run_heygen_json(
    command: str,
    args: list[str],
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ai-video-creator-") as temporary:
        call = [command, *args]
        if payload is not None:
            request_file = Path(temporary) / "request.json"
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            call.extend(["--data", str(request_file)])
        try:
            proc = subprocess.run(
                call,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="HeyGen demorou demais para responder.") from exc
    if proc.returncode != 0:
        detail = proc.stderr or proc.stdout or "Falha na comunicacao com o HeyGen."
        raise HTTPException(status_code=502, detail=detail[-700:])
    return _read_json_output(proc)


def _find_value(value: Any, *keys: str) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) not in (None, ""):
                return value[key]
        for child in value.values():
            found = _find_value(child, *keys)
            if found not in (None, ""):
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_value(child, *keys)
            if found not in (None, ""):
                return found
    return None


def _job_status(payload: dict[str, Any]) -> tuple[str, int]:
    raw = str(_find_value(payload, "status", "state") or "").lower()
    if raw in {"completed", "complete", "success", "done"}:
        return "pronto", 100
    if raw in {"failed", "error", "cancelled", "canceled"}:
        return "erro", 0
    if raw in {"thinking", "generating", "processing", "in_progress"}:
        return "processando", 50
    return "fila", 0


def _script_text(script: dict[str, Any]) -> str:
    parts = [
        script.get("hook"),
        script.get("dorConflito"),
        script.get("explicacaoSimples"),
        script.get("virada"),
        script.get("cta"),
    ]
    return "\n\n".join(str(part).strip() for part in parts if str(part or "").strip())


def _strip_video_outros(text: str, selected_outro: str = "") -> str:
    return strip_known_outros(text, selected_outro)


def _video_prompt(
    script: dict[str, Any],
    *,
    duration_seconds: int = 45,
    speech_mode: str = "natural",
    captions: bool = True,
    optimize_pronunciation: bool = True,
    narration_text: str | None = None,
    outro_text: str = MANDATORY_VIDEO_OUTRO,
) -> str:
    texto = narration_text.strip() if narration_text and narration_text.strip() else _script_text(script)
    omit_outro = duration_seconds == 10
    selected_outro = "" if omit_outro else re.sub(r"\s+", " ", outro_text).strip() or MANDATORY_VIDEO_OUTRO
    if omit_outro:
        texto = _strip_video_outros(texto, outro_text)
    if optimize_pronunciation:
        texto = prepare_script_for_heygen_voice(texto)
    if selected_outro and selected_outro.lower() not in texto.lower():
        texto = f"{texto.rstrip()}\n{selected_outro}"

    ending_direction = (
        "Start speaking immediately and end on the hook's strongest point. Do not add a closing phrase, "
        "spoken call to action, greeting, intro sequence, or outro sequence."
        if omit_outro
        else (
            "End the spoken narration exactly once with: "
            f'"{selected_outro}" This must be the final sentence.'
        )
    )

    speech_directions = {
        "natural": (
            "Speak naturally and conversationally. You may make small transitions, "
            "but preserve the medical meaning of the script."
        ),
        "fiel": (
            "Follow the supplied script closely. Do not add claims, examples, "
            "or medical advice that are not in the script."
        ),
        "direto": (
            "Use concise, energetic delivery. Shorten transitions while preserving "
            "every essential message and medical caution."
        ),
    }
    opening_direction = (
        "Create a portrait 9:16 single-take talking-head clip in Brazilian Portuguese."
        if omit_outro
        else "Create a portrait educational video in Brazilian Portuguese for social media."
    )
    presenter_direction = (
        "Keep the selected presenter centered and visible for the entire clip in one continuous locked-camera shot."
        if omit_outro
        else "The selected presenter explains one health topic with a clear, calm and non-prescriptive tone."
    )
    script_direction = (
        "Speak ONLY the supplied Portuguese script, verbatim. Do not expand, explain, paraphrase, summarize, "
        "or add any words."
        if omit_outro
        else "Preserve the supplied script's facts and medical meaning."
    )
    visual_direction = (
        "Do not create multiple scenes, a visual narrative, music, B-roll, A-roll overlays, motion graphics, "
        "stock media, AI-generated media, transitions, cutaways, title cards, or a visual intro/outro. "
        "Use only the selected presenter. Preserve the selected avatar's existing background exactly as-is. "
        "Do not generate, select, replace, extend, or restyle the background. This project has exactly one A-roll scene."
        if omit_outro
        else (
            "Use minimal, clean styled visuals. Blue, black, and white as main colors. "
            "Leverage motion graphics as B-rolls and A-roll overlays."
        )
    )
    return "\n\n".join(
        [
            opening_direction,
            presenter_direction,
            "Do not mention medication doses, promise outcomes, or make sensational claims.",
            f"Target duration: approximately {duration_seconds} seconds. Do not pad with silence or pauses.",
            (
                "Treat the supplied script as the complete content plan, not as a timing constraint. "
                "Preserve every medical fact and caution. You may improve only brief transitions, without "
                "adding new claims. Let the narration determine the final duration and never fill time with silence."
            ),
            (
                "Deliver the supplied script verbatim with a natural cadence. Do not add transitions or filler words."
                if omit_outro
                else speech_directions.get(speech_mode, speech_directions["natural"])
            ),
            script_direction,
            (
                "Add clean, readable Brazilian Portuguese captions synchronized with the narration."
                if captions
                else "Do not add burned-in captions or subtitles."
            ),
            ending_direction,
            f"VOICE-OPTIMIZED SCRIPT (Portuguese):\n{texto}",
            visual_direction,
        ]
    )


def _int(value: Any) -> int:
    if value is None:
        return 0
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0


def _norm(value: Any) -> str:
    return (str(value or "")).strip().lower()


def _row_id(row: dict[str, Any], prefix: str, index: int) -> str:
    """Usa o ID persistido no Sheets e aceita snapshots antigos durante a migracao."""
    value = str(row.get("ID") or "").strip()
    return value or f"{prefix}-{index}"


def _prioridade(value: Any) -> str:
    v = _norm(value)
    if "alt" in v:
        return "alta"
    if "med" in v or "méd" in v:
        return "media"
    if "baix" in v:
        return "baixa"
    return "media"


def _risco(value: Any) -> str:
    v = _norm(value)
    if "alt" in v:
        return "alto"
    if "baix" in v:
        return "baixo"
    if "med" in v or "méd" in v:
        return "medio"
    return "medio"


def _familia(*campos: Any) -> str:
    blob = " ".join(_norm(c) for c in campos)
    if any(k in blob for k in ("mounjaro", "ozempic", "wegovy", "glp", "medicament", "remedio", "remédio")):
        return "medicamento"
    if any(k in blob for k in ("metabol", "insulin", "resistenc")):
        return "metabolismo"
    if any(k in blob for k in ("obesidad", "estigma", "peso")):
        return "obesidade"
    if any(k in blob for k in ("jejum", "habito", "hábito", "comportament", "compuls", "sono", "dieta")):
        return "comportamento"
    return "educativo"


def _canal(value: Any) -> str:
    v = _norm(value)
    if "tiktok" in v:
        return "tiktok"
    if "you" in v or "short" in v:
        return "youtube_shorts"
    return "instagram"


def _iso(value: Any) -> str:
    """Aceita datas comuns do Sheets; devolve ISO ou hoje se nao parsear."""
    from datetime import datetime, timezone

    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def _trend_status(value: Any) -> str:
    v = _norm(value)
    if "descart" in v or "rejeit" in v:
        return "descartado"
    if "anali" in v or "análi" in v or "andament" in v or "ideia" in v:
        return "em_analise"
    return "novo"


def _link(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw if raw.lower().startswith("http") else None


def _idea_status(value: Any) -> str:
    v = _norm(value)
    if "aprov" in v or "gerad" in v:
        return "aprovado"
    if "descart" in v or "rejeit" in v:
        return "descartado"
    if "anali" in v or "análi" in v:
        return "em_analise"
    return "novo"


def _script_status(value: Any) -> str:
    v = _norm(value)
    if "aprov" in v or "pronto" in v:
        return "aprovado_clinicamente"
    if "rejeit" in v or "arquiv" in v:
        return "rejeitado"
    if "revis" in v or "edi" in v:
        return "em_revisao"
    return "aguardando_validacao"


def _post_status(value: Any) -> str:
    v = _norm(value)
    if "public" in v:
        return "publicado"
    if "agend" in v:
        return "agendado"
    return "pendente"




# --------------------------------------------------------------------------- #
# Mapeadores por aba
# --------------------------------------------------------------------------- #
def map_trends(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": _row_id(r, "t", i),
                "titulo": r.get("Tema") or r.get("Sinal de tendência") or "Tendencia",
                "subtema": r.get("Subtema") or None,
                "sinal": r.get("Sinal de tendência") or None,
                "dorPublico": r.get("Dor do público") or None,
                "link": _link(r.get("Link referência")),
                "fonte": r.get("Fonte") or "Google Sheets",
                "potencial": min(_int(r.get("Potencial Viral")), 10),
                "volume": 0,  # radar real nao tem volume; mantido por compat com seeds
                "familia": _familia(r.get("Tema"), r.get("Subtema")),
                "risco": "medio",  # radar real nao tem risco; nao exibido na tabela
                "prioridade": _prioridade(r.get("Prioridade")),
                "status": _trend_status(r.get("Status")),
                "criadoEm": _iso(r.get("Data")),
                "notas": r.get("Observações") or None,
            }
        )
    return out


def map_ideas(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": _row_id(r, "i", i),
                "trendId": r.get("Trend ID") or None,
                "titulo": r.get("Tema") or r.get("Hook") or "Ideia",
                "familia": _familia(r.get("Tema"), r.get("Tipo")),
                "hook": r.get("Hook") or "",
                "angulo": r.get("Ângulo") or "",
                "tipo": r.get("Tipo") or None,
                "publicoDor": r.get("Público/Dor") or None,
                "cta": r.get("CTA") or "",
                "linkOrigem": _link(r.get("Link origem")),
                "observacaoCompliance": r.get("Observações") or "",
                "prioridade": _prioridade(r.get("Prioridade")),
                "status": _idea_status(r.get("Status")),
                "criadoEm": _iso(r.get("Criado em") or r.get("Data")),
            }
        )
    return out


def map_scripts(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": _row_id(r, "s", i),
                "ideaId": r.get("Idea ID") or None,
                "categoria": _familia(r.get("Categoria"), r.get("Tema")),
                "tema": r.get("Tema") or "",
                "titulo": r.get("Título") or r.get("Tema") or "Roteiro",
                "hook": r.get("Hook") or "",
                "dorConflito": r.get("Dor/Conflito") or "",
                "explicacaoSimples": r.get("Explicação simples") or "",
                "virada": r.get("Virada/Provocação") or "",
                "cta": r.get("CTA") or "",
                "cuidadosMedicos": r.get("Cuidados médicos") or "",
                "risco": _risco(r.get("Risco")),
                "prioridade": "media",
                "formatoSugerido": r.get("Formato sugerido") or "Reels",
                "aprovador": r.get("Aprovador") or None,
                "link": _link(r.get("Link doc/video")),
                "status": _script_status(r.get("Status")),
                "criadoEm": _iso(r.get("Criado em") or r.get("Data")),
                "validadoEm": _iso(r.get("Data aprovação")) if r.get("Data aprovação") else None,
                "editorialTone": r.get("Tom editorial") or None,
                "textoFalado": r.get("Texto falado") or "",
                "outroText": r.get("Frase final") or MANDATORY_VIDEO_OUTRO,
                "generationProvider": r.get("Gerado por") or None,
                "generationFlowVersion": r.get("Versão do fluxo") or None,
            }
        )
    return out


def map_calendar(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": _row_id(r, "p", i),
                "titulo": r.get("Título/Hook") or r.get("Tema") or "Post",
                "tema": r.get("Tema") or None,
                "formato": r.get("Formato") or None,
                "responsavel": r.get("Responsável") or None,
                "link": _link(r.get("Link post")),
                "dataAgendada": _iso(r.get("Data publicação")),
                "canal": _canal(r.get("Canal")),
                "status": _post_status(r.get("Status")),
                "scriptId": r.get("Roteiro ID") or None,
                "videoJobId": r.get("Video Job ID") or None,
                "publicadoEm": _iso(r.get("Publicado em")) if r.get("Publicado em") else None,
            }
        )
    return out


def map_performance(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": f"m-{i}",
                "postId": f"perf-{i}",
                "tema": r.get("Tema") or None,
                "canal": _canal(r.get("Canal")),
                "views": _int(r.get("Views")),
                "likes": 0,
                "retencao": _int(r.get("Retenção %")),
                "comments": _int(r.get("Comentários")),
                "shares": _int(r.get("Compartilhamentos")),
                "saves": _int(r.get("Salvamentos")),
                "novosSeguidores": _int(r.get("Novos seguidores")),
                "cliques": _int(r.get("Cliques")),
                "leads": _int(r.get("Leads")),
                "nota": r.get("Nota") or None,
                "aprendizado": r.get("Aprendizado") or None,
                "link": _link(r.get("Link post")),
                "coletadoEm": _iso(r.get("Data")),
            }
        )
    return out


def _attach_calendar_links(
    performance: list[dict[str, Any]], calendar_posts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cruza Performance com Calendario pelo 'Link post' (coluna presente nas duas
    abas hoje). Nao exige mudar o schema da planilha: linhas de Performance sem
    link preenchido simplesmente ficam sem o cruzamento."""
    by_link: dict[str, dict[str, Any]] = {}
    for post in calendar_posts:
        link = (post.get("link") or "").strip()
        if link and link not in by_link:
            by_link[link] = post
    for metric in performance:
        link = (metric.get("link") or "").strip()
        match = by_link.get(link) if link else None
        metric["calendarPostId"] = match.get("id") if match else None
        metric["scriptId"] = match.get("scriptId") if match else None
        metric["videoJobId"] = match.get("videoJobId") if match else None
        metric["formatoSugerido"] = match.get("formato") if match else None
    return performance


DEFAULT_SETTINGS = {
    "temasPrioritarios": [
        "obesidade", "GLP-1", "Mounjaro", "Ozempic", "Wegovy",
        "dieta", "metabolismo", "comportamento alimentar",
    ],
    "palavrasProibidas": [
        "cura", "milagre", "garantido", "sem esforco",
        "resultado certo", "emagrece rapido", "prometo",
    ],
    "radar": {
        "termosExtras": ["atividade fisica", "sono", "compulsao alimentar"],
        "fontes": ["google_news", "gdelt", "pubmed", "reddit", "serpapi"],
        "periodo": "semana",
        "limitePorBusca": 20,
        "potencialMinimo": 1,
    },
    # Integracoes reais existem no backend, mas so ligar quando testadas.
    "integracoes": {"heygen": False, "meta": False, "googleSheets": True},
    "heygen": {"defaultAvatarId": None, "favoriteAvatarIds": []},
}


# Fonte unica das regras medicas de compliance. O backend usa isto para
# apontar alertas de revisao (_pack_compliance); o frontend recebe a mesma
# lista via /api/state e usa para o preview em tempo real (web/src/lib/compliance.ts),
# evitando que as duas pontas fiquem com regras divergentes.
MEDICAL_COMPLIANCE_RULES: list[dict[str, str]] = [
    {
        "id": "dose",
        "pattern": r"\b\d+\s?(mg|mcg|ml|g)\b|\bdose\b|\bcomprimid|\bampola",
        "titulo": "Possível menção de dose ou formulação",
        "detalhe": "Não citar dose, mg ou formato de administração. Reforçar avaliação médica.",
        "severidade": "alta",
    },
    {
        "id": "prescrever",
        "pattern": r"\b(prescreva|tome|use|aumente|reduza|pare|comece)\b",
        "titulo": "Possível linguagem prescritiva",
        "detalhe": "Não prescrever pelo vídeo. Reforçar consulta individual.",
        "severidade": "alta",
    },
    {
        "id": "sensacional",
        "pattern": r"\b(chocante|inacreditavel|voce nao vai acreditar|surreal|absurdo)\b",
        "titulo": "Tom sensacionalista",
        "detalhe": "Evitar sensacionalismo. Manter tom educativo.",
        "severidade": "media",
    },
    {
        "id": "autodx",
        "pattern": r"\bvoce (esta|tem)\s+(diabetes|resistencia|obesidade)\b",
        "titulo": "Sugestão de autodiagnóstico",
        "detalhe": "Não induzir autodiagnóstico. Reforçar avaliação clínica.",
        "severidade": "media",
    },
]


class RadarSettingsIn(BaseModel):
    termosExtras: list[str] = Field(default_factory=list, max_length=30)
    fontes: list[Literal["google_news", "gdelt", "pubmed", "reddit", "serpapi"]] = Field(
        default_factory=lambda: ["google_news", "gdelt", "pubmed", "reddit", "serpapi"],
        max_length=5,
    )
    periodo: Literal["dia", "semana", "quinzena", "mes"] = "semana"
    limitePorBusca: int = Field(default=20, ge=1, le=50)
    potencialMinimo: int = Field(default=1, ge=1, le=10)


class IntegrationsSettingsIn(BaseModel):
    heygen: bool = False
    meta: bool = False
    googleSheets: bool = True


class HeyGenSettingsIn(BaseModel):
    defaultAvatarId: str | None = Field(default=None, max_length=120)
    favoriteAvatarIds: list[str] = Field(default_factory=list, max_length=100)


class AppSettingsIn(BaseModel):
    temasPrioritarios: list[str] = Field(default_factory=list, max_length=80)
    palavrasProibidas: list[str] = Field(default_factory=list, max_length=120)
    radar: RadarSettingsIn = Field(default_factory=RadarSettingsIn)
    integracoes: IntegrationsSettingsIn = Field(default_factory=IntegrationsSettingsIn)
    heygen: HeyGenSettingsIn = Field(default_factory=HeyGenSettingsIn)


class InstagramPublishIn(BaseModel):
    videoJobId: str = Field(min_length=3, max_length=120)
    mediaType: Literal["REELS", "STORIES"] = "REELS"
    caption: str = Field(default="", max_length=2200)
    shareToFeed: bool = True


def _clean_string_list(values: list[str], *, limit: int = 80) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = re.sub(r"\s+", " ", str(value)).strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item[:120])
        if len(cleaned) >= limit:
            break
    return cleaned


def _merge_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if not isinstance(raw, dict):
        return settings
    settings["temasPrioritarios"] = _clean_string_list(
        raw.get("temasPrioritarios") or settings["temasPrioritarios"],
        limit=80,
    )
    settings["palavrasProibidas"] = _clean_string_list(
        raw.get("palavrasProibidas") or settings["palavrasProibidas"],
        limit=120,
    )
    radar = raw.get("radar") if isinstance(raw.get("radar"), dict) else {}
    settings["radar"] = {
        **settings["radar"],
        **{key: radar[key] for key in ["periodo", "limitePorBusca", "potencialMinimo"] if key in radar},
    }
    settings["radar"]["termosExtras"] = _clean_string_list(
        radar.get("termosExtras") or settings["radar"]["termosExtras"],
        limit=30,
    )
    allowed_sources = {"google_news", "gdelt", "pubmed", "reddit", "serpapi"}
    configured_sources = [
        source for source in radar.get("fontes", settings["radar"]["fontes"]) if source in allowed_sources
    ]
    settings["radar"]["fontes"] = configured_sources or settings["radar"]["fontes"]
    integrations = raw.get("integracoes") if isinstance(raw.get("integracoes"), dict) else {}
    settings["integracoes"] = {
        "heygen": bool(integrations.get("heygen", settings["integracoes"]["heygen"])),
        "meta": bool(integrations.get("meta", settings["integracoes"]["meta"])),
        "googleSheets": bool(
            integrations.get("googleSheets", settings["integracoes"]["googleSheets"])
        ),
    }
    heygen = raw.get("heygen") if isinstance(raw.get("heygen"), dict) else {}
    default_avatar_id = str(heygen.get("defaultAvatarId") or "").strip()
    settings["heygen"] = {
        "defaultAvatarId": default_avatar_id[:120] or None,
        "favoriteAvatarIds": _clean_string_list(
            heygen.get("favoriteAvatarIds") or [],
            limit=100,
        ),
    }
    return settings


def _load_settings() -> dict[str, Any]:
    if not APP_SETTINGS.exists():
        return _merge_settings()
    try:
        return _merge_settings(json.loads(APP_SETTINGS.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return _merge_settings()


def _save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    APP_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    merged = _merge_settings(settings)
    temporary = APP_SETTINGS.with_suffix(".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(APP_SETTINGS)
    return merged


HEYGEN_CATALOG = {
    "voices": [
        {"id": "33a98f732fe144d9a40f5cf33a7e95ec", "name": "drguilhermeia", "gender": "male"},
    ],
}


def _load_heygen_avatar_cache() -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    try:
        cached = json.loads(HEYGEN_AVATAR_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    groups = cached.get("groups")
    looks = cached.get("looks")
    if not isinstance(groups, list) or not isinstance(looks, list):
        return None
    return groups, looks


def _save_heygen_avatar_cache(groups: list[dict[str, Any]], looks: list[dict[str, Any]]) -> None:
    HEYGEN_AVATAR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    HEYGEN_AVATAR_CACHE.write_text(
        json.dumps(
            {"updatedAt": _now(), "groups": groups, "looks": looks},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _private_avatar_library(
    command: str | None = None,
    *,
    allow_cache: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Lista identidades privadas e todos os visuais de cada identidade.

    O terceiro valor (from_cache) indica se algum dado veio do cache local em
    vez de uma consulta ao vivo na HeyGen. Chamadas que vao gastar producao
    real (ex.: criar video) devem passar allow_cache=False para nunca validar
    o avatar escolhido contra uma lista desatualizada."""
    if command is None:
        try:
            command = _heygen_cli()
        except HTTPException:
            cached = _load_heygen_avatar_cache() if allow_cache else None
            if cached:
                return cached[0], cached[1], True
            raise
    try:
        response = _run_heygen_json(
            command,
            ["avatar", "list", "--ownership", "private", "--limit", "50"],
            timeout=45,
        )
    except HTTPException:
        cached = _load_heygen_avatar_cache() if allow_cache else None
        if cached:
            return cached[0], cached[1], True
        raise
    groups = _find_value(response, "data")
    if not isinstance(groups, list):
        groups = []

    cached_lookup: dict[str, list[dict[str, Any]]] = {}
    if allow_cache:
        cached = _load_heygen_avatar_cache()
        if cached:
            _, cached_looks = cached
            for cached_look in cached_looks:
                if not isinstance(cached_look, dict):
                    continue
                cached_lookup.setdefault(str(cached_look.get("group_id") or ""), []).append(cached_look)

    looks: list[dict[str, Any]] = []
    used_cache_for_some_looks = False
    for group in groups:
        group_id = str(group.get("id") or "")
        if not group_id:
            continue
        try:
            look_response = _run_heygen_json(
                command,
                ["avatar", "looks", "list", "--group-id", group_id, "--limit", "50"],
                timeout=45,
            )
            group_looks = _find_value(look_response, "data")
        except HTTPException:
            group_looks = cached_lookup.get(group_id, [])
            if group_looks:
                used_cache_for_some_looks = True
        if not isinstance(group_looks, list):
            continue
        for raw_look in group_looks:
            if not isinstance(raw_look, dict):
                continue
            look = dict(raw_look)
            look["group_id"] = look.get("group_id") or group_id
            look["group_name"] = group.get("name") or "Identidade sem nome"
            looks.append(look)
    if looks:
        _save_heygen_avatar_cache(groups, looks)
        return groups, looks, used_cache_for_some_looks
    if allow_cache:
        cached = _load_heygen_avatar_cache()
        if cached:
            return cached[0], cached[1], True
    return groups, looks, False


def _heygen_default_avatar_id(avatars: list[dict[str, Any]]) -> str:
    allowed_ids = {str(avatar.get("id")) for avatar in avatars}
    saved_default = str(_load_settings().get("heygen", {}).get("defaultAvatarId") or "")
    if saved_default in allowed_ids:
        return saved_default
    environment_default = os.getenv("HEYGEN_DEFAULT_AVATAR_ID")
    if environment_default in allowed_ids:
        return environment_default
    if not avatars:
        raise HTTPException(status_code=503, detail="Nenhum avatar privado pronto foi encontrado.")
    return str(avatars[0]["id"])


def _heygen_default_voice_id() -> str:
    configured = os.getenv("HEYGEN_DEFAULT_VOICE_ID")
    allowed_ids = {voice["id"] for voice in HEYGEN_CATALOG["voices"]}
    if configured in allowed_ids:
        return configured
    return HEYGEN_CATALOG["voices"][0]["id"]


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    _job_store()
    return {
        "ok": True,
        "snapshot_exists": SNAPSHOT.exists(),
        "operational_db": OPERATIONAL_DB.exists(),
    }


@app.get("/api/instagram/status")
def instagram_status() -> dict:
    """Valida as credenciais Meta sem enviar ou alterar conteudo."""
    client = InstagramClient()
    if not client.is_configured:
        return {
            "configured": False,
            "connected": False,
            "account": None,
            "detail": "Configure META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID no backend.",
        }
    try:
        profile = client.profile()
    except (RuntimeError, requests.RequestException) as exc:
        return {
            "configured": True,
            "connected": False,
            "account": None,
            "detail": str(exc),
        }
    return {
        "configured": True,
        "connected": True,
        "account": {
            "id": profile.get("id"),
            "username": profile.get("username"),
            "name": profile.get("name"),
            "profilePictureUrl": profile.get("profile_picture_url"),
            "followersCount": profile.get("followers_count"),
            "mediaCount": profile.get("media_count"),
        },
        "detail": "Conta profissional conectada.",
    }


@app.post("/api/instagram/publish")
def instagram_publish(payload: InstagramPublishIn) -> dict:
    """Publica um video pronto como Reel ou Story depois da confirmacao na UI."""
    job = _job_store().get("video", payload.videoJobId)
    if not job:
        raise HTTPException(status_code=404, detail="Video nao encontrado.")
    if job.get("status") != "pronto":
        raise HTTPException(status_code=409, detail="O video precisa estar pronto antes de publicar.")
    video_url = str(job.get("videoUrl") or "")
    parsed = urlparse(video_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(
            status_code=409,
            detail="O Instagram exige uma URL HTTPS publica para buscar o video.",
        )

    client = InstagramClient()
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Configure META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID no backend.",
        )
    try:
        publication = client.publish_video(
            video_url,
            media_type=payload.mediaType,
            caption=payload.caption.strip(),
            share_to_feed=payload.shareToFeed,
        )
    except (RuntimeError, requests.RequestException) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    publication["publishedAt"] = _now()
    history = job.get("instagramPublications")
    if not isinstance(history, list):
        history = []
    job["instagramPublications"] = [*history, publication]
    job["atualizadoEm"] = _now()
    _job_store().upsert("video", job)
    return {"ok": True, "publication": publication, "job": job}


@app.get("/api/heygen/catalog")
def heygen_catalog() -> dict:
    """Catalogo de avatares e vozes privados disponiveis para producao."""
    _, looks, _from_cache = _private_avatar_library()
    catalog = build_catalog(looks, HEYGEN_CATALOG["voices"])
    settings = _load_settings().get("heygen", {})
    available_ids = {avatar["id"] for avatar in catalog["avatars"]}
    preferred_ids = [
        str(settings.get("defaultAvatarId") or ""),
        *[str(avatar_id) for avatar_id in settings.get("favoriteAvatarIds") or []],
    ]
    catalog["defaultAvatarId"] = next(
        (avatar_id for avatar_id in preferred_ids if avatar_id in available_ids),
        None,
    )
    catalog["defaultVoiceId"] = _heygen_default_voice_id()
    catalog["speechPresets"] = SPEECH_PRESETS
    catalog["generationModes"] = ["direct", "video_agent", "cinematic"]
    catalog["directDurations"] = sorted(DIRECT_VIDEO_DURATIONS)
    return catalog


@app.get("/api/heygen/avatars")
def heygen_avatars() -> dict:
    """Lista identidades privadas e todos os visuais criados na conta conectada."""
    groups, looks, from_cache = _private_avatar_library()
    return {
        "avatars": groups,
        "looks": looks,
        "jobs": _load_avatar_jobs(),
        "fromCache": from_cache,
    }


@app.get("/api/heygen/styles")
def heygen_styles(tag: str = "cinematic") -> dict:
    """Retorna estilos visuais oficiais disponiveis no Video Agent."""
    allowed_tags = {
        "cinematic",
        "retro-tech",
        "iconic-artist",
        "pop-culture",
        "handmade",
        "print",
    }
    selected_tag = tag if tag in allowed_tags else "cinematic"
    command = _heygen_cli()
    response = _run_heygen_json(
        command,
        ["video-agent", "styles", "list", "--tag", selected_tag, "--limit", "30"],
        timeout=45,
    )
    styles = _find_value(response, "data")
    return {"styles": styles if isinstance(styles, list) else [], "tag": selected_tag}


@app.get("/api/providers/heygen/capabilities")
def heygen_provider_capabilities(refresh: bool = False) -> dict:
    """Inspeciona contratos locais do CLI; não cria sessão nem consome créditos."""
    return {"ok": True, "capabilities": _heygen_capabilities(refresh=refresh)}


class AvatarMediaIn(BaseModel):
    name: str
    mimeType: str
    data: str


class AvatarCreateIn(BaseModel):
    name: str
    creationType: Literal["photo", "digital_twin", "prompt"]
    appearancePrompt: str = ""
    media: list[AvatarMediaIn] = Field(default_factory=list)
    cloneVoice: bool = False
    voiceSource: Literal["upload", "video"] = "upload"
    voiceMedia: AvatarMediaIn | None = None
    consentAccepted: bool = False


def _media_payload(
    media: AvatarMediaIn,
    *,
    allowed_mime_types: set[str],
    max_bytes: int = 32 * 1024 * 1024,
) -> dict[str, str]:
    decoded = _decode_avatar_media(
        media,
        allowed_mime_types=allowed_mime_types,
        max_bytes=max_bytes,
    )
    return {
        "type": "base64",
        "media_type": media.mimeType,
        "data": base64.b64encode(decoded).decode("ascii"),
    }


def _decode_avatar_media(
    media: AvatarMediaIn,
    *,
    allowed_mime_types: set[str],
    max_bytes: int,
) -> bytes:
    if media.mimeType not in allowed_mime_types:
        raise HTTPException(status_code=400, detail=f"Formato de arquivo nao aceito: {media.mimeType}.")
    try:
        decoded = base64.b64decode(media.data, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Arquivo invalido: {media.name}.") from exc
    if not decoded or len(decoded) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"O arquivo {media.name} deve ter ate {limit_mb} MB.",
        )
    return decoded


def _direct_upload_avatar_asset(
    command: str,
    media: AvatarMediaIn,
    content: bytes,
) -> dict[str, str]:
    upload = _run_heygen_json(
        command,
        ["asset", "direct-uploads", "create"],
        payload={
            "filename": media.name,
            "content_type": media.mimeType,
            "size_bytes": len(content),
        },
        timeout=45,
    )
    asset_id = _find_value(upload, "asset_id")
    upload_url = _find_value(upload, "upload_url")
    upload_headers = _find_value(upload, "upload_headers")
    if not asset_id or not upload_url:
        raise HTTPException(
            status_code=502,
            detail="HeyGen não retornou os dados para enviar o vídeo.",
        )
    headers = (
        {str(key): str(value) for key, value in upload_headers.items()}
        if isinstance(upload_headers, dict)
        else {}
    )
    try:
        response = requests.put(
            str(upload_url),
            data=content,
            headers=headers,
            timeout=300,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível enviar o vídeo ao armazenamento do HeyGen.",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"O armazenamento do HeyGen recusou o vídeo ({response.status_code}).",
        )
    completed = _run_heygen_json(
        command,
        ["asset", "complete", "create", str(asset_id)],
        payload={},
        timeout=60,
    )
    completed_asset_id = _find_value(completed, "asset_id") or asset_id
    return {"type": "asset_id", "asset_id": str(completed_asset_id)}


def _avatar_file_payload(
    command: str,
    media: AvatarMediaIn,
    *,
    allowed_mime_types: set[str],
    max_bytes: int = 30 * 1024 * 1024,
    inline_max_bytes: int = 16 * 1024 * 1024,
) -> dict[str, str]:
    content = _decode_avatar_media(
        media,
        allowed_mime_types=allowed_mime_types,
        max_bytes=max_bytes,
    )
    if len(content) <= inline_max_bytes:
        return {
            "type": "base64",
            "media_type": media.mimeType,
            "data": base64.b64encode(content).decode("ascii"),
        }
    return _direct_upload_avatar_asset(command, media, content)


def _voice_from_video(media: AvatarMediaIn) -> dict[str, str]:
    if media.mimeType not in {"video/mp4", "video/webm"}:
        raise HTTPException(status_code=400, detail="Envie um vídeo MP4 ou WebM com áudio.")
    try:
        video_bytes = base64.b64decode(media.data, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Arquivo inválido: {media.name}.") from exc
    if not video_bytes:
        raise HTTPException(status_code=400, detail="O vídeo selecionado está vazio.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(
            status_code=503,
            detail="FFmpeg não está disponível para extrair a voz do vídeo.",
        )

    suffix = ".webm" if media.mimeType == "video/webm" else ".mp4"
    with tempfile.TemporaryDirectory(prefix="avatar-voice-") as temporary:
        source = Path(temporary) / f"source{suffix}"
        output = Path(temporary) / "voice.wav"
        source.write_bytes(video_bytes)
        try:
            process = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-c:a",
                    "pcm_s16le",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                status_code=504,
                detail="A extração da voz demorou demais. Tente um vídeo menor.",
            ) from exc
        if process.returncode != 0 or not output.exists() or output.stat().st_size <= 44:
            raise HTTPException(
                status_code=400,
                detail="Não foi possível encontrar uma faixa de voz no vídeo selecionado.",
            )
        audio_bytes = output.read_bytes()

    if len(audio_bytes) > 32 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="A voz extraída ficou maior que 32 MB. Use um vídeo mais curto.",
        )
    return {
        "type": "base64",
        "media_type": "audio/x-wav",
        "data": base64.b64encode(audio_bytes).decode("ascii"),
    }


def _avatar_creation_metadata(response: dict[str, Any]) -> dict[str, Any]:
    """Extrai grupo e visual sem confundir os dois IDs da resposta v3."""
    data = response.get("data")
    data = data if isinstance(data, dict) else {}
    group = data.get("avatar_group")
    group = group if isinstance(group, dict) else {}
    item = data.get("avatar_item")
    item = item if isinstance(item, dict) else {}

    # Respostas antigas/fixtures retornam os campos diretamente em data.
    group_id = group.get("id") or data.get("group_id") or item.get("group_id")
    avatar_id = item.get("id") or (data.get("id") if not group else None)
    status = group.get("status") or item.get("status") or data.get("status")
    consent_status = group.get("consent_status") or data.get("consent_status")
    voice_id = (
        item.get("default_voice_id")
        or group.get("default_voice_id")
        or data.get("default_voice_id")
    )
    return {
        "groupId": str(group_id) if group_id else None,
        "avatarId": str(avatar_id) if avatar_id else None,
        "status": str(status) if status else None,
        "consentStatus": str(consent_status) if consent_status else None,
        "voiceId": str(voice_id) if voice_id else None,
        "previewImageUrl": item.get("preview_image_url") or group.get("preview_image_url"),
        "previewVideoUrl": item.get("preview_video_url") or group.get("preview_video_url"),
    }


def _avatar_requires_consent(
    creation_type: str,
    *,
    status: str | None,
    consent_status: str | None,
) -> bool:
    normalized_status = str(status or "").lower()
    normalized_consent = str(consent_status or "").lower()
    if normalized_consent in {"approved", "completed", "not_required", "not-required"}:
        return False
    if normalized_consent:
        return True
    # A resposta v3 informa consent_status=None quando não há consentimento oficial.
    # Digital twins antigos nem sempre trazem esse campo, então mantemos o fallback.
    return normalized_status == "pending_consent" or creation_type == "digital_twin"


@app.post("/api/heygen/avatars")
def create_heygen_avatar(payload: AvatarCreateIn) -> dict:
    """Cria avatar e voz somente apos consentimento explicito na interface."""
    if not payload.consentAccepted:
        raise HTTPException(
            status_code=400,
            detail="Confirme a autorizacao de uso de imagem e voz antes de continuar.",
        )
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do avatar.")

    command = _heygen_cli()
    image_mimes = {"image/jpeg", "image/png"}
    video_mimes = {"video/mp4", "video/webm"}
    avatar_request: dict[str, Any] = {"type": payload.creationType, "name": name}
    voice_audio: dict[str, str] | None = None

    if payload.creationType == "prompt":
        prompt = payload.appearancePrompt.strip()
        if len(prompt) < 12:
            raise HTTPException(status_code=400, detail="Descreva a aparencia do apresentador.")
        avatar_request["prompt"] = prompt
        if payload.media:
            avatar_request["reference_images"] = [
                _avatar_file_payload(command, item, allowed_mime_types=image_mimes)
                for item in payload.media[:3]
            ]
    else:
        if not payload.media:
            expected = "uma foto" if payload.creationType == "photo" else "um video"
            raise HTTPException(status_code=400, detail=f"Envie {expected} para criar o avatar.")
        allowed = image_mimes if payload.creationType == "photo" else video_mimes
        avatar_request["file"] = _avatar_file_payload(
            command,
            payload.media[0],
            allowed_mime_types=allowed,
        )

    if payload.cloneVoice:
        if payload.voiceSource == "video":
            if payload.creationType != "digital_twin" or not payload.media:
                raise HTTPException(
                    status_code=400,
                    detail="A voz do vídeo só pode ser usada na criação de um digital twin.",
                )
        else:
            if not payload.voiceMedia:
                raise HTTPException(status_code=400, detail="Envie um áudio para clonar a voz.")
            voice_audio = _media_payload(
                payload.voiceMedia,
                allowed_mime_types={"audio/mpeg", "audio/wav", "audio/x-wav"},
            )

    avatar_response = _run_heygen_json(
        command,
        ["avatar", "create"],
        payload=avatar_request,
        timeout=180,
    )
    metadata = _avatar_creation_metadata(avatar_response)
    group_id = metadata["groupId"]
    avatar_id = metadata["avatarId"]
    if not group_id:
        raise HTTPException(status_code=502, detail="HeyGen nao retornou a identidade do avatar.")

    requires_consent = _avatar_requires_consent(
        payload.creationType,
        status=metadata["status"],
        consent_status=metadata["consentStatus"],
    )
    now = _now()
    job = {
        "id": f"a-{uuid.uuid4().hex[:12]}",
        "name": name,
        "creationType": payload.creationType,
        "status": metadata["status"]
        or ("pending_consent" if requires_consent else "processing"),
        "groupId": group_id,
        "avatarId": avatar_id,
        "voiceId": metadata["voiceId"],
        "consentStatus": metadata["consentStatus"],
        "consentUrl": None,
        "previewImageUrl": metadata["previewImageUrl"],
        "previewVideoUrl": metadata["previewVideoUrl"],
        "createdAt": now,
        "updatedAt": now,
    }
    # A criação remota já consumiu a solicitação. Grave imediatamente para que
    # qualquer falha posterior não leve o usuário a criar um avatar duplicado.
    _job_store().upsert("avatar", job)
    LOGGER.info(
        "HeyGen avatar created: group_id=%s avatar_id=%s type=%s status=%s consent=%s",
        group_id,
        avatar_id,
        payload.creationType,
        job["status"],
        metadata["consentStatus"],
    )

    setup_warnings: list[str] = []
    voice_id = metadata["voiceId"]
    if payload.cloneVoice and payload.voiceSource == "video" and not voice_id:
        try:
            avatar_details = _run_heygen_json(
                command,
                ["avatar", "get", str(group_id)],
                timeout=45,
            )
            voice_id = _find_value(avatar_details, "default_voice_id")
        except HTTPException as exc:
            setup_warnings.append(
                "O avatar foi criado, mas a voz nativa ainda não pôde ser confirmada."
            )
            LOGGER.warning(
                "HeyGen avatar native voice lookup failed after creation: group_id=%s detail=%s",
                group_id,
                exc.detail,
            )

    if voice_audio:
        try:
            voice_response = _run_heygen_json(
                command,
                ["voice", "clone", "create"],
                payload={
                    "voice_name": f"{name} - voz",
                    "language": "pt",
                    "remove_background_noise": True,
                    "audio": voice_audio,
                },
                timeout=180,
            )
            voice_id = _find_value(voice_response, "voice_clone_id")
        except HTTPException as exc:
            setup_warnings.append("O avatar foi criado, mas a clonagem da voz precisa ser refeita.")
            LOGGER.warning(
                "HeyGen voice clone failed after avatar creation: group_id=%s detail=%s",
                group_id,
                exc.detail,
            )

    if requires_consent:
        try:
            consent_response = _run_heygen_json(
                command,
                ["avatar", "consent", "create", str(group_id)],
                payload={},
                timeout=45,
            )
            job["consentUrl"] = _find_value(
                consent_response,
                "url",
                "consent_url",
                "consentUrl",
            )
            job["status"] = "pending_consent"
        except HTTPException as exc:
            setup_warnings.append(
                "O avatar foi criado, mas o link de consentimento ainda não pôde ser aberto."
            )
            LOGGER.warning(
                "HeyGen consent setup failed after avatar creation: group_id=%s detail=%s",
                group_id,
                exc.detail,
            )

    job["voiceId"] = voice_id
    if setup_warnings:
        job["setupWarning"] = " ".join(setup_warnings)
    job["updatedAt"] = _now()
    _job_store().upsert("avatar", job)
    return {"ok": True, "job": job}


@app.post("/api/heygen/avatars/{job_id}/refresh")
def refresh_heygen_avatar(job_id: str) -> dict:
    job = _job_store().get("avatar", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Criacao de avatar nao encontrada.")
    command = _heygen_cli()
    avatar_response = _run_heygen_json(
        command,
        ["avatar", "get", str(job["groupId"])],
        timeout=45,
    )
    status = str(_find_value(avatar_response, "status") or job.get("status") or "processing")
    job["status"] = status
    job["previewImageUrl"] = _find_value(avatar_response, "preview_image_url") or job.get(
        "previewImageUrl"
    )
    job["previewVideoUrl"] = _find_value(avatar_response, "preview_video_url") or job.get(
        "previewVideoUrl"
    )
    if job.get("voiceId"):
        voice_response = _run_heygen_json(
            command,
            ["voice", "get", str(job["voiceId"])],
            timeout=45,
        )
        job["voiceStatus"] = _find_value(voice_response, "status")
    job["updatedAt"] = _now()
    _job_store().upsert("avatar", job)
    return {"ok": True, "job": job}


@app.get("/api/state")
def state() -> dict:
    """Payload unico que hidrata o store do frontend."""
    snap = _load_snapshot()
    sheets = snap.get("sheets", {})
    calendar_posts = map_calendar(sheets.get("calendario", []))
    performance = _attach_calendar_links(
        map_performance(sheets.get("performance", [])), calendar_posts
    )
    return {
        "trends": map_trends(sheets.get("radar", [])),
        "ideas": map_ideas(sheets.get("ideias", [])),
        "scripts": map_scripts(sheets.get("roteiros", [])),
        "videoJobs": _load_video_jobs(),
        "calendarPosts": calendar_posts,
        "performance": performance,
        "settings": _load_settings(),
        "complianceRules": MEDICAL_COMPLIANCE_RULES,
        "updatedAt": snap.get("updated_at"),
    }


@app.put("/api/settings")
def save_settings(payload: AppSettingsIn) -> dict:
    settings = payload.model_dump()
    return {"ok": True, "settings": _save_settings(settings), "updatedAt": _now()}


# --------------------------------------------------------------------------- #
# HeyGen: envio e consulta somente por acao explicita do usuario
# --------------------------------------------------------------------------- #
class VideoCreateIn(BaseModel):
    scriptId: str
    avatarId: str | None = Field(default=None, max_length=160)
    voiceId: str | None = Field(default=None, max_length=160)
    orientation: Literal["portrait", "landscape"] = "portrait"
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    voiceMood: Literal["confident", "upbeat", "warm", "serious", "neutral"] = "confident"
    generationMode: Literal["direct", "video_agent", "cinematic"] = "direct"
    ctaMode: Literal["auto", "manual", "none", "visual"] = "manual"
    captions: bool = True
    optimizePronunciation: bool = True
    styleId: str | None = None
    brandKitId: str | None = Field(default=None, max_length=160)
    videoAgentMode: Literal["generate", "chat"] = "generate"
    forceNewVersion: bool = False
    narrationText: str | None = Field(default=None, max_length=6000)
    displayText: str | None = Field(default=None, max_length=6000)
    spokenText: str | None = Field(default=None, max_length=6000)
    cinematicPrompt: str | None = Field(default=None, max_length=2000)
    outroText: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)
    expectedScriptRevision: int | None = Field(default=None, ge=0)
    expectedFinalSpeechHash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    contractVersion: str | None = Field(default=None, min_length=1, max_length=40)
    medicalReviewStatus: Literal["not_required", "recommended", "required", "approved"] | None = None
    humanReviewApproved: bool = False
    aiOperationInFlight: bool = False
    aiSchemaValid: bool = True
    editorTechnicalError: str | None = Field(default=None, max_length=500)
    finalConfirmed: bool = True


class VideoPreviewCreateIn(BaseModel):
    scriptId: str
    avatarId: str = Field(min_length=1, max_length=160)
    voiceId: str = Field(min_length=1, max_length=160)
    orientation: Literal["portrait", "landscape"] = "portrait"
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    voiceMood: Literal["confident", "upbeat", "warm", "serious", "neutral"] = "confident"
    generationMode: Literal["direct", "video_agent"] = "direct"
    captions: bool = True
    optimizePronunciation: bool = True
    displayText: str = Field(min_length=10, max_length=6000)
    spokenText: str | None = Field(default=None, max_length=6000)
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)
    expectedScriptRevision: int | None = Field(default=None, ge=0)
    expectedFinalSpeechHash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    contractVersion: str | None = Field(default=None, min_length=1, max_length=40)
    finalConfirmed: bool = True


class SceneVideoConfirmIn(BaseModel):
    confirmed: Literal[True]
    orientation: Literal["portrait", "landscape"] = "portrait"
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    voiceMood: Literal["confident", "upbeat", "warm", "serious", "neutral"] = "confident"
    captions: bool = True
    optimizePronunciation: bool = True
    forceNewVersion: bool = False
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)
    expectedScriptRevision: int | None = Field(default=None, ge=0)
    expectedFinalSpeechHash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    contractVersion: str | None = Field(default=None, min_length=1, max_length=40)


class ProductionProfileIn(BaseModel):
    avatarId: str = Field(min_length=1, max_length=160)
    voiceId: str = Field(min_length=1, max_length=160)
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    voiceMood: Literal["confident", "upbeat", "warm", "serious", "neutral"] = "confident"
    generationMode: Literal["direct", "video_agent", "cinematic"] = "direct"
    avatarMode: Literal["single", "set"] = "single"
    avatarSetId: str | None = Field(default=None, max_length=160)
    primaryAvatarId: str | None = Field(default=None, max_length=160)
    musicTrackId: str | None = Field(default=None, max_length=80)
    musicVolume: float = Field(default=0.12, ge=0.03, le=0.25)
    cinematicPrompt: str = Field(default="", max_length=2000)


class ScriptEditorStateIn(BaseModel):
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    humanReviewApproved: bool = False
    titleChoice: Literal["current", "suggested"] = "current"
    suggestedTitle: str | None = Field(default=None, max_length=500)
    schemaValid: bool = True
    technicalError: str | None = Field(default=None, max_length=500)
    previousScript: str | None = Field(default=None, max_length=6000)
    lastResult: dict[str, Any] | None = None
    reviewActor: str | None = Field(default=None, max_length=120)
    reviewReason: str | None = Field(default=None, max_length=500)


class AvatarLookIn(BaseModel):
    avatarId: str = Field(min_length=1, max_length=160)
    role: Literal["primary", "front", "close", "three_quarter", "standing", "wide"]
    label: str = Field(min_length=1, max_length=120)


class AvatarSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    voiceId: str = Field(min_length=1, max_length=160)
    looks: list[AvatarLookIn] = Field(min_length=2, max_length=12)


class ScenePlanSceneIn(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=1, max_length=6000)
    lookRole: Literal["primary", "front", "close", "three_quarter", "standing", "wide"] = "primary"
    estimatedStart: float = Field(default=0, ge=0, le=3600)
    estimatedEnd: float = Field(default=0, ge=0, le=3600)


class ScenePlanIn(BaseModel):
    scenes: list[ScenePlanSceneIn] = Field(min_length=1, max_length=30)


class SceneDirectorIn(BaseModel):
    displayText: str = Field(min_length=1, max_length=6000)
    spokenText: str = Field(default="", max_length=6000)
    tone: str = Field(default="médico humano e seguro", max_length=300)
    pace: str = Field(default="frases curtas, com pausas naturais", max_length=300)
    emotion: str = Field(default="calmo e convincente", max_length=300)
    emphasisWords: list[str] = Field(default_factory=list, max_length=20)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45


class VisualDirectorIn(BaseModel):
    displayText: str = Field(min_length=1, max_length=6000)
    spokenText: str = Field(default="", max_length=6000)
    tone: str = Field(default="médico humano e seguro", max_length=300)
    pace: str = Field(default="frases curtas, com pausas naturais", max_length=300)
    emotion: str = Field(default="calmo e convincente", max_length=300)
    emphasisWords: list[str] = Field(default_factory=list, max_length=20)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45


class VisualPlanVisualIn(BaseModel):
    type: str = Field(default="none", max_length=40)
    layout: str = Field(default="", max_length=80)
    headline: str = Field(default="", max_length=180)
    body: str = Field(default="", max_length=500)
    purpose: str = Field(default="", max_length=300)
    startRatio: float = Field(default=0.65, ge=0, le=1)
    durationSeconds: float = Field(default=2.5, ge=0, le=60)
    motionPreset: str = Field(default="fade", max_length=40)


class VisualPlanSceneIn(BaseModel):
    sceneId: str = Field(min_length=1, max_length=80)
    visual: VisualPlanVisualIn


class VisualPlanIn(BaseModel):
    scenes: list[VisualPlanSceneIn] = Field(min_length=1, max_length=30)


SCENE_DIRECTOR_PROMPT_VERSION = "2026-08-07-v1-scene-director"
VISUAL_DIRECTOR_PROMPT_VERSION = "2026-08-07-v3-visual-director"
_SCENE_DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "lookRole": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["text", "lookRole", "reason"],
            },
        }
    },
    "required": ["scenes"],
}
_VISUAL_DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sceneId": {"type": "string"},
                    "visual": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "layout": {"type": "string"},
                            "headline": {"type": "string"},
                            "body": {"type": "string"},
                            "purpose": {"type": "string"},
                            "startRatio": {"type": "number"},
                            "durationSeconds": {"type": "number"},
                            "motionPreset": {"type": "string"},
                        },
                        "required": [
                            "type",
                            "layout",
                            "headline",
                            "body",
                            "purpose",
                            "startRatio",
                            "durationSeconds",
                            "motionPreset",
                        ],
                    },
                },
                "required": ["sceneId", "visual"],
            },
        }
    },
    "required": ["scenes"],
}


SHORT_DIRECT_VIDEO_DURATIONS = DIRECT_VIDEO_DURATIONS
SHORT_VIDEO_VOICE_SPEEDS = {key: float(value["speed"]) for key, value in SPEECH_PRESETS.items()}


def _direct_video_payload(
    *,
    script: dict[str, Any],
    narration_text: str,
    avatar_id: str,
    voice_id: str,
    orientation: str,
    speech_mode: str,
    captions: bool,
    optimize_pronunciation: bool,
    voice_mood: str = "confident",
    caption_source_matches_spoken: bool = True,
) -> dict[str, Any]:
    """Monta um video curto deterministico, sem impor duracao artificial."""
    return direct_video_payload(
        script=script,
        narration_text=narration_text,
        avatar_id=avatar_id,
        voice_id=voice_id,
        orientation=orientation,
        speech_mode=speech_mode,
        voice_mood=voice_mood,
        captions=captions,
        optimize_pronunciation=optimize_pronunciation,
        caption_source_matches_spoken=caption_source_matches_spoken,
    )


@app.get("/api/scripts/{script_id}/production-profile")
def get_script_production_profile(script_id: str) -> dict:
    """Intencao de producao escolhida na tela do roteiro, antes do job pago."""
    _find_script(script_id)
    return {"ok": True, "profile": _production_profile(script_id)}


@app.get("/api/scripts/{script_id}/editor-state")
def get_script_editor_state(script_id: str) -> dict:
    script = _find_script(script_id)
    return {"ok": True, "state": _script_editor_state(script_id, script)}


@app.put("/api/scripts/{script_id}/editor-state")
def save_script_editor_state(script_id: str, payload: ScriptEditorStateIn) -> dict:
    script = _find_script(script_id)
    state = _save_script_editor_state(
        {"scriptId": script_id, **payload.model_dump()},
        script,
    )
    return {"ok": True, "state": state}


@app.get("/api/music-tracks")
def list_music_tracks() -> dict:
    """Lista faixas locais disponíveis para a mixagem final, sem custo externo."""
    return {
        "ok": True,
        "tracks": [
            _music_track_response(track)
            for track in MUSIC_LIBRARY
            if (MUSIC_TRACKS_DIR / track["file"]).is_file()
        ],
    }


@app.get("/api/music-tracks/{track_id}/file")
def music_track_file(track_id: str) -> FileResponse:
    track = _music_track(track_id)
    path = _music_track_path(track_id)
    if not track or not path:
        raise HTTPException(status_code=404, detail="Trilha não encontrada.")
    return FileResponse(path, media_type="audio/mpeg", filename=str(track["file"]))


@app.put("/api/scripts/{script_id}/production-profile")
def save_script_production_profile(script_id: str, payload: ProductionProfileIn) -> dict:
    """Persiste avatar/voz/modo associados ao roteiro sem tocar no Sheets."""
    _find_script(script_id)
    profile = _save_production_profile(
        {
            "scriptId": script_id,
            "avatarId": payload.avatarId,
            "voiceId": payload.voiceId,
            "speechMode": payload.speechMode,
            "voiceMood": payload.voiceMood,
            "generationMode": payload.generationMode,
            "avatarMode": payload.avatarMode,
            "avatarSetId": payload.avatarSetId,
            "primaryAvatarId": payload.primaryAvatarId,
            "musicTrackId": payload.musicTrackId,
            "musicVolume": payload.musicVolume,
            "cinematicPrompt": payload.cinematicPrompt,
        }
    )
    return {"ok": True, "profile": profile}


@app.get("/api/avatar-sets")
def list_avatar_sets() -> dict:
    """Lista conjuntos de looks locais; não consulta nem gera vídeo na HeyGen."""
    return {"ok": True, "avatarSets": _list_avatar_sets()}


@app.post("/api/avatar-sets")
def create_avatar_set(payload: AvatarSetIn) -> dict:
    """Cria um Avatar Set local com duas ou mais posições reais."""
    saved = _save_avatar_set(
        name=payload.name,
        voice_id=payload.voiceId,
        looks=[look.model_dump() for look in payload.looks],
    )
    return {"ok": True, "avatarSet": saved}


@app.put("/api/avatar-sets/{avatar_set_id}")
def update_avatar_set(avatar_set_id: str, payload: AvatarSetIn) -> dict:
    if not _get_avatar_set(avatar_set_id):
        raise HTTPException(status_code=404, detail="Avatar Set não encontrado.")
    saved = _save_avatar_set(
        name=payload.name,
        voice_id=payload.voiceId,
        looks=[look.model_dump() for look in payload.looks],
        avatar_set_id=avatar_set_id,
    )
    return {"ok": True, "avatarSet": saved}


@app.delete("/api/avatar-sets/{avatar_set_id}")
def delete_avatar_set(avatar_set_id: str) -> dict:
    conn = _ai_db()
    try:
        cursor = conn.execute("DELETE FROM avatar_sets WHERE id = ?", (avatar_set_id,))
        conn.commit()
    finally:
        conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Avatar Set não encontrado.")
    return {"ok": True, "deleted": avatar_set_id}


@app.get("/api/scripts/{script_id}/scene-plan")
def get_script_scene_plan(script_id: str) -> dict:
    _find_script(script_id)
    return {"ok": True, "scenePlan": _refresh_scene_plan_avatar_bindings(script_id)}


@app.put("/api/scripts/{script_id}/scene-plan")
def save_script_scene_plan(script_id: str, payload: ScenePlanIn) -> dict:
    _find_script(script_id)
    plan = _save_scene_plan(script_id, [scene.model_dump() for scene in payload.scenes])
    return {"ok": True, "scenePlan": plan}


@app.get("/api/scripts/{script_id}/scene-generation/plan")
def get_scene_generation_plan(
    script_id: str,
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural",
    voiceMood: Literal["confident", "upbeat", "warm", "serious", "neutral"] = "confident",
    orientation: Literal["portrait", "landscape"] = "portrait",
) -> dict:
    """Expõe o contrato futuro por cena sem criar job ou chamar a HeyGen."""
    _find_script(script_id)
    scene_plan = _refresh_scene_plan_avatar_bindings(script_id)
    if not scene_plan or not scene_plan.get("scenes"):
        raise HTTPException(status_code=409, detail="Salve o Scene Plan antes de montar a geração por cena.")
    profile = _production_profile(script_id)
    if not profile or not profile.get("voiceId"):
        raise HTTPException(status_code=409, detail="Salve o perfil de produção antes de montar a geração por cena.")
    try:
        result = build_scene_generation_result(
            script_id=script_id,
            scene_plan=scene_plan,
            voice_id=str(profile["voiceId"]),
            speech_mode=speechMode,
            voice_mood=voiceMood,
            orientation=orientation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "generation": result.to_dict()}


@app.post("/api/scripts/{script_id}/scene-generation/submit")
def submit_scene_generation(script_id: str, payload: SceneVideoConfirmIn) -> dict:
    """Submete uma chamada HeyGen por cena somente após confirmação explícita."""
    with _paid_generation_lock(script_id):
        authorization = _authorize_paid_generation(
            script_id=script_id,
            duration_seconds=payload.durationSeconds,
            expected_script_revision=payload.expectedScriptRevision,
            expected_final_speech_hash=payload.expectedFinalSpeechHash,
            contract_version=payload.contractVersion,
            requested_speech=None,
            ai_operation_in_flight=False,
            final_confirmed=payload.confirmed,
        )
        script = authorization["script"]
        scene_plan = _refresh_scene_plan_avatar_bindings(script_id)
        profile = _production_profile(script_id)
        if not scene_plan or not profile or not profile.get("voiceId"):
            raise _paid_error(
                409,
                "SCENE_CONFIGURATION_INCOMPLETE",
                "Salve perfil de produção e Scene Plan antes de gerar por cena.",
            )
        try:
            generation = build_scene_generation_result(
                script_id=script_id,
                scene_plan=scene_plan,
                voice_id=str(profile["voiceId"]),
                speech_mode=payload.speechMode,
                voice_mood=payload.voiceMood,
                orientation=payload.orientation,
            )
        except ValueError as exc:
            raise _paid_error(422, "SCENE_PLAN_INVALID", str(exc)) from exc

        base_key = payload.idempotencyKey or request_fingerprint(
            {
                "generation": generation.to_dict(),
                "scriptRevision": authorization["scriptRevision"],
                "finalSpeechHash": authorization["finalSpeechHash"],
            }
        )
        if payload.forceNewVersion and not payload.idempotencyKey:
            base_key = f"{base_key}:version:{uuid.uuid4().hex[:12]}"
        reservations: list[tuple[Any, dict[str, Any], str]] = []
        for request in generation.requests:
            now = _now()
            scene_key = f"scene-video:{script_id}:{request.scene_id}:{base_key}"
            production_settings = {
                "avatarId": request.avatar_id,
                "voiceId": request.voice_id,
                "orientation": request.orientation,
                "durationSeconds": payload.durationSeconds,
                "speechMode": request.speech_mode,
                "voiceMood": request.voice_mood,
                "generationMode": "direct",
                "captions": payload.captions,
                "optimizePronunciation": payload.optimizePronunciation,
                "spokenText": request.spoken_text,
                "sceneCount": generation.scene_count,
                "cutPolicy": "hard_cut",
                "avatarSetId": profile.get("avatarSetId"),
            }
            reserved_job = {
                "id": f"sv-{uuid.uuid4().hex[:12]}",
                "scriptId": script_id,
                "scriptRevision": authorization["scriptRevision"],
                "finalSpeechHash": authorization["finalSpeechHash"],
                "contractVersion": authorization["contractVersion"],
                "requestFingerprint": request_fingerprint(
                    {
                        "scriptId": script_id,
                        "scriptRevision": authorization["scriptRevision"],
                        "finalSpeechHash": authorization["finalSpeechHash"],
                        "contractVersion": authorization["contractVersion"],
                        "generationMode": "scene",
                        "sceneId": request.scene_id,
                        "productionSettings": production_settings,
                    }
                ),
                "status": "fila",
                "provider": "heygen",
                "progresso": 0,
                "criadoEm": now,
                "atualizadoEm": now,
                "submissionState": "reserved",
                "isScene": True,
                "sceneBatchId": base_key,
                "sceneId": request.scene_id,
                "sceneOrder": request.order,
                "productionSettings": production_settings,
            }
            job, reservation = _job_store().reserve_video(
                reserved_job,
                idempotency_key=scene_key,
                force_new_version=payload.forceNewVersion,
            )
            if reservation == "conflict":
                if job.get("idempotencyKey") == scene_key:
                    raise _paid_error(
                        409,
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "Esta chave de idempotência já foi usada com outro payload de cena.",
                    )
                raise _paid_error(
                    409,
                    "SCENE_GENERATION_IN_PROGRESS",
                    f"A cena {request.scene_id} já está em produção.",
                )
            reservations.append((request, job, reservation))

    created_jobs = [job for _request, job, reservation in reservations if reservation == "created"]
    jobs: list[dict[str, Any]] = [
        job for _request, job, reservation in reservations if reservation == "duplicate"
    ]
    try:
        command = _heygen_cli()
        _, private_looks, _from_cache = _private_avatar_library(command, allow_cache=False)
        ready_avatar_ids = {
            str(look.get("id"))
            for look in private_looks
            if isinstance(look, dict) and look.get("status") == "completed" and look.get("id")
        }
        missing = [
            request.avatar_id
            for request, _job, reservation in reservations
            if reservation == "created" and request.avatar_id not in ready_avatar_ids
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Looks não prontos na HeyGen: {', '.join(missing)}",
            )
    except Exception as exc:
        message = _safe_video_provider_error(exc)
        for job in created_jobs:
            job["status"] = "erro"
            job["erro"] = message
            job["retrySafe"] = True
            job["submissionState"] = "failed_safe"
            job["atualizadoEm"] = _now()
            _job_store().upsert("video", job)
        if isinstance(exc, HTTPException):
            raise
        raise _paid_error(502, "HEYGEN_CONFIGURATION_FAILED", message) from exc

    for request, job, reservation in reservations:
        if reservation == "duplicate":
            continue
        try:
            job["submissionState"] = "submitting"
            job["atualizadoEm"] = _now()
            _job_store().upsert("video", job)
            direct_payload = _direct_video_payload(
                script=script,
                narration_text=request.spoken_text,
                avatar_id=request.avatar_id,
                voice_id=request.voice_id,
                orientation=request.orientation,
                speech_mode=request.speech_mode,
                voice_mood=request.voice_mood,
                captions=payload.captions,
                optimize_pronunciation=payload.optimizePronunciation,
            )
            response = _run_heygen_json(command, ["video", "create"], payload=direct_payload, timeout=60)
            video_id = _find_value(response, "video_id", "videoId", "id")
            if not video_id:
                raise RuntimeError("HeyGen não retornou o identificador da cena.")
            job["status"] = "fila"
            job["submissionState"] = "submitted"
            job["remoteVideoId"] = video_id
            job["atualizadoEm"] = _now()
            _job_store().upsert("video", job)
            jobs.append(job)
        except Exception as exc:
            job["status"] = "erro"
            job["erro"] = _safe_video_provider_error(exc)
            job["retrySafe"] = job.get("submissionState") != "submitting"
            job["submissionState"] = "failed_safe" if job["retrySafe"] else "submission_uncertain"
            job["atualizadoEm"] = _now()
            _job_store().upsert("video", job)
            raise HTTPException(status_code=502, detail=f"Falha ao gerar a cena {request.scene_id}: {job['erro']}") from exc
    return {
        "ok": True,
        "generation": generation.to_dict(),
        "jobs": jobs,
    }


@app.post("/api/scripts/{script_id}/scene-plan/direct")
def direct_scene_plan(script_id: str, payload: SceneDirectorIn) -> dict:
    """Sugere a divisão de cenas somente após ação explícita do usuário."""
    script = _find_script(script_id)
    profile = _production_profile(script_id)
    if not profile:
        raise HTTPException(status_code=409, detail="Salve o perfil de produção antes de pedir direção ao Claude.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="Defina ANTHROPIC_API_KEY para gerar direção com Claude.")

    avatar_set = _get_avatar_set(str(profile.get("avatarSetId") or "")) if profile.get("avatarMode") == "set" else None
    available_roles = [str(look["role"]) for look in (avatar_set or {}).get("looks", []) if look.get("role")]
    if not available_roles:
        available_roles = ["primary"]
    cache_payload = {
        "promptVersion": SCENE_DIRECTOR_PROMPT_VERSION,
        "scriptId": script_id,
        "script": {
            "titulo": script.get("titulo"),
            "hook": script.get("hook"),
            "dorConflito": script.get("dorConflito"),
            "explicacaoSimples": script.get("explicacaoSimples"),
            "virada": script.get("virada"),
            "cta": script.get("cta"),
            "cuidadosMedicos": script.get("cuidadosMedicos"),
        },
        "performance": payload.model_dump(),
        "avatarMode": profile.get("avatarMode"),
        "availableRoles": available_roles,
    }
    cached = _ai_cache_get("scene-plan.direct", cache_payload)
    if cached:
        return cached

    user_prompt = json.dumps(
        {
            "IDEIA_E_ROTEIRO": cache_payload["script"],
            "PERFORMANCE": payload.model_dump(),
            "AVATAR_SET": {
                "mode": profile.get("avatarMode"),
                "availableRoles": available_roles,
                "instruction": "Escolha somente lookRole. Nunca escolha ou invente avatarId.",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = f"""Você é diretor de cenas para vídeos curtos médicos em português brasileiro.
Divida a narrativa em poucas cenas coerentes, sem transformar cada frase em uma cena.

Regras obrigatórias:
- Preserve exatamente o texto falado; não reescreva a fala.
- Use 1–2 cenas para vídeos de 10–15s, 2–3 para 30s, 3–4 para 45s e 3–5 para 60s.
- Mude de posição principalmente no hook, mudança de argumento, virada ou conclusão.
- Se houver dois ou mais roles disponíveis, use pelo menos dois roles distintos.
- Escolha somente um lookRole por cena dentre os roles disponíveis no contexto.
- Nunca retorne avatarId; o backend resolve o avatar real.
- Uma cena possui um único look fixo. Nunca descreva transição de posição dentro da cena.
- Retorne somente JSON no schema solicitado.

VERSÃO DO PROMPT: {SCENE_DIRECTOR_PROMPT_VERSION}"""

    import anthropic

    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_SCENE_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"))
        message = client.messages.create(
            model=model,
            max_tokens=1200,
            system=system_prompt,
            output_config={"format": {"type": "json_schema", "schema": _SCENE_DIRECTOR_SCHEMA}},
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = json.loads(raw_text)
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Claude respondeu {exc.status_code}: {exc.message}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="A direção do Claude não veio em JSON válido.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gerar direção de cenas: {exc}")

    suggestions: list[dict[str, str]] = []
    for item in parsed.get("scenes") or []:
        if not isinstance(item, dict):
            continue
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        role = str(item.get("lookRole") or "primary")
        suggestions.append(
            {
                "text": text,
                "lookRole": role if role in available_roles else "primary",
                "reason": re.sub(r"\s+", " ", str(item.get("reason") or "mudança narrativa")).strip(),
            }
        )
    if not suggestions:
        raise HTTPException(status_code=502, detail="Claude não retornou nenhuma cena utilizável.")
    response = {"ok": True, "provider": "claude", "promptVersion": SCENE_DIRECTOR_PROMPT_VERSION, "scenes": suggestions}
    _record_anthropic_usage("scene-plan.direct", model, message)
    _ai_cache_put("scene-plan.direct", cache_payload, response)
    return response


@app.get("/api/scripts/{script_id}/visual-plan")
def get_script_visual_plan(script_id: str) -> dict:
    _find_script(script_id)
    return {"ok": True, "visualPlan": _get_visual_plan(script_id)}


@app.put("/api/scripts/{script_id}/visual-plan")
def save_script_visual_plan(script_id: str, payload: VisualPlanIn) -> dict:
    _find_script(script_id)
    scene_plan = _scene_plan(script_id)
    if not scene_plan or not scene_plan.get("scenes"):
        raise HTTPException(status_code=409, detail="Salve o Scene Plan antes de editar a direção visual.")
    submitted = {scene.sceneId: scene.visual.model_dump() for scene in payload.scenes}
    visual_scenes: list[dict[str, Any]] = []
    scene_count = len(scene_plan["scenes"])
    for index, scene in enumerate(scene_plan["scenes"]):
        visual = submitted.get(str(scene["id"]), {})
        visual_scenes.append(
            {
                "sceneId": scene["id"],
                "visual": _normalize_video_visual(
                    visual,
                    scene=scene,
                    index=index,
                    scene_count=scene_count,
                    strict_required=True,
                ),
            }
        )
    plan = {
        "scriptId": script_id,
        "designSystemVersion": VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
        "promptVersion": VISUAL_DIRECTOR_PROMPT_VERSION,
        "scenes": visual_scenes,
    }
    return {"ok": True, "visualPlan": _save_visual_plan(script_id, plan)}


@app.get("/api/scripts/{script_id}/video-slides")
def get_video_slide_render(script_id: str) -> dict:
    _find_script(script_id)
    return {"ok": True, "render": _video_slide_public_render(script_id, _get_video_slide_render(script_id))}


@app.post("/api/scripts/{script_id}/video-slides/render")
def render_script_video_slides(script_id: str) -> dict:
    """Renderiza previews locais; nao chama Claude, HeyGen ou outro provedor."""
    _find_script(script_id)
    visual_plan = _get_visual_plan(script_id)
    if not visual_plan or not visual_plan.get("scenes"):
        raise HTTPException(status_code=409, detail="Salve a direção visual antes de renderizar os previews.")
    try:
        visual_plan = _save_visual_plan(script_id, _normalize_visual_plan_for_render(script_id, visual_plan))
        rendered = render_video_slides(_video_slide_output_dir(script_id), visual_plan)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível renderizar os previews locais: {exc}") from exc
    saved = _save_video_slide_render(script_id, rendered)
    return {"ok": True, "render": _video_slide_public_render(script_id, saved)}


@app.get("/api/scripts/{script_id}/video-slides/{filename}")
def get_video_slide_file(script_id: str, filename: str) -> FileResponse:
    _find_script(script_id)
    suffix = Path(filename).suffix.lower()
    if Path(filename).name != filename or suffix not in {".png", ".svg"}:
        raise HTTPException(status_code=404, detail="Preview não encontrado.")
    path = (_video_slide_output_dir(script_id) / filename).resolve()
    root = _video_slide_output_dir(script_id).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Preview não encontrado.")
    return FileResponse(path, media_type="image/svg+xml" if suffix == ".svg" else "image/png")


@app.post("/api/scripts/{script_id}/compose-final-video")
def compose_script_final_video(script_id: str) -> dict:
    _find_script(script_id)
    job = _compose_final_video_if_ready(script_id, raise_when_not_ready=True)
    return {"ok": True, "job": job}


@app.post("/api/scripts/{script_id}/visual-plan/direct")
def direct_visual_plan(script_id: str, payload: VisualDirectorIn) -> dict:
    """Analisa o vídeo inteiro e sugere apoios visuais somente após clique explícito."""
    script = _find_script(script_id)
    scene_plan = _scene_plan(script_id)
    if not scene_plan or not scene_plan.get("scenes"):
        raise HTTPException(status_code=409, detail="Salve o Scene Plan antes de pedir direção visual.")
    profile = _production_profile(script_id)
    if not profile:
        raise HTTPException(status_code=409, detail="Salve o perfil de produção antes de pedir direção visual.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="Defina ANTHROPIC_API_KEY para gerar direção visual com Claude.")

    avatar_set = _get_avatar_set(str(profile.get("avatarSetId") or "")) if profile.get("avatarMode") == "set" else None
    scene_count = len(scene_plan["scenes"])
    required_supports = _required_visual_support_count(scene_count)
    design_system = {
        "version": VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
        "canvas": "1080x1920",
        "allowedTypes": sorted(VIDEO_VISUAL_TYPES),
        "allowedLayouts": sorted(VIDEO_VISUAL_LAYOUTS),
        "allowedMotionPresets": sorted(VIDEO_VISUAL_MOTION_PRESETS),
        "requiredSupportSlides": required_supports,
        "supportPolicy": (
            "Se houver N cenas, crie exatamente N-1 apoios visuais: um para cada cena antes da última. "
            "O apoio aparece durante o áudio do avatar; a troca de avatar/look acontece somente no corte para a próxima cena."
        ),
        "rules": [
            "apoio de vídeo, não slide explicativo: uma ideia visual por apoio",
            "headline de 2 a 6 palavras quando houver headline",
            "body opcional; se usar, no máximo 3 labels curtos separados por •",
            "cada label do body deve ter no máximo 3 palavras",
            "linguagem simples e complementar à fala",
            "não transcrever o roteiro",
            "não criar rodapé, disclaimer, texto técnico ou resumo longo",
            "não gerar HTML, CSS ou JavaScript",
            "startRatio sempre entre 0.15 e 0.70 para apoios obrigatórios",
            "durationSeconds entre 1.0 e 5.0",
            "motionPreset somente none, fade, soft_zoom ou fade_zoom",
        ],
    }
    cache_payload = {
        "promptVersion": VISUAL_DIRECTOR_PROMPT_VERSION,
        "designSystemVersion": VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
        "script": {
            "scriptId": script_id,
            "titulo": script.get("titulo"),
            "hook": script.get("hook"),
            "dorConflito": script.get("dorConflito"),
            "explicacaoSimples": script.get("explicacaoSimples"),
            "virada": script.get("virada"),
            "cta": script.get("cta"),
            "cuidadosMedicos": script.get("cuidadosMedicos"),
        },
        "performance": payload.model_dump(),
        "scenePlan": scene_plan,
        "avatarSet": avatar_set,
        "designSystem": design_system,
    }
    cached = _ai_cache_get("visual-plan.direct", cache_payload)
    if cached:
        return cached

    user_prompt = json.dumps(
        {
            "ROTEIRO_COMPLETO": cache_payload["script"],
            "PERFORMANCE": payload.model_dump(),
            "PLANO_DE_CENAS": scene_plan,
            "AVATAR_SET": avatar_set or {"mode": "single", "primaryAvatarId": profile.get("primaryAvatarId")},
            "DESIGN_SYSTEM": design_system,
            "COMPLIANCE": "O visual não pode ser mais assertivo que o roteiro. Trate associações como associações.",
        },
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = f"""Você é diretor visual de vídeos médicos verticais.
Analise o vídeo como uma narrativa completa, considerando o que foi dito antes,
o que está sendo dito agora e o que será explicado depois.

Regras obrigatórias:
- Retorne exatamente uma entrada para cada cena do PLANO_DE_CENAS.
- Se o vídeo tiver N cenas, crie exatamente N-1 apoios visuais.
- Para as primeiras N-1 cenas, visual.type não pode ser none.
- Para a última cena, use visual.type none para fechar no avatar.
- O apoio visual aparece durante a fala do avatar; ele não é um intervalo mudo.
- startRatio é posição relativa dentro da própria cena, nunca timestamp absoluto.
- Para apoios obrigatórios, startRatio deve ficar entre 0.15 e 0.70.
- durationSeconds deve ficar entre 1.0 e 5.0.
- motionPreset deve ser um dos presets permitidos.
- Quando usar visual, escolha somente tipos e layouts permitidos no DESIGN_SYSTEM.
- O visual deve complementar, não repetir ou transcrever, a fala.
- O visual deve parecer apoio de edição em vídeo: objetivo, escaneável e mais visual que textual.
- Headline ideal: 2–6 palavras. Nunca use parágrafo.
- Body é opcional. Se necessário, use no máximo 3 labels curtos separados por " • ".
- Cada label do body deve ter no máximo 3 palavras.
- Evite frases explicativas completas no body; prefira palavras-chave visuais.
- Não crie afirmações médicas mais fortes que o roteiro.
- Não gere HTML, CSS, JavaScript ou avatarId.
- Retorne somente JSON no schema solicitado.

VERSÃO DO PROMPT: {VISUAL_DIRECTOR_PROMPT_VERSION}"""

    import anthropic

    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_VISUAL_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"))
        message = client.messages.create(
            model=model,
            max_tokens=1600,
            system=system_prompt,
            output_config={"format": {"type": "json_schema", "schema": _VISUAL_DIRECTOR_SCHEMA}},
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = json.loads(raw_text)
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Claude respondeu {exc.status_code}: {exc.message}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="A direção visual do Claude não veio em JSON válido.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gerar direção visual: {exc}")

    returned_by_id = {
        str(item.get("sceneId")): item
        for item in parsed.get("scenes") or []
        if isinstance(item, dict)
    }
    visual_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scene_plan["scenes"]):
        raw_item = returned_by_id.get(str(scene["id"]))
        if raw_item is None:
            raw_items = parsed.get("scenes") or []
            raw_item = raw_items[index] if index < len(raw_items) and isinstance(raw_items[index], dict) else {}
        raw_visual = raw_item.get("visual") if isinstance(raw_item, dict) else {}
        raw_visual = raw_visual if isinstance(raw_visual, dict) else {}
        visual_scenes.append(
            {
                "sceneId": scene["id"],
                "visual": _normalize_video_visual(
                    raw_visual,
                    scene=scene,
                    index=index,
                    scene_count=scene_count,
                ),
            }
        )
    plan = {
        "scriptId": script_id,
        "designSystemVersion": VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
        "promptVersion": VISUAL_DIRECTOR_PROMPT_VERSION,
        "scenes": visual_scenes,
    }
    saved_plan = _save_visual_plan(script_id, plan)
    response = {"ok": True, "provider": "claude", "visualPlan": saved_plan}
    _record_anthropic_usage("visual-plan.direct", model, message)
    _ai_cache_put("visual-plan.direct", cache_payload, response)
    return response


class ScriptEditorAssistIn(BaseModel):
    operation: Literal["medical_rewrite", "fit_duration"]
    scriptId: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=6000)
    title: str = Field(default="", max_length=500)
    sourceText: str = Field(default="", max_length=20000)
    contextText: str = Field(default="", max_length=20000)
    medicalCautions: str = Field(default="", max_length=3000)
    riskLevel: str = Field(default="medio", max_length=80)
    claims: list[str] = Field(default_factory=list, max_length=50)
    glossary: list[str] = Field(default_factory=list, max_length=50)
    cta: str = Field(default="", max_length=500)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    speechProfileId: str = Field(default=DEFAULT_SPEECH_PROFILE.id, max_length=100)
    editorialProfileId: str = Field(
        default=SCRIPT_EDITOR_CONTRACT["editorialProfile"]["id"],
        max_length=100,
    )
    humanReviewApproved: bool = False


_SCRIPT_EDITOR_INFLIGHT: dict[str, Future[dict[str, Any]]] = {}
_SCRIPT_EDITOR_INFLIGHT_LOCK = threading.Lock()


def _script_editor_model_call(
    client: Any,
    *,
    model: str,
    system: str,
    user: str,
) -> tuple[Any, Any]:
    message = client.messages.create(
        model=model,
        max_tokens=1600,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": EDITOR_OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    raw_text = "".join(getattr(block, "text", "") for block in message.content)
    return message, json.loads(raw_text)


def _safe_script_editor_response(
    payload: ScriptEditorAssistIn,
    *,
    provider: str,
    model: str,
    retry_count: int,
    reason: str,
) -> dict[str, Any]:
    current = payload.text.strip()
    fallback = {
        "operation": payload.operation,
        "script": current,
        "summaryOfChanges": [],
        "titleAlignment": title_alignment(payload.title, current),
        "medicalSafety": {
            "meaningPreserved": True,
            "newClaimsAdded": False,
            "unsupportedPersonalExperienceAdded": False,
            "requiresHumanReview": True,
            "reasons": [reason],
        },
        "warnings": [
            "A resposta da IA não pôde ser aplicada com segurança. O texto anterior foi mantido."
        ],
    }
    validated = post_validate_editor_output(
        fallback,
        title=payload.title,
        current_script=current,
        allowed_context="\n".join(
            [payload.text, payload.sourceText, payload.contextText, payload.medicalCautions]
            + payload.claims
            + payload.glossary
        ),
        duration_seconds=payload.durationSeconds,
        risk_level=payload.riskLevel,
        human_review_approved=payload.humanReviewApproved,
    )
    return {
        "ok": False,
        **validated,
        "provider": provider,
        "model": model,
        "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
        "cacheHit": False,
        "retryCount": retry_count,
        "schemaValid": False,
        "technicalError": reason,
        "previousScript": current,
    }


def _script_editor_provider_failure(exc: Exception) -> tuple[str, str]:
    """Classifica falhas sem copiar payload, resposta bruta ou segredo para a UI/log."""

    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired, requests.Timeout)):
        return "PROVIDER_TIMEOUT", "A IA excedeu o tempo limite."
    if status_code == 429:
        return "PROVIDER_RATE_LIMITED", "A IA atingiu o limite temporário de requisições."
    if isinstance(status_code, int) and status_code >= 500:
        return "PROVIDER_UNAVAILABLE", "A IA está temporariamente indisponível."
    if isinstance(exc, (ConnectionError, OSError, requests.ConnectionError)):
        return "PROVIDER_CONNECTION_INTERRUPTED", "A conexão com a IA foi interrompida."
    return "PROVIDER_ERROR", "A IA não respondeu agora."


def _run_script_editor_assist(
    payload: ScriptEditorAssistIn,
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="A edição com IA não está configurada. O texto atual foi preservado.",
        )
    import anthropic

    body = payload.model_dump()
    system, user = build_editor_prompt(body)
    allowed_context = "\n".join(
        [payload.text, payload.sourceText, payload.contextText, payload.medicalCautions]
        + payload.claims
        + payload.glossary
    )
    client = anthropic.Anthropic()
    retry_count = 0
    last_reason = "A resposta não passou na validação estruturada."
    for attempt in range(2):
        request_user = user
        if attempt:
            request_user += (
                "\n\nCORREÇÃO ÚNICA OBRIGATÓRIA: a resposta anterior foi rejeitada. "
                f"Motivo: {last_reason} Corrija o JSON e todas as regras sem inventar conteúdo."
            )
        try:
            message, raw = _script_editor_model_call(
                client,
                model=model,
                system=system,
                user=request_user,
            )
            _record_anthropic_usage(
                "scripts.editor_assist" if attempt == 0 else "scripts.editor_assist.repair",
                model,
                message,
            )
            normalized = normalize_editor_output(raw, payload.operation)
            validated = post_validate_editor_output(
                normalized,
                title=payload.title,
                current_script=payload.text,
                allowed_context=allowed_context,
                duration_seconds=payload.durationSeconds,
                risk_level=payload.riskLevel,
                human_review_approved=payload.humanReviewApproved,
            )
            if (
                payload.operation == "fit_duration"
                and validated["durationAssessment"]["status"] == "blocking"
            ):
                last_reason = (
                    "A fala ajustada ainda ultrapassa o limite rígido local de duração. "
                    "Reduza redundâncias e respeite a faixa de geração."
                )
                if attempt == 0:
                    retry_count = 1
                    continue
                return _safe_script_editor_response(
                    payload,
                    provider=provider,
                    model=model,
                    retry_count=1,
                    reason=last_reason,
                )
            return {
                "ok": True,
                **validated,
                "provider": provider,
                "model": model,
                "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
                "cacheHit": False,
                "retryCount": retry_count,
                "schemaValid": True,
                "previousScript": payload.text,
            }
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            last_reason = str(exc)[:300] or "JSON inválido."
            if attempt == 0:
                retry_count = 1
                continue
            return _safe_script_editor_response(
                payload,
                provider=provider,
                model=model,
                retry_count=1,
                reason=last_reason,
            )
        except Exception as exc:
            error_code, last_reason = _script_editor_provider_failure(exc)
            LOGGER.warning(
                "script_editor_provider_error operation=%s provider=%s model=%s code=%s attempt=%s",
                payload.operation,
                provider,
                model,
                error_code,
                attempt + 1,
            )
            if attempt == 0:
                retry_count = 1
                continue
            return _safe_script_editor_response(
                payload,
                provider=provider,
                model=model,
                retry_count=1,
                reason=last_reason,
            )
    return _safe_script_editor_response(
        payload,
        provider=provider,
        model=model,
        retry_count=1,
        reason=last_reason,
    )


@app.post("/api/scripts/editor-assist")
def script_editor_assist(payload: ScriptEditorAssistIn) -> dict:
    """Executa revisão médica ou ajuste de duração sem persistir a fala automaticamente."""
    started = time.perf_counter()
    input_assessment = duration_assessment(payload.text, payload.durationSeconds)
    model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    provider = "anthropic"
    body = payload.model_dump()

    if (
        payload.operation == "fit_duration"
        and input_assessment.generationMinWords
        <= input_assessment.wordCount
        <= input_assessment.generationMaxWords
    ):
        no_op_output = {
            "operation": payload.operation,
            "script": payload.text.strip(),
            "summaryOfChanges": [],
            "titleAlignment": title_alignment(payload.title, payload.text),
            "medicalSafety": {
                "meaningPreserved": True,
                "newClaimsAdded": False,
                "unsupportedPersonalExperienceAdded": False,
                "requiresHumanReview": False,
                "reasons": [],
            },
            "warnings": [],
        }
        validated = post_validate_editor_output(
            no_op_output,
            title=payload.title,
            current_script=payload.text,
            allowed_context=payload.text,
            duration_seconds=payload.durationSeconds,
            risk_level=payload.riskLevel,
            human_review_approved=payload.humanReviewApproved,
        )
        response = {
            "ok": True,
            **validated,
            "provider": "local",
            "model": "deterministic",
            "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
            "cacheHit": False,
            "retryCount": 0,
            "noOp": True,
            "message": f"O texto já está adequado para {payload.durationSeconds}s; nenhuma chamada de IA foi feita.",
            "schemaValid": True,
            "previousScript": payload.text,
        }
        LOGGER.info(
            "script_editor operation=%s preset=%s input_words=%s output_words=%s input_status=%s output_status=%s prompt_version=%s provider=%s model=%s cache_hit=false retry=0 latency_ms=%s",
            payload.operation, payload.durationSeconds, input_assessment.wordCount,
            validated["durationAssessment"]["wordCount"], input_assessment.status,
            validated["durationAssessment"]["status"], MEDICAL_EDITORIAL_PROMPT_VERSION,
            "local", "deterministic", round((time.perf_counter() - started) * 1000),
        )
        return response

    cache_payload = editor_cache_payload(body, provider=provider, model=model)
    request_key = _ai_cache_key("scripts.editor_assist", cache_payload)
    owner = False
    with _SCRIPT_EDITOR_INFLIGHT_LOCK:
        future = _SCRIPT_EDITOR_INFLIGHT.get(request_key)
        if future is None:
            future = Future()
            _SCRIPT_EDITOR_INFLIGHT[request_key] = future
            owner = True
    if not owner:
        try:
            response = future.result(timeout=120)
        except FutureTimeoutError as exc:
            raise HTTPException(
                status_code=409,
                detail="Uma edição idêntica ainda está em andamento. Aguarde alguns segundos.",
            ) from exc
        return {**response, "deduplicated": True}

    try:
        cached = _ai_cache_get("scripts.editor_assist", cache_payload)
        if cached:
            response = {**cached, "cacheHit": True, "deduplicated": False}
            future.set_result(response)
            LOGGER.info(
                "script_editor operation=%s preset=%s input_words=%s output_words=%s input_status=%s output_status=%s prompt_version=%s provider=%s model=%s cache_hit=true retry=%s latency_ms=%s",
                payload.operation, payload.durationSeconds, input_assessment.wordCount,
                response.get("durationAssessment", {}).get("wordCount"), input_assessment.status,
                response.get("durationAssessment", {}).get("status"), MEDICAL_EDITORIAL_PROMPT_VERSION,
                provider, model, response.get("retryCount", 0),
                round((time.perf_counter() - started) * 1000),
            )
            return response

        response = _run_script_editor_assist(payload, provider=provider, model=model)
        if response.get("schemaValid"):
            _ai_cache_put("scripts.editor_assist", cache_payload, response)
        if payload.scriptId:
            existing_state = _script_editor_state(payload.scriptId)
            _save_script_editor_state(
                {
                    **existing_state,
                    "scriptId": payload.scriptId,
                    "durationSeconds": payload.durationSeconds,
                    "humanReviewApproved": payload.humanReviewApproved,
                    "schemaValid": bool(response.get("schemaValid")),
                    "technicalError": response.get("technicalError"),
                    "previousScript": payload.text,
                    "suggestedTitle": response.get("titleAlignment", {}).get("suggestedTitle"),
                    "lastResult": response,
                }
            )
        future.set_result(response)
        LOGGER.info(
            "script_editor operation=%s preset=%s input_words=%s output_words=%s input_status=%s output_status=%s medical_review=%s title_alignment=%s prompt_version=%s provider=%s model=%s cache_hit=false retry=%s latency_ms=%s",
            payload.operation, payload.durationSeconds, input_assessment.wordCount,
            response.get("durationAssessment", {}).get("wordCount"), input_assessment.status,
            response.get("durationAssessment", {}).get("status"), response.get("medicalReviewStatus"),
            response.get("titleAlignment", {}).get("status"), MEDICAL_EDITORIAL_PROMPT_VERSION,
            provider, model, response.get("retryCount", 0),
            round((time.perf_counter() - started) * 1000),
        )
        return response
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with _SCRIPT_EDITOR_INFLIGHT_LOCK:
            _SCRIPT_EDITOR_INFLIGHT.pop(request_key, None)


class NaturalizeScriptIn(BaseModel):
    text: str = Field(min_length=20, max_length=6000)
    medicalCautions: str = Field(default="", max_length=2000)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    outro: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    ctaMode: Literal["auto", "manual", "none", "visual"] = "auto"
    manualCta: str = Field(default="", max_length=240)
    recentCtas: list[str] = Field(default_factory=list)
    generationMode: Literal["direct", "video_agent", "cinematic"] = "direct"


_NATURAL_SCRIPT_SCHEMA = PERFORMANCE_SCHEMA

def _natural_script_system(duration_seconds: int, outro: str = MANDATORY_VIDEO_OUTRO) -> str:
    prompt = build_performance_prompt(
        text="",
        medical_cautions="",
        duration_seconds=duration_seconds,
        cta_mode="manual",
        manual_cta=outro,
        recent_ctas=[],
        video_agent=False,
    )
    return prompt.system


def _fit_ten_second_text(text: str) -> str:
    """Reduz uma fala a um hook coerente de 18–24 palavras, sem encerramento."""
    return fit_ten_second_text(text)


def _duration_word_limits(duration_seconds: int) -> tuple[int, int]:
    return duration_word_limits(duration_seconds)


def _fit_text_to_duration(text: str, duration_seconds: int, outro: str) -> str:
    return fit_text_to_duration(text, duration_seconds, outro)


_SAFE_NARRATION_PADDING = (
    "Esse resultado precisa ser interpretado com calma, porque uma associação não prova causa.",
    "Pessoas diferentes podem ter contextos e respostas diferentes, então um número não representa automaticamente cada indivíduo.",
    "O mais importante é entender os limites da informação antes de tomar uma decisão.",
    "Uma conversa com um profissional de saúde ajuda a colocar o achado no contexto da sua história.",
)


def _repair_script_narration(script: dict[str, Any], payload: GenerateScriptIn) -> tuple[str, bool]:
    """Recompõe uma fala curta usando o conteúdo estruturado já retornado pelo Claude."""
    original = str(script.get("textoFalado") or "").strip()
    candidate = _fit_text_to_duration(original, payload.durationSeconds, payload.outro)
    if duration_assessment(candidate, payload.durationSeconds).wordCount >= _duration_word_limits(payload.durationSeconds)[0]:
        return candidate, candidate != original

    parts = [
        original,
        str(script.get("hook") or ""),
        str(script.get("dorConflito") or ""),
        str(script.get("explicacaoSimples") or ""),
        str(script.get("virada") or ""),
        str(script.get("cta") or ""),
    ]
    expanded = " ".join(part.strip() for part in parts if part.strip())
    candidate = _fit_text_to_duration(expanded, payload.durationSeconds, payload.outro)
    for padding in _SAFE_NARRATION_PADDING:
        if duration_assessment(candidate, payload.durationSeconds).wordCount >= _duration_word_limits(payload.durationSeconds)[0]:
            break
        candidate = _fit_text_to_duration(
            f"{candidate} {padding}", payload.durationSeconds, payload.outro
        )
    return candidate, candidate != original


_SCRIPT_GENERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "titulo": {"type": "string"},
        "hook": {"type": "string"},
        "dorConflito": {"type": "string"},
        "explicacaoSimples": {"type": "string"},
        "virada": {"type": "string"},
        "cta": {"type": "string"},
        "cuidadosMedicos": {"type": "string"},
        "textoFalado": {"type": "string"},
    },
    "required": [
        "titulo",
        "hook",
        "dorConflito",
        "explicacaoSimples",
        "virada",
        "cta",
        "cuidadosMedicos",
        "textoFalado",
    ],
}


SCRIPT_GENERATION_PROMPT_VERSION = "2026-08-07-v5-duration-repair"


def _script_generation_system(tone: str, duration_seconds: int) -> str:
    """Sistema de prompt para gerar roteiros com tom editorial especificado."""
    tone_guide = {
        "positivo": """
TOM POSITIVO: Leitura otimista e construtiva.
- Destaque oportunidades e beneficios possiveis.
- Linguagem acolhedora e esperancosa, mas nao prometa resultados garantidos.
- Framing: "pode ser util", "estudos sugerem", "possibilidades".
- Evite linguagem de risco direto; reframe como aprendizado e cuidado.""",
        "neutro": """
TOM NEUTRO: Linguagem jornalistica, equilibrada e respeitosa.
- Apresente achado, numeros, contexto e limitacoes de forma clara.
- Use dados e dados exatos sem adjetivos que virem juizo.
- Framing: "estudos mostram", "dados indicam", "contexto importante".
- Balanceie descoberta e limite: nao prometa, nao alarme.""",
        "apreensivo": """
TOM APREENSIVO: Cria tensao e atencao via riscos reais.
- Destaque riscos e incertezas sustentados pelo estudo ou contexto.
- Use linguagem de atencao sem catastrofismo medico.
- Framing: "riscos reais", "cuidado necessario", "nao descuide".
- Proibido: alarmismo, diagnóstico, vergonha, urgencia falsa, risco inventado.
- Riscos devem estar explicitamente na fonte (artigo, analise, contexto).""",
    }
    ending_rule = (
        "- Para 10 segundos: textoFalado entre 18 e 24 palavras, sem frase final, CTA falado ou despedida."
        if duration_seconds == 10
        else "- Termine com a frase final fornecida no pedido. Nao use outro encerramento padrao."
    )
    return f"""Voce e um roteirista editorial para videos curtos do Dr. Guilherme.
Crie um roteiro estruturado e um texto falado completo a partir da ideia e analise fornecidas.

{tone_guide.get(tone, tone_guide['neutro'])}

REGRAS OBRIGATORIAS PARA TODO TOM:
- Conteudo educativo e nao prescritivo.
- Nao cite doses, nao prometa resultado, nao use cura/milagre/garantia.
- Nao incentive uso de medicamento sem avaliacao individual.
- Separe claramente: achado, limite do estudo, orientacao individual.
- Se o artigo for observacional, nunca afirme causalidade como certeza.
- Quando houver dado numerico, trate como "estudos sugerem/associam", nunca como verdade absoluta.
- Respeite a observacaoCompliance da ideia.
- O texto falado deve ser portugues brasileiro falado, espontaneo, humano, com frases curtas.
- Diga cada informacao uma unica vez. Nao repita listas de riscos, achados ou o gancho com palavras diferentes.
- Quando houver artigo/fonte, dedique a maior parte da fala ao fato, contexto e exemplo da noticia. Reserve o cuidado clinico para uma unica frase curta no fim, imediatamente antes do encerramento.
- Para {duration_seconds} segundos, escreva textoFalado entre {_duration_word_limits(duration_seconds)[0]} e {_duration_word_limits(duration_seconds)[1]} palavras.
- Nunca devolva um resumo curto: desenvolva hook, contexto, explicacao, virada e encerramento.
{ending_rule}
- Responda somente no JSON solicitado."""


@app.post("/api/scripts/naturalize")
def naturalize_script(payload: NaturalizeScriptIn) -> dict:
    """Transforma o roteiro em fala natural somente apos acao explicita do usuario."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Defina ANTHROPIC_API_KEY no arquivo .env para naturalizar com IA.",
        )
    cache_payload = {"promptVersion": "2026-08-07-v1-performance", **payload.model_dump()}
    cached = _ai_cache_get("scripts.naturalize", cache_payload)
    if cached:
        return cached
    import anthropic

    prompt = build_performance_prompt(
        text=payload.text,
        medical_cautions=payload.medicalCautions,
        duration_seconds=payload.durationSeconds,
        cta_mode=payload.ctaMode,
        manual_cta=payload.manualCta or payload.outro,
        recent_ctas=payload.recentCtas,
        video_agent=payload.generationMode in {"video_agent", "cinematic"},
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=1200,
            system=prompt.system,
            output_config={"format": {"type": "json_schema", "schema": _NATURAL_SCRIPT_SCHEMA}},
            messages=[{"role": "user", "content": prompt.user}],
        )
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Claude respondeu {exc.status_code}: {exc.message}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao naturalizar o texto: {exc}")

    raw_text = "".join(getattr(block, "text", "") for block in message.content)
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="A IA nao retornou um JSON valido.")

    performance = normalize_performance_response(
        parsed,
        source_text=payload.text,
        duration_seconds=payload.durationSeconds,
        cta_mode=payload.ctaMode,
        manual_cta=payload.manualCta or payload.outro,
    )
    response = {"ok": True, "text": performance["displayText"], **performance}
    _record_anthropic_usage("scripts.naturalize", model, message)
    _ai_cache_put("scripts.naturalize", cache_payload, response)
    return response


class IdeaForScriptIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    hook: str = Field(default="", max_length=1000)
    angulo: str = Field(default="", max_length=4000)
    tipo: str | None = Field(default=None, max_length=200)
    publicoDor: str | None = Field(default=None, max_length=1000)
    cta: str = Field(default="", max_length=500)
    familia: Literal["medicamento", "comportamento", "metabolismo", "obesidade", "educativo"] = "educativo"
    observacaoCompliance: str = Field(default="", max_length=2000)
    prioridade: Literal["alta", "media", "baixa"] = "media"
    linkOrigem: str | None = Field(default=None, max_length=1000)


class ArticleAnalysisForScriptIn(BaseModel):
    tituloArtigo: str | None = None
    achadoPrincipal: str | None = None
    tipoEstudo: str | None = None
    populacao: str | None = None
    amostra: str | None = None
    seguimento: str | None = None
    numerosChave: list[str] = Field(default_factory=list)
    limitacoes: list[str] = Field(default_factory=list)
    podeFalar: list[str] = Field(default_factory=list)
    naoPodeFalar: list[str] = Field(default_factory=list)


class GenerateScriptIn(BaseModel):
    idea: IdeaForScriptIn
    articleAnalysis: ArticleAnalysisForScriptIn | None = None
    editorialTone: Literal["positivo", "neutro", "apreensivo"] = "neutro"
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    outro: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    requireClaude: bool = False


def _script_risk_for_idea(idea: IdeaForScriptIn) -> str:
    medication_terms = re.search(
        r"glp|mounjaro|ozempic|wegovy|semaglutida|tirzepatida", idea.titulo, re.I
    )
    is_medication = idea.familia == "medicamento" or bool(medication_terms)
    if is_medication:
        return "alto"
    if idea.familia == "comportamento":
        return "alto"
    return "medio"


def _script_generation_prompt(payload: GenerateScriptIn) -> str:
    idea = payload.idea
    analysis = payload.articleAnalysis
    lines = [
        f"IDEIA:",
        f"Titulo: {idea.titulo}",
        f"Hook: {idea.hook or 'nao informado'}",
        f"Angulo/briefing: {idea.angulo or 'nao informado'}",
        f"Publico/Dor: {idea.publicoDor or 'nao informado'}",
        f"CTA sugerido: {idea.cta or 'nao informado'}",
        f"Familia: {idea.familia}",
        f"Observacao de compliance: {idea.observacaoCompliance or 'nenhuma'}",
        f"Prioridade: {idea.prioridade}",
    ]
    if analysis:
        lines.append("\nANALISE CIENTIFICA DO ARTIGO:")
        if analysis.achadoPrincipal:
            lines.append(f"Achado principal: {analysis.achadoPrincipal}")
        if analysis.tipoEstudo:
            lines.append(f"Tipo de estudo: {analysis.tipoEstudo}")
        if analysis.populacao:
            lines.append(f"Populacao: {analysis.populacao}")
        if analysis.amostra:
            lines.append(f"Amostra: {analysis.amostra}")
        if analysis.seguimento:
            lines.append(f"Seguimento: {analysis.seguimento}")
        if analysis.numerosChave:
            lines.append(f"Numeros-chave: {'; '.join(analysis.numerosChave)}")
        if analysis.limitacoes:
            lines.append(f"Limitacoes: {'; '.join(analysis.limitacoes)}")
        if analysis.podeFalar:
            lines.append(f"Pode falar: {'; '.join(analysis.podeFalar)}")
        if analysis.naoPodeFalar:
            lines.append(f"Nao pode falar: {'; '.join(analysis.naoPodeFalar)}")
    minimum_words, maximum_words = _duration_word_limits(payload.durationSeconds)
    word_range = f"{minimum_words} a {maximum_words}"
    lines.append(f"\nDURACAO ALVO: {payload.durationSeconds} segundos ({word_range} palavras)")
    if payload.durationSeconds == 10:
        lines.append("SEM FRASE FINAL: termine diretamente no impacto do hook, sem CTA falado ou despedida.")
        ending_direction = "terminando diretamente no impacto, sem frase final"
    else:
        lines.append(f"FRASE FINAL OBRIGATORIA (ultima frase do texto falado): {payload.outro}")
        ending_direction = "terminando com a frase final obrigatoria"
    lines.append(
        "\nGere titulo, hook, dorConflito, explicacaoSimples, virada, cta, cuidadosMedicos "
        f"e o textoFalado completo (fala unica, pronta para o avatar, {ending_direction})."
    )
    return "\n".join(lines)


def _normalize_generated_outro(text: str, outro: str, *, omit_outro: bool = False) -> str:
    selected = re.sub(r"\s+", " ", outro).strip() or MANDATORY_VIDEO_OUTRO
    body = text.strip()
    for candidate in {selected, MANDATORY_VIDEO_OUTRO}:
        body = re.sub(rf"\s*{re.escape(candidate)}\s*", " ", body, flags=re.I)
    body = re.sub(r"[ \t]+", " ", body).strip().rstrip(" .!?…")
    if omit_outro:
        return f"{body}." if body else ""
    return f"{body}. {selected}" if body else selected


def _manual_script_generation(payload: GenerateScriptIn) -> dict[str, Any]:
    """Fallback local sem Claude: monta roteiro a partir da ideia, sem custo de IA."""
    idea = payload.idea
    analysis = payload.articleAnalysis
    tone = payload.editorialTone

    titulo = idea.titulo.strip() or "Roteiro sem titulo"
    hook = idea.hook.strip() or f"{titulo}: o que os dados realmente mostram."
    dor_conflito = (idea.publicoDor or "").strip() or "Muita gente busca uma resposta simples para um tema que depende de contexto."
    if not dor_conflito.endswith((".", "?")):
        dor_conflito = f"{dor_conflito}."

    if analysis and analysis.achadoPrincipal:
        explicacao = analysis.achadoPrincipal.strip()
    else:
        explicacao = idea.angulo.strip() or f"{titulo} precisa ser explicado com contexto, nao so com uma manchete."

    tone_turn = {
        "positivo": "A parte boa e que esse tipo de achado ajuda a fazer perguntas melhores na proxima consulta, sem prometer resultado igual para todo mundo.",
        "neutro": "O ponto central e separar o que o estudo mostrou do que ainda precisa ser confirmado, sem tirar conclusao apressada.",
        "apreensivo": "O cuidado aqui e real: existem limites e riscos descritos no proprio estudo que merecem atencao antes de qualquer decisao.",
    }.get(tone, "O ponto central e separar o que foi observado do que ainda precisa ser confirmado.")

    cta = idea.cta.strip() or "Procure avaliacao individualizada antes de tirar conclusoes."

    caution_parts = [idea.observacaoCompliance.strip()]
    if analysis and analysis.limitacoes:
        caution_parts.append("Limites do estudo: " + "; ".join(analysis.limitacoes))
    caution_parts.append("Nao prescrever, nao citar dose, nao prometer resultado e reforcar avaliacao individual.")
    cuidados = " ".join(part for part in caution_parts if part)

    texto_falado = " ".join(
        part.strip()
        for part in [hook, dor_conflito, explicacao, tone_turn, cta]
        if part and part.strip()
    )
    texto_falado = _fit_text_to_duration(texto_falado, payload.durationSeconds, payload.outro)

    return {
        "titulo": titulo,
        "hook": hook,
        "dorConflito": dor_conflito,
        "explicacaoSimples": explicacao,
        "virada": tone_turn,
        "cta": cta,
        "cuidadosMedicos": cuidados,
        "textoFalado": texto_falado,
    }


@app.post("/api/scripts/generate")
def generate_script(payload: GenerateScriptIn) -> dict:
    """Gera roteiro estruturado + texto falado completo a partir de uma ideia ja escolhida.

    Chamada paga unica: o tom editorial (positivo/neutro/apreensivo) e escolhido
    pelo usuario ANTES desta chamada, entao nunca geramos os tres tons de uma vez.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        if payload.requireClaude:
            raise HTTPException(
                status_code=503,
                detail="Claude não está configurado. Nenhuma ideia ou roteiro foi salvo.",
            )
        script = _manual_script_generation(payload)
        return {"ok": True, "provider": "fallback", "script": script}

    cache_payload = {
        "promptVersion": SCRIPT_GENERATION_PROMPT_VERSION,
        **payload.model_dump(),
    }
    cached = _ai_cache_get("scripts.generate", cache_payload)
    if cached:
        return cached

    import anthropic

    prompt = _script_generation_prompt(payload)
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=1400,
            system=_script_generation_system(payload.editorialTone, payload.durationSeconds),
            output_config={"format": {"type": "json_schema", "schema": _SCRIPT_GENERATION_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        script = json.loads(raw_text)
    except anthropic.APIStatusError as exc:
        if payload.requireClaude:
            raise HTTPException(
                status_code=502,
                detail=f"Claude respondeu {exc.status_code}. O roteiro não foi salvo.",
            )
        script = _manual_script_generation(payload)
        return {"ok": True, "provider": "fallback", "script": script}
    except Exception as exc:
        if payload.requireClaude:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao gerar o roteiro com Claude: {exc}. Nenhum dado foi salvo.",
            )
        script = _manual_script_generation(payload)
        return {"ok": True, "provider": "fallback", "script": script}

    script["textoFalado"], narration_repaired = _repair_script_narration(script, payload)
    if payload.durationSeconds == 10:
        script["cta"] = ""

    quality_issues = _narration_quality_issues(
        script["textoFalado"], payload.durationSeconds, payload.outro
    )
    if quality_issues:
        detail = "; ".join(quality_issues)
        if payload.requireClaude:
            raise HTTPException(
                status_code=502,
                detail=f"O roteiro do Claude não passou pela validação de fala: {detail}. Nenhum dado foi salvo.",
            )
        script = _manual_script_generation(payload)
        return {"ok": True, "provider": "fallback", "script": script}

    response = {
        "ok": True,
        "provider": "claude",
        "script": script,
        "repairApplied": narration_repaired,
    }
    _record_anthropic_usage("scripts.generate", model, message)
    _ai_cache_put("scripts.generate", cache_payload, response)
    return response


def _find_script(script_id: str) -> dict[str, Any]:
    snapshot = _load_snapshot()
    scripts = map_scripts(snapshot.get("sheets", {}).get("roteiros", []))
    script = next((item for item in scripts if item["id"] == script_id), None)
    if not script:
        raise HTTPException(status_code=404, detail="Roteiro nao encontrado no snapshot.")
    if not _script_text(script):
        raise HTTPException(status_code=400, detail="O roteiro nao possui texto para gerar o video.")
    return script


def _paid_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _authorize_paid_generation(
    *,
    script_id: str,
    duration_seconds: int,
    expected_script_revision: int | None,
    expected_final_speech_hash: str | None,
    contract_version: str | None,
    requested_speech: str | None,
    ai_operation_in_flight: bool,
    final_confirmed: bool,
) -> dict[str, Any]:
    """Única autoridade para gate/versionamento antes de qualquer reserva paga."""

    script = _find_script(script_id)
    editor_state = _script_editor_state(script_id, script)
    persisted_speech = _canonical_script_speech(script)
    persisted_hash = editor_state.get("finalSpeechHash") or (
        hash_text(persisted_speech) if persisted_speech else None
    )
    script_revision = int(editor_state.get("scriptRevision") or (1 if persisted_speech else 0))
    version = validate_paid_version(
        persisted_speech=persisted_speech,
        script_revision=script_revision,
        persisted_speech_hash=persisted_hash,
        expected_script_revision=expected_script_revision,
        expected_final_speech_hash=expected_final_speech_hash,
        expected_contract_version=contract_version,
    )
    if not version.allowed:
        status_code = 409 if version.code and "CONFLICT" in version.code else 422
        raise _paid_error(
            status_code,
            version.code or "PAID_GENERATION_BLOCKED",
            version.message or "A geração foi bloqueada pelo estado do roteiro.",
        )

    approval_has_version = (
        "approvedScriptRevision" in editor_state
        or "approvedFinalSpeechHash" in editor_state
    )
    approved = bool(editor_state.get("humanReviewApproved"))
    if approval_has_version:
        approved = bool(
            approved
            and editor_state.get("approvedScriptRevision") == script_revision
            and editor_state.get("approvedFinalSpeechHash") == version.final_speech_hash
        )
    authoritative_state = {**editor_state, "humanReviewApproved": approved}
    review_status = _resolved_medical_review_status(script, authoritative_state)
    exact_saved_speech = bool(
        requested_speech is None
        or normalize_editor_text(requested_speech)
        == normalize_editor_text(persisted_speech)
    )
    gate = evaluate_generation_gate(
        speech=persisted_speech,
        duration_seconds=duration_seconds,
        ai_operation_in_flight=ai_operation_in_flight,
        schema_valid=bool(editor_state.get("schemaValid", False)),
        technical_error=editor_state.get("technicalError"),
        medical_review=review_status,
        human_review_approved=approved,
        script_status=str(script.get("status") or ""),
        final_saved=exact_saved_speech,
        final_confirmed=final_confirmed,
    )
    if not gate.allowed:
        reason = gate.reasons[0]
        raise _paid_error(422, reason["code"].upper(), reason["message"])
    return {
        "script": script,
        "editorState": authoritative_state,
        "speech": persisted_speech,
        "scriptRevision": script_revision,
        "finalSpeechHash": version.final_speech_hash,
        "contractVersion": version.contract_version,
        "medicalReviewStatus": review_status,
    }


def _heygen_wallet(command: str) -> tuple[float | None, str | None]:
    proc = subprocess.run(
        [command, "user", "me", "get"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    response = _read_json_output(proc)
    wallet = _find_value(response, "wallet") or {}
    if not isinstance(wallet, dict):
        return None, None
    balance = wallet.get("remaining_balance")
    currency = wallet.get("currency")
    return (float(balance) if isinstance(balance, (int, float)) else None, currency if isinstance(currency, str) else None)


@app.get("/api/ai-costs")
def ai_costs() -> dict:
    """Retorna o saldo real dos provedores de IA conectados ao projeto."""
    heygen: dict[str, Any] = {
        "id": "heygen",
        "name": "HeyGen",
        "description": "Videos com avatar e voz",
        "status": "conectado",
        "currency": "USD",
        "remainingBalance": None,
        "trackedSpend": 0.0,
        "note": "O custo e registrado pela diferenca de saldo em cada novo video.",
    }
    try:
        command = _heygen_cli()
        balance, currency = _heygen_wallet(command)
        heygen["remainingBalance"] = balance
        if currency:
            heygen["currency"] = currency.upper()
        heygen["trackedSpend"] = round(
            sum(float(job.get("costUsd", 0)) for job in _load_video_jobs()),
            2,
        )
    except (HTTPException, OSError, RuntimeError, subprocess.TimeoutExpired):
        heygen["status"] = "indisponivel"
        heygen["note"] = "Nao foi possivel consultar o saldo agora."

    anthropic_usage = _anthropic_usage_summary()
    claude: dict[str, Any] = {
        "id": "anthropic",
        "name": "Claude",
        "description": "Ideias, artigos, naturalizacao e packs de conteudo",
        "status": "conectado" if os.getenv("ANTHROPIC_API_KEY") else "nao_conectado",
        "currency": "USD",
        "remainingBalance": None,
        "trackedSpend": anthropic_usage["estimatedCostUsd"],
        "calls": anthropic_usage["calls"],
        "inputTokens": anthropic_usage["inputTokens"],
        "outputTokens": anthropic_usage["outputTokens"],
        "cacheReadTokens": anthropic_usage["cacheReadTokens"],
        "cacheWriteTokens": anthropic_usage["cacheWriteTokens"],
        "note": "Estimativa calculada pelos tokens retornados pela API. O saldo pre-pago fica no Console Anthropic.",
    }
    return {
        "updatedAt": _now(),
        "providers": [heygen, claude],
    }


def _safe_video_provider_error(exc: Exception) -> str:
    """Retorna diagnóstico operacional sem propagar resposta bruta do provedor."""

    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired, requests.Timeout)):
        return "Tempo limite ao comunicar com a HeyGen."
    if status_code == 429:
        return "A HeyGen atingiu o limite temporário de requisições."
    if isinstance(status_code, int) and status_code >= 500:
        return "A HeyGen está temporariamente indisponível."
    if isinstance(exc, (ConnectionError, OSError, requests.ConnectionError)):
        return "A conexão com a HeyGen foi interrompida."
    if isinstance(exc, HTTPException) and exc.status_code < 500:
        return str(exc.detail)[:500]
    return "Falha ao comunicar com a HeyGen."


def _mark_video_submission_failure(job: dict[str, Any], exc: Exception) -> dict[str, Any]:
    current = _job_store().get("video", str(job["id"])) or job
    current["status"] = "erro"
    current["progresso"] = 0
    current["erro"] = _safe_video_provider_error(exc)
    current["retrySafe"] = current.get("submissionState") != "submitting"
    current["submissionState"] = (
        "failed_safe" if current["retrySafe"] else "submission_uncertain"
    )
    current["atualizadoEm"] = _now()
    _job_store().upsert("video", current)
    LOGGER.warning(
        "video_provider_error job_id=%s script_id=%s state=%s provider=heygen error_type=%s",
        current.get("id"),
        current.get("scriptId"),
        current.get("submissionState"),
        type(exc).__name__,
    )
    return current


@app.post("/api/videos")
def create_video(payload: VideoCreateIn) -> dict:
    """Cria um job real no HeyGen somente apos o clique de enviar para producao."""
    LOGGER.info(
        "Video creation requested: script_id=%s mode=%s force_new_version=%s",
        payload.scriptId,
        payload.generationMode,
        payload.forceNewVersion,
    )
    now = _now()
    cinematic_prompt = (
        _clean_cinematic_prompt(payload.cinematicPrompt)
        if payload.generationMode == "cinematic"
        else ""
    )
    if payload.generationMode == "cinematic" and not cinematic_prompt:
        raise HTTPException(
            status_code=422,
            detail="Escreva a direção cinematic antes de enviar este modo para produção.",
        )
    if payload.generationMode == "direct" and (
        payload.styleId or payload.brandKitId or payload.videoAgentMode != "generate"
    ):
        raise HTTPException(
            status_code=422,
            detail="styleId, brandKitId e modo chat pertencem somente ao Video Agent.",
        )
    provider_capabilities: dict[str, Any] | None = None
    if payload.generationMode in {"video_agent", "cinematic"}:
        provider_capabilities = _heygen_capabilities()
        try:
            validate_video_agent_options(
                provider_capabilities,
                style_id=payload.styleId,
                brand_kit_id=payload.brandKitId,
                mode=payload.videoAgentMode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Preserve the historical "existing video" response for callers that have
    # not supplied any editable text. Requests with production text always go
    # through the stricter pre-reservation compliance path below.
    if not payload.forceNewVersion and not any(
        (value or "").strip() for value in (payload.narrationText, payload.displayText, payload.spokenText)
    ):
        existing = next(
            (
                job
                for job in _job_store().list("video")
                if job.get("scriptId") == payload.scriptId
                and (job.get("status") != "erro" or not bool(job.get("retrySafe")))
            ),
            None,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Este roteiro ja possui um video. Abra a producao existente ou use 'Criar nova versao' para gerar outro video.",
            )
    with _paid_generation_lock(payload.scriptId):
        script = _find_script(payload.scriptId)
        requested_display_text = performance_display_text(
            payload.displayText or payload.narrationText or _canonical_script_speech(script)
        )
        authorization = _authorize_paid_generation(
            script_id=payload.scriptId,
            duration_seconds=payload.durationSeconds,
            expected_script_revision=payload.expectedScriptRevision,
            expected_final_speech_hash=payload.expectedFinalSpeechHash,
            contract_version=payload.contractVersion,
            requested_speech=requested_display_text,
            ai_operation_in_flight=payload.aiOperationInFlight,
            final_confirmed=payload.finalConfirmed,
        )
        script = authorization["script"]
        final_display_text, final_spoken_text = _finalize_video_texts(payload, script)
        assessment = duration_assessment(final_display_text, payload.durationSeconds)
        LOGGER.info(
            "generation_gate script_id=%s revision=%s preset=%s words=%s duration_status=%s medical_review=%s allowed=true reason_code=none",
            payload.scriptId,
            authorization["scriptRevision"],
            payload.durationSeconds,
            assessment.wordCount,
            assessment.status,
            authorization["medicalReviewStatus"],
        )
        idempotency_key = payload.idempotencyKey or _production_configuration_key(
            payload, final_display_text, final_spoken_text
        )
        if payload.forceNewVersion and not payload.idempotencyKey:
            idempotency_key = f"{idempotency_key}:version:{uuid.uuid4().hex}"
        production_settings = {
            "avatarId": payload.avatarId,
            "voiceId": payload.voiceId,
            "orientation": payload.orientation,
            "durationSeconds": payload.durationSeconds,
            "speechMode": payload.speechMode,
            "voiceMood": payload.voiceMood,
            "generationMode": payload.generationMode,
            "ctaMode": payload.ctaMode,
            "captions": payload.captions,
            "optimizePronunciation": payload.optimizePronunciation,
            "styleId": payload.styleId,
            "brandKitId": payload.brandKitId,
            "videoAgentMode": payload.videoAgentMode,
            **(
                {
                    "providerCapabilitiesVersion": provider_capabilities["capabilitiesVersion"],
                    "providerCapabilities": {
                        key: value
                        for key, value in provider_capabilities.items()
                        if key != "checkedAt"
                    },
                }
                if provider_capabilities
                else {}
            ),
            "narrationText": final_display_text,
            "displayText": final_display_text,
            "spokenText": final_spoken_text,
            **({"cinematicPrompt": cinematic_prompt} if cinematic_prompt else {}),
            "outroText": payload.outroText,
        }
        fingerprint = request_fingerprint(
            {
                "scriptId": payload.scriptId,
                "scriptRevision": authorization["scriptRevision"],
                "finalSpeechHash": authorization["finalSpeechHash"],
                "contractVersion": authorization["contractVersion"],
                "generationMode": payload.generationMode,
                "productionSettings": production_settings,
            }
        )
        reserved_job = {
            "id": f"v-{uuid.uuid4().hex[:12]}",
            "scriptId": payload.scriptId,
            "scriptRevision": authorization["scriptRevision"],
            "finalSpeechHash": authorization["finalSpeechHash"],
            "contractVersion": authorization["contractVersion"],
            "requestFingerprint": fingerprint,
            "status": "fila",
            "provider": "heygen",
            "progresso": 0,
            "criadoEm": now,
            "atualizadoEm": now,
            "submissionState": "reserved",
            "productionSettings": production_settings,
        }
        job, reservation = _job_store().reserve_video(
            reserved_job,
            idempotency_key=idempotency_key,
            force_new_version=payload.forceNewVersion,
        )
    LOGGER.info(
        "Video job reservation: script_id=%s job_id=%s result=%s",
        payload.scriptId,
        job.get("id"),
        reservation,
    )
    if reservation == "duplicate":
        return {"ok": True, "job": job, "deduplicated": True}
    if reservation == "conflict":
        if job.get("idempotencyKey") == idempotency_key:
            raise _paid_error(
                409,
                "IDEMPOTENCY_KEY_CONFLICT",
                "Esta chave de idempotência já foi usada com outro payload.",
            )
        if job.get("submissionState") in {"reserved", "submitting", "submission_uncertain"}:
            raise _paid_error(
                409,
                "SCRIPT_GENERATION_IN_PROGRESS",
                (
                    "Ja existe um envio deste roteiro em andamento ou aguardando reconciliacao. "
                    "Nenhuma nova chamada foi feita ao HeyGen."
                ),
            )
        raise _paid_error(
            409,
            "SCRIPT_ALREADY_GENERATED",
            (
                "Este roteiro ja possui um video. Abra a producao existente ou use "
                "'Criar nova versao' para gerar outro video."
            ),
        )
    try:
        result = _create_video_job(
            payload,
            reserved_job,
            script=script,
            final_texts=(final_display_text, final_spoken_text),
        )
        LOGGER.info(
            "Video submitted: script_id=%s job_id=%s remote_video_id=%s",
            payload.scriptId,
            result["job"].get("id"),
            result["job"].get("remoteVideoId"),
        )
        return result
    except Exception as exc:
        _mark_video_submission_failure(reserved_job, exc)
        raise


def _create_video_job(
    payload: VideoCreateIn,
    job: dict[str, Any],
    *,
    script: dict[str, Any] | None = None,
    final_texts: tuple[str, str] | None = None,
) -> dict:
    script = script or _find_script(payload.scriptId)
    if script.get("status") != "aprovado_clinicamente":
        raise HTTPException(
            status_code=409,
            detail="O roteiro precisa concluir a revisão de fala e estar marcado como Pronto antes do HeyGen.",
        )
    final_display_text, final_spoken_text = final_texts or _finalize_video_texts(payload, script)
    cinematic_prompt = (
        _clean_cinematic_prompt(payload.cinematicPrompt)
        if payload.generationMode == "cinematic"
        else ""
    )
    if payload.generationMode == "cinematic" and not cinematic_prompt:
        raise HTTPException(
            status_code=422,
            detail="Escreva a direção cinematic antes de enviar este modo para produção.",
        )
    command = _heygen_cli()
    try:
        balance_before, currency_before = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_before, currency_before = None, None
    # allow_cache=False: este e o momento de gastar producao real na HeyGen, entao
    # o avatar escolhido precisa ser validado contra a lista ao vivo, nunca contra
    # um cache que pode estar desatualizado (avatar removido ou criado recentemente).
    _, private_looks, _from_cache = _private_avatar_library(command, allow_cache=False)
    ready_looks = [look for look in private_looks if look.get("status") == "completed"]
    avatar_id = payload.avatarId
    selected_look = next((look for look in ready_looks if look.get("id") == avatar_id), None)
    voice_id = payload.voiceId or (default_voice_id(selected_look or {}) or _heygen_default_voice_id())
    allowed_avatar_ids = {look.get("id") for look in ready_looks}
    if avatar_id not in allowed_avatar_ids:
        raise HTTPException(status_code=400, detail="Selecione um avatar privado pronto.")

    existing_profile = _production_profile(payload.scriptId) or {}
    _save_production_profile(
        {
            "scriptId": payload.scriptId,
            "avatarId": avatar_id,
            "voiceId": voice_id,
            "speechMode": payload.speechMode,
            "voiceMood": payload.voiceMood,
            "generationMode": payload.generationMode,
            "avatarMode": existing_profile.get("avatarMode", "single"),
            "avatarSetId": existing_profile.get("avatarSetId"),
            "primaryAvatarId": existing_profile.get("primaryAvatarId") or avatar_id,
            "musicTrackId": existing_profile.get("musicTrackId"),
            "musicVolume": existing_profile.get("musicVolume", 0.12),
            "cinematicPrompt": (
                cinematic_prompt
                if payload.generationMode == "cinematic"
                else existing_profile.get("cinematicPrompt", "")
            ),
        }
    )
    job["productionSettings"]["avatarId"] = avatar_id
    job["productionSettings"]["voiceId"] = voice_id
    job["productionSettings"]["voiceMood"] = payload.voiceMood
    job["productionSettings"]["displayText"] = final_display_text
    job["productionSettings"]["spokenText"] = final_spoken_text
    if payload.generationMode == "cinematic":
        job["productionSettings"]["cinematicPrompt"] = cinematic_prompt
    else:
        job["productionSettings"].pop("cinematicPrompt", None)
    captions_need_normalization = payload.captions and final_display_text != final_spoken_text
    job["productionSettings"]["captionStrategy"] = (
        "sidecar_srt_normalized" if captions_need_normalization else "sidecar_srt"
    ) if payload.captions else "disabled"
    job["submissionState"] = "submitting"
    job["atualizadoEm"] = _now()
    _job_store().upsert("video", job)

    if payload.generationMode == "direct":
        generation_mode = "direct"
        direct_voice_settings = voice_settings(payload.speechMode, payload.voiceMood)
        voice_speed = float(direct_voice_settings["speed"])
        job["productionSettings"]["generationMode"] = generation_mode
        job["productionSettings"]["voiceSpeed"] = voice_speed
        _job_store().upsert("video", job)
        direct_payload = _direct_video_payload(
            script=script,
            narration_text=final_spoken_text,
            avatar_id=avatar_id,
            voice_id=voice_id,
            orientation=payload.orientation,
            speech_mode=payload.speechMode,
            voice_mood=payload.voiceMood,
            captions=payload.captions,
            optimize_pronunciation=payload.optimizePronunciation,
            caption_source_matches_spoken=not captions_need_normalization,
        )
        response = _run_heygen_json(
            command,
            ["video", "create"],
            payload=direct_payload,
            timeout=60,
        )
        session_id = None
        video_id = _find_value(response, "video_id", "videoId", "id")
        if not video_id:
            raise HTTPException(status_code=502, detail="HeyGen nao retornou o identificador do video.")
    else:
        generation_mode = payload.generationMode
        job["productionSettings"]["generationMode"] = generation_mode
        job["productionSettings"]["voiceSpeed"] = speech_speed(payload.speechMode)
        _job_store().upsert("video", job)
        # Video Agent e Cinematic usam o mesmo transporte, mas prompts isolados:
        # o modo comum recebe só fala + performance; apenas Cinematic recebe
        # direção visual. Scene Plan, Visual Plan e slides nunca entram aqui.
        agent_text, agent_input_mode = _compose_video_agent_prompt(
            final_display_text,
            cinematic_prompt if payload.generationMode == "cinematic" else None,
            payload.durationSeconds,
            payload.voiceMood,
        )
        if not agent_text:
            raise HTTPException(status_code=400, detail="A fala final não pode estar vazia para o Video Agent.")
        job["productionSettings"]["agentInput"] = agent_input_mode
        _job_store().upsert("video", job)
        capabilities = job["productionSettings"].get("providerCapabilities")
        if not isinstance(capabilities, dict):
            raise HTTPException(
                status_code=409,
                detail=(
                    "O registro de capabilities usado na reserva deste job não está disponível. "
                    "Crie uma nova reserva antes de enviar ao HeyGen."
                ),
            )
        try:
            args = video_agent_create_args(
                capabilities,
                prompt=agent_text,
                avatar_id=avatar_id,
                voice_id=voice_id,
                orientation=payload.orientation,
                style_id=payload.styleId,
                brand_kit_id=payload.brandKitId,
                mode=payload.videoAgentMode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        response = _run_heygen_json(command, args, timeout=60)
        session_id = _find_value(response, "session_id", "sessionId")
        video_id = _find_value(response, "video_id", "videoId", "id")
        if not session_id:
            raise HTTPException(status_code=502, detail="HeyGen nao retornou o identificador da sessao.")

    job["status"] = "fila"
    job["submissionState"] = "submitted"
    job["atualizadoEm"] = _now()
    if session_id:
        job["remoteSessionId"] = session_id
    job["remoteVideoId"] = video_id or None
    _job_store().upsert("video", job)
    try:
        balance_after, currency_after = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_after, currency_after = None, None
    if balance_before is not None and balance_after is not None and balance_after <= balance_before:
        job["costUsd"] = round(balance_before - balance_after, 2)
        job["currency"] = (currency_after or currency_before or "USD").upper()
    _job_store().upsert("video", job)
    return {"ok": True, "job": job}


@app.post("/api/videos/preview")
def create_video_preview(payload: VideoPreviewCreateIn) -> dict:
    """Gera uma previa tecnica de 10s sempre pelo Direct Avatar."""
    now = _now()
    with _paid_generation_lock(payload.scriptId):
        script = _find_script(payload.scriptId)
        editor_state = _script_editor_state(payload.scriptId, script)
        selected_duration = int(editor_state.get("durationSeconds") or 45)
        authorization = _authorize_paid_generation(
            script_id=payload.scriptId,
            duration_seconds=selected_duration,
            expected_script_revision=payload.expectedScriptRevision,
            expected_final_speech_hash=payload.expectedFinalSpeechHash,
            contract_version=payload.contractVersion,
            requested_speech=None,
            ai_operation_in_flight=False,
            final_confirmed=payload.finalConfirmed,
        )
        script = authorization["script"]
        authoritative_preview_payload = payload.model_copy(
            update={"displayText": authorization["speech"], "spokenText": None}
        )
        preview_display_text, preview_spoken_text = _finalize_preview_texts(
            authoritative_preview_payload
        )
        idempotency_key = payload.idempotencyKey or _preview_configuration_key(
            payload, preview_display_text, preview_spoken_text
        )
        production_settings = {
            "avatarId": payload.avatarId,
            "voiceId": payload.voiceId,
            "orientation": payload.orientation,
            "durationSeconds": 10,
            "speechMode": payload.speechMode,
            "voiceMood": payload.voiceMood,
            "generationMode": "direct",
            "captions": payload.captions,
            "optimizePronunciation": payload.optimizePronunciation,
            "displayText": preview_display_text,
            "spokenText": preview_spoken_text,
        }
        reserved_job = {
            "id": f"vp-{uuid.uuid4().hex[:12]}",
            "scriptId": payload.scriptId,
            "scriptRevision": authorization["scriptRevision"],
            "finalSpeechHash": authorization["finalSpeechHash"],
            "contractVersion": authorization["contractVersion"],
            "requestFingerprint": request_fingerprint(
                {
                    "scriptId": payload.scriptId,
                    "scriptRevision": authorization["scriptRevision"],
                    "finalSpeechHash": authorization["finalSpeechHash"],
                    "contractVersion": authorization["contractVersion"],
                    "generationMode": "preview",
                    "productionSettings": production_settings,
                }
            ),
            "status": "fila",
            "provider": "heygen",
            "progresso": 0,
            "criadoEm": now,
            "atualizadoEm": now,
            "submissionState": "reserved",
            "isPreview": True,
            "productionSettings": production_settings,
        }
        job, reservation = _job_store().reserve(
            "video",
            reserved_job,
            idempotency_key=idempotency_key,
        )
    if reservation == "duplicate":
        return {"ok": True, "job": job, "deduplicated": True}
    if reservation == "conflict":
        raise _paid_error(
            409,
            "IDEMPOTENCY_KEY_CONFLICT",
            "Esta chave de idempotência já foi usada com outro payload.",
        )

    try:
        command = _heygen_cli()
        _, private_looks, _from_cache = _private_avatar_library(command, allow_cache=False)
        ready_looks = [look for look in private_looks if look.get("status") == "completed"]
        allowed_avatar_ids = {look.get("id") for look in ready_looks}
        if payload.avatarId not in allowed_avatar_ids:
            raise HTTPException(status_code=400, detail="Selecione um avatar privado pronto.")
        existing_profile = _production_profile(payload.scriptId) or {}
        _save_production_profile(
            {
                "scriptId": payload.scriptId,
                "avatarId": payload.avatarId,
                "voiceId": payload.voiceId,
                "speechMode": payload.speechMode,
                "voiceMood": payload.voiceMood,
                "generationMode": "direct",
                "avatarMode": existing_profile.get("avatarMode", "single"),
                "avatarSetId": existing_profile.get("avatarSetId"),
                "primaryAvatarId": existing_profile.get("primaryAvatarId") or payload.avatarId,
                "musicTrackId": existing_profile.get("musicTrackId"),
                "musicVolume": existing_profile.get("musicVolume", 0.12),
                "cinematicPrompt": existing_profile.get("cinematicPrompt", ""),
            }
        )
        job["submissionState"] = "submitting"
        job["productionSettings"]["generationMode"] = "direct"
        job["productionSettings"]["voiceSpeed"] = float(
            voice_settings(payload.speechMode, payload.voiceMood)["speed"]
        )
        job["productionSettings"]["captionStrategy"] = (
            "sidecar_srt_normalized"
            if payload.captions and preview_display_text != preview_spoken_text
            else "sidecar_srt" if payload.captions else "disabled"
        )
        _job_store().upsert("video", job)
        direct_payload = _direct_video_payload(
            script=script,
            narration_text=preview_spoken_text,
            avatar_id=payload.avatarId,
            voice_id=payload.voiceId,
            orientation=payload.orientation,
            speech_mode=payload.speechMode,
            voice_mood=payload.voiceMood,
            captions=payload.captions,
            optimize_pronunciation=False,
            caption_source_matches_spoken=preview_display_text == preview_spoken_text,
        )
        response = _run_heygen_json(command, ["video", "create"], payload=direct_payload, timeout=60)
        video_id = _find_value(response, "video_id", "videoId", "id")
        if not video_id:
            raise HTTPException(status_code=502, detail="HeyGen nao retornou o identificador da previa.")
        job["status"] = "fila"
        job["submissionState"] = "submitted"
        job["remoteVideoId"] = video_id
        job["atualizadoEm"] = _now()
        _job_store().upsert("video", job)
        return {"ok": True, "job": job}
    except Exception as exc:
        _mark_video_submission_failure(reserved_job, exc)
        raise


@app.post("/api/videos/{job_id}/refresh")
def refresh_video(job_id: str) -> dict:
    """Consulta o HeyGen e atualiza um job local ja criado."""
    command = _heygen_cli()
    job = _job_store().get("video", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de video nao encontrado.")
    settings = job.get("productionSettings") or {}
    generation_mode = settings.get("generationMode")
    session_id = job.get("remoteSessionId")
    video_id = job.get("remoteVideoId")
    if generation_mode == "direct" or (not session_id and video_id):
        if not video_id:
            raise HTTPException(status_code=500, detail="Job sem video HeyGen.")
        response = _run_heygen_json(
            command,
            ["video", "get", str(video_id)],
            timeout=45,
        )
    else:
        if not session_id:
            raise HTTPException(status_code=500, detail="Job sem sessao HeyGen.")
        response = _run_heygen_json(
            command,
            ["video-agent", "get", str(session_id)],
            timeout=45,
        )
    status, progress = _job_status(response)
    LOGGER.info(
        "Video status refreshed: job_id=%s status=%s progress=%s",
        job_id,
        status,
        progress,
    )
    job["status"] = status
    job["progresso"] = progress
    job["atualizadoEm"] = _now()
    job["remoteVideoId"] = _find_value(response, "video_id", "videoId") or job.get("remoteVideoId")
    refreshed_video_url = _find_value(
        response,
        "video_url",
        "videoUrl",
        "video_page_url",
        "videoPageUrl",
    )
    if refreshed_video_url:
        job["videoUrl"] = refreshed_video_url
        job["remoteVideoUrl"] = refreshed_video_url
    job["thumbnailUrl"] = _find_value(response, "thumbnail_url", "thumbnailUrl") or job.get("thumbnailUrl")
    caption_srt = _find_value(response, "caption_srt", "captionSrt", "srt")
    if isinstance(caption_srt, str) and caption_srt.strip():
        # Keep a corrected sidecar ready for a future local burn-in pipeline.
        job["captionSrt"] = normalize_caption_srt(caption_srt)
    caption_srt_url = _find_value(response, "caption_url", "captionUrl", "srt_url", "srtUrl")
    if caption_srt_url:
        job["captionSrtUrl"] = caption_srt_url
    duration = _find_value(response, "duration", "duration_seconds", "durationSeconds")
    if duration not in (None, ""):
        try:
            job["duracaoSegundos"] = round(float(duration), 2)
        except (TypeError, ValueError):
            pass
    if job.get("remoteVideoId") and not job.get("videoUrl") and generation_mode != "direct":
        try:
            video_details = _run_heygen_json(
                command,
                ["video", "get", str(job["remoteVideoId"])],
                timeout=45,
            )
        except HTTPException:
            video_details = {}
        job["videoUrl"] = _find_value(video_details, "video_url", "videoUrl") or job.get("videoUrl")
        job["thumbnailUrl"] = _find_value(video_details, "thumbnail_url", "thumbnailUrl") or job.get("thumbnailUrl")
    if status == "erro":
        job["erro"] = str(
            _find_value(
                response,
                "failure_message",
                "failureMessage",
                "error",
                "message",
                "detail",
            )
            or "HeyGen nao concluiu o video."
        )
    job["submissionState"] = "completed" if status == "pronto" else "processing"
    _archive_completed_video(job)
    _job_store().upsert("video", job)
    composed_job = None
    if job.get("isScene") and job.get("status") == "pronto":
        try:
            composed_job = _compose_final_video_if_ready(str(job.get("scriptId") or ""))
        except HTTPException:
            pass
    return {"ok": True, "job": job, "composedJob": composed_job}


@app.get("/api/videos/{job_id}/download")
def download_video(job_id: str):
    """Transmite o MP4 pronto do HeyGen como download com nome amigavel."""
    job = _job_store().get("video", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video nao encontrado.")
    if _local_output_path(job.get("outputPath")):
        return _composed_video_file_response(job, download=True)
    video_url = str(job.get("remoteVideoUrl") or job.get("videoUrl") or "")
    parsed = urlparse(video_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "heygen.ai" or hostname.endswith(".heygen.ai")
    ):
        raise HTTPException(status_code=409, detail="O arquivo do HeyGen ainda nao esta disponivel.")

    try:
        response = requests.get(video_url, stream=True, timeout=(15, 300))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Nao foi possivel baixar o video do HeyGen.") from exc

    try:
        script = _find_script(str(job.get("scriptId") or ""))
        base_name = str(script.get("titulo") or "video")
    except HTTPException:
        base_name = "video"
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", _norm(base_name)).strip("-") or "video"

    def stream_file():
        try:
            yield from response.iter_content(chunk_size=1024 * 1024)
        finally:
            response.close()

    return StreamingResponse(
        stream_file(),
        media_type=response.headers.get("content-type", "video/mp4"),
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.mp4"'},
    )


@app.get("/api/videos/{job_id}/file")
def video_file(job_id: str) -> FileResponse:
    job = _job_store().get("video", job_id)
    if not job or not _local_output_path(job.get("outputPath")):
        raise HTTPException(status_code=404, detail="Vídeo local não encontrado.")
    return _composed_video_file_response(job, download=False)


class PostProductionCreateIn(BaseModel):
    videoJobId: str = Field(min_length=1, max_length=160)
    autoRender: bool = False


class PostProductionEventUpdateIn(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    enabled: bool | None = None
    visualText: str | None = Field(default=None, max_length=100)
    interactionType: Literal[
        "none", "caption_emphasis", "kinetic_text", "progressive_list", "supporting_visual", "cta_card"
    ] | None = None
    reviewStatus: Literal["pending", "approved", "rejected"] | None = None


class PostProductionEventsIn(BaseModel):
    events: list[PostProductionEventUpdateIn] = Field(max_length=100)


def _launch_post_production_analysis(job_id: str) -> None:
    def analyze() -> None:
        store = _job_store()
        analyze_post_production(
            store=store,
            job_id=job_id,
            output_root=POST_PRODUCTION_OUTPUTS,
            project_root=ROOT,
            cache_get=_ai_cache_get,
            cache_put=_ai_cache_put,
            record_usage=_record_anthropic_usage,
        )
        current = store.get("post_production", job_id)
        if not current or not current.get("autoRender") or current.get("status") != "needs_review":
            return
        current.update(
            status="rendering_preview",
            progresso=84,
            etapa="Aplicando edição elegante",
            atualizadoEm=_now(),
        )
        store.upsert("post_production", current)
        _launch_post_production_render(job_id)

    worker = threading.Thread(
        target=analyze,
        daemon=True,
        name=f"post-production-analysis-{job_id}",
    )
    worker.start()


def _launch_post_production_render(job_id: str) -> None:
    def render() -> None:
        try:
            render_post_production_preview(
                store=_job_store(),
                job_id=job_id,
                output_root=POST_PRODUCTION_OUTPUTS,
            )
        except Exception as exc:
            current = _job_store().get("post_production", job_id)
            if current and current.get("status") != "cancelled":
                current.update(
                    status="failed",
                    etapa="Falha ao renderizar prévia",
                    erro=str(exc)[-1200:],
                    atualizadoEm=_now(),
                )
                _job_store().upsert("post_production", current)

    threading.Thread(
        target=render,
        daemon=True,
        name=f"post-production-render-{job_id}",
    ).start()


@app.post("/api/post-production")
def create_post_production(payload: PostProductionCreateIn) -> dict:
    video_job = _job_store().get("video", payload.videoJobId)
    if not video_job or video_job.get("status") != "pronto" or not (
        video_job.get("videoUrl") or _local_output_path(video_job.get("outputPath"))
    ):
        raise HTTPException(status_code=409, detail="A pós-produção exige um vídeo pronto.")
    POST_PRODUCTION_OUTPUTS.mkdir(parents=True, exist_ok=True)
    temporary = POST_PRODUCTION_OUTPUTS / f"incoming-{uuid.uuid4().hex}.mp4"
    try:
        _copy_or_download_video(video_job, temporary)
        key = post_production_idempotency_key(temporary)
        now = _now()
        job_id = f"post-{uuid.uuid4().hex[:16]}"
        job = {
            "id": job_id,
            "kind": "post_production",
            "videoJobId": payload.videoJobId,
            "scriptId": video_job.get("scriptId"),
            "status": "queued",
            "progresso": 2,
            "etapa": "Na fila para análise",
            "autoRender": payload.autoRender,
            "criadoEm": now,
            "atualizadoEm": now,
        }
        reserved, reservation = _job_store().reserve(
            "post_production",
            job,
            idempotency_key=key,
        )
        if reservation == "duplicate":
            if payload.autoRender and not reserved.get("autoRender"):
                reserved["autoRender"] = True
                reserved["atualizadoEm"] = _now()
                _job_store().upsert("post_production", reserved)
            if reserved.get("status") in {"failed", "cancelled", "stale"}:
                existing_source = POST_PRODUCTION_OUTPUTS / str(reserved["id"]) / "source.mp4"
                if existing_source.is_file():
                    reserved.update(
                        status="queued",
                        progresso=2,
                        etapa="Reiniciando análise",
                        erro=None,
                        atualizadoEm=_now(),
                    )
                    _job_store().upsert("post_production", reserved)
                    _launch_post_production_analysis(str(reserved["id"]))
            elif payload.autoRender and reserved.get("status") == "needs_review":
                report = run_post_production_preflight(
                    output_root=POST_PRODUCTION_OUTPUTS,
                    job_id=str(reserved["id"]),
                )
                if report["ok"]:
                    reserved.update(
                        status="rendering_preview",
                        progresso=84,
                        etapa="Aplicando edição elegante",
                        atualizadoEm=_now(),
                    )
                    _job_store().upsert("post_production", reserved)
                    _launch_post_production_render(str(reserved["id"]))
            return {"ok": True, "job": reserved, "duplicate": True}
        directory = POST_PRODUCTION_OUTPUTS / job_id
        directory.mkdir(parents=True, exist_ok=True)
        temporary.replace(directory / "source.mp4")
        _launch_post_production_analysis(job_id)
        return {"ok": True, "job": job, "duplicate": False}
    finally:
        temporary.unlink(missing_ok=True)


@app.get("/api/post-production/{job_id}")
def get_post_production(job_id: str) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    return {"job": job}


@app.get("/api/videos/{video_job_id}/post-production")
def get_latest_video_post_production(video_job_id: str) -> dict:
    """Recupera a edição mais recente sem iniciar uma nova análise."""
    job = next(
        (
            candidate
            for candidate in _job_store().list("post_production")
            if candidate.get("videoJobId") == video_job_id
        ),
        None,
    )
    return {"job": job}


@app.get("/api/post-production/{job_id}/artifacts")
def get_post_production_artifacts(job_id: str) -> dict:
    if not _job_store().get("post_production", job_id):
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    try:
        transcript, timeline = load_post_production_artifacts(POST_PRODUCTION_OUTPUTS, job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    transcript["text"] = normalize_ptbr_medical_text(str(transcript.get("text") or ""))
    for segment in transcript.get("segments", []):
        segment["text"] = normalize_ptbr_medical_text(str(segment.get("text") or ""))
    for event in timeline.get("events", []):
        event["spokenText"] = normalize_ptbr_medical_text(str(event.get("spokenText") or ""))
    return {"transcript": transcript, "timeline": timeline}


@app.patch("/api/post-production/{job_id}/events")
def update_post_production_events(job_id: str, payload: PostProductionEventsIn) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    try:
        timeline = save_post_production_event_updates(
            output_root=POST_PRODUCTION_OUTPUTS,
            job_id=job_id,
            updates=[event.model_dump(exclude_none=True) for event in payload.events],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job.update(status="needs_review", etapa="Alterações salvas; execute o preflight", atualizadoEm=_now())
    _job_store().upsert("post_production", job)
    return {"ok": True, "timeline": timeline, "job": job}


@app.post("/api/post-production/{job_id}/preflight")
def preflight_post_production(job_id: str) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    try:
        report = run_post_production_preflight(output_root=POST_PRODUCTION_OUTPUTS, job_id=job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    stale = any(
        finding.get("code") in {"timeline.stale", "video.stale"}
        for finding in report.get("findings", [])
    )
    job.update(
        status="needs_review" if report["ok"] else ("stale" if stale else "failed"),
        etapa="Preflight aprovado" if report["ok"] else "Preflight com blockers",
        atualizadoEm=_now(),
    )
    _job_store().upsert("post_production", job)
    return {"ok": report["ok"], "report": report, "job": job}


@app.post("/api/post-production/{job_id}/render")
def render_post_production(job_id: str) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    if job.get("status") not in {"needs_review", "failed", "preview_ready"}:
        raise HTTPException(status_code=409, detail="A análise ainda não está pronta para renderização.")
    report = run_post_production_preflight(output_root=POST_PRODUCTION_OUTPUTS, job_id=job_id)
    if not report["ok"]:
        raise HTTPException(status_code=409, detail={"message": "Preflight com blockers.", "report": report})
    job.update(status="rendering_preview", progresso=84, etapa="Renderização na fila", atualizadoEm=_now())
    _job_store().upsert("post_production", job)
    _launch_post_production_render(job_id)
    return {"ok": True, "job": job}


@app.post("/api/post-production/{job_id}/replan")
def replan_post_production(job_id: str) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    if job.get("status") in {"queued", "transcribing", "planning", "preflight", "rendering_preview"}:
        raise HTTPException(status_code=409, detail="O job já está em processamento.")
    source = POST_PRODUCTION_OUTPUTS / job_id / "source.mp4"
    if not source.is_file():
        raise HTTPException(status_code=409, detail="O vídeo original do job não está disponível.")
    job.update(
        status="queued",
        progresso=5,
        etapa="Regenerando plano visual",
        erro=None,
        atualizadoEm=_now(),
    )
    _job_store().upsert("post_production", job)
    _launch_post_production_analysis(job_id)
    return {"ok": True, "job": job}


@app.post("/api/post-production/{job_id}/cancel")
def cancel_post_production(job_id: str) -> dict:
    job = _job_store().get("post_production", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de pós-produção não encontrado.")
    if job.get("status") in {"preview_ready", "failed", "cancelled"}:
        return {"ok": True, "job": job}
    job.update(status="cancelled", etapa="Processamento cancelado", atualizadoEm=_now())
    _job_store().upsert("post_production", job)
    return {"ok": True, "job": job}


@app.get("/api/post-production/{job_id}/preview")
def post_production_preview(job_id: str, download: bool = False) -> FileResponse:
    job = _job_store().get("post_production", job_id)
    path = POST_PRODUCTION_OUTPUTS / job_id / "preview.mp4"
    if not job or job.get("status") != "preview_ready" or not path.is_file():
        raise HTTPException(status_code=404, detail="Prévia ainda não está disponível.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{job_id}-preview.mp4" if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


class LocalVideoKitCreateIn(BaseModel):
    uploadId: str | None = Field(default=None, min_length=8, max_length=100)
    videoJobId: str | None = Field(default=None, min_length=1, max_length=160)
    sourceKitJobId: str | None = Field(default=None, min_length=1, max_length=160)
    sourceName: str = Field(default="video-local.mp4", min_length=1, max_length=300)
    name: str = Field(default="Dr. Guilherme Martins", min_length=1, max_length=80)
    role: str = Field(default="Médico", min_length=1, max_length=90)
    title: str = Field(default="Saúde e desempenho", min_length=1, max_length=120)
    subtitle: str = Field(
        default="Informação clara, direto ao ponto.",
        min_length=1,
        max_length=150,
    )
    sectionNumber: str = Field(default="Ponto 01", min_length=1, max_length=30)
    sectionTitle: str = Field(default="O que realmente ajuda", max_length=100)
    cta: str = Field(default="Quer mais dicas?", min_length=1, max_length=90)
    site: str = Field(default="@drguilhermemartins", min_length=1, max_length=80)
    accent: str = Field(default="#c8e05a", pattern=r"^#[0-9a-fA-F]{6}$")
    sectionStartSeconds: float | None = Field(default=None, ge=3, le=7200)
    sectionDurationSeconds: float | None = Field(default=3, ge=0.5, le=120)
    sectionTransition: Literal["none", "fade", "slide_up"] | None = "fade"
    musicTrackId: str | None = Field(default=None, max_length=80)
    musicVolume: float = Field(default=0.12, ge=0.03, le=0.25)
    includeCaptions: bool = True
    captionStyle: Literal["dynamic", "clean", "editorial"] = "dynamic"
    captionPosition: Literal["safe_bottom", "center", "upper"] = "safe_bottom"
    highlightKeywords: bool = True
    duckMusicDuringSpeech: bool = True
    motionPreset: Literal["none", "subtle", "social"] = "subtle"
    enhanceVoice: bool = True
    outroTailSeconds: float = Field(default=10, ge=0, le=120)
    includeOpening: bool = True
    includeLowerThird: bool = True
    includeSection: bool = True
    includeOutro: bool = True


def _local_video_kit_job_path(job_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "", job_id)
    return LOCAL_VIDEO_KIT_JOBS / safe_id / "job.json"


def _save_local_video_kit_job(job: dict[str, Any]) -> dict[str, Any]:
    path = _local_video_kit_job_path(str(job["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return job


def _get_local_video_kit_job(job_id: str) -> dict[str, Any] | None:
    path = _local_video_kit_job_path(job_id)
    if not path.is_file():
        return None
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return job if isinstance(job, dict) else None


def _list_local_video_kit_jobs() -> list[dict[str, Any]]:
    if not LOCAL_VIDEO_KIT_JOBS.is_dir():
        return []
    jobs = [
        job
        for path in LOCAL_VIDEO_KIT_JOBS.glob("*/job.json")
        if (job := _get_local_video_kit_job(path.parent.name))
    ]
    return sorted(
        jobs,
        key=lambda item: str(item.get("atualizadoEm") or item.get("criadoEm") or ""),
        reverse=True,
    )


@app.post("/api/local-video-kit/uploads")
async def upload_local_video_kit_source(request: Request) -> dict:
    """Recebe o MP4 direto no disco, sem HeyGen e sem carregar tudo na memória."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Selecione um arquivo de vídeo.")
    declared_size = int(request.headers.get("content-length") or 0)
    max_bytes = 2 * 1024 * 1024 * 1024
    if declared_size > max_bytes:
        raise HTTPException(status_code=413, detail="O vídeo deve ter no máximo 2 GB.")
    upload_id = f"kit-upload-{uuid.uuid4().hex[:16]}"
    LOCAL_VIDEO_KIT_UPLOADS.mkdir(parents=True, exist_ok=True)
    destination = LOCAL_VIDEO_KIT_UPLOADS / f"{upload_id}.mp4"
    temporary = destination.with_suffix(".part")
    written = 0
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail="O vídeo deve ter no máximo 2 GB.")
                output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    filename = unquote(request.headers.get("x-filename") or "video-local.mp4")
    return {"ok": True, "uploadId": upload_id, "filename": filename, "size": written}


def _launch_local_video_kit(job_id: str) -> None:
    def render() -> None:
        job = _get_local_video_kit_job(job_id)
        if not job:
            return

        def update(progress: int, stage: str) -> None:
            current = _get_local_video_kit_job(job_id) or job
            current.update(
                status="processando" if progress < 100 else "pronto",
                progresso=progress,
                etapa=stage,
                atualizadoEm=_now(),
            )
            _save_local_video_kit_job(current)

        try:
            source = ROOT / str(job["sourcePath"])
            output = ROOT / str(job["outputPath"])
            config = dict(job["config"])
            music_path = _music_track_path(config.get("musicTrackId"))
            manifest = render_local_kit_video(
                source,
                output,
                _local_video_kit_job_path(job_id).parent,
                config,
                project_root=ROOT,
                music_path=music_path,
                on_progress=update,
            )
            current = _get_local_video_kit_job(job_id) or job
            current.update(
                status="pronto",
                progresso=100,
                etapa="Vídeo pronto",
                duracaoSegundos=manifest["outputDuration"],
                coverPath=str(Path(manifest["coverPath"]).relative_to(ROOT)),
                manifest=manifest,
                atualizadoEm=_now(),
            )
            current.pop("erro", None)
            _save_local_video_kit_job(current)
        except Exception as exc:
            current = _get_local_video_kit_job(job_id) or job
            current.update(
                status="erro",
                progresso=0,
                etapa="Falha na edição local",
                erro=str(exc)[-1800:],
                atualizadoEm=_now(),
            )
            _save_local_video_kit_job(current)

    threading.Thread(target=render, daemon=True, name=f"local-video-kit-{job_id}").start()


def _local_video_kit_config(payload: LocalVideoKitCreateIn) -> dict[str, Any]:
    """Normaliza peças opcionais antes de persistir e iniciar o render."""
    config = payload.model_dump(
        exclude={"uploadId", "videoJobId", "sourceKitJobId", "sourceName"}
    )
    config["sectionTitle"] = str(config.get("sectionTitle") or "").strip()
    if not config["sectionTitle"]:
        config["includeSection"] = False
    return config


@app.post("/api/local-video-kit")
def create_local_video_kit(payload: LocalVideoKitCreateIn) -> dict:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(status_code=503, detail="FFmpeg não está instalado.")
    selected_sources = sum(bool(value) for value in (payload.uploadId, payload.videoJobId, payload.sourceKitJobId))
    if selected_sources != 1:
        raise HTTPException(
            status_code=422,
            detail="Escolha um arquivo local, um vídeo pronto da produção ou um kit salvo.",
        )

    if payload.videoJobId:
        video_job = _job_store().get("video", payload.videoJobId)
        if not video_job:
            raise HTTPException(status_code=404, detail="O vídeo da produção não foi encontrado.")
        if video_job.get("status") != "pronto":
            raise HTTPException(status_code=409, detail="O vídeo da produção ainda não está pronto.")
        source = _local_output_path(video_job.get("outputPath"))
        if not source:
            source = LOCAL_VIDEO_KIT_UPLOADS / f"kit-import-{uuid.uuid4().hex[:16]}.mp4"
            _copy_or_download_video(video_job, source)
    elif payload.sourceKitJobId:
        source_job = _get_local_video_kit_job(payload.sourceKitJobId)
        if not source_job:
            raise HTTPException(status_code=404, detail="O kit salvo não foi encontrado.")
        if source_job.get("status") != "pronto":
            raise HTTPException(status_code=409, detail="O kit salvo ainda não está pronto.")
        source = _local_output_path(source_job.get("sourcePath"))
        if not source:
            raise HTTPException(status_code=404, detail="O vídeo original do kit salvo não foi encontrado.")
    else:
        source = LOCAL_VIDEO_KIT_UPLOADS / f"{payload.uploadId}.mp4"
        if not source.is_file():
            raise HTTPException(status_code=404, detail="O vídeo enviado não foi encontrado.")

    job_id = f"kit-{uuid.uuid4().hex[:16]}"
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", _norm(Path(payload.sourceName).stem)).strip("-")
    output = LOCAL_VIDEO_KIT_OUTPUTS / f"{safe_name or 'video-local'}--kit-grafico--{job_id}.mp4"
    now = _now()
    job = {
        "id": job_id,
        "status": "fila",
        "progresso": 2,
        "etapa": "Preparando edição local",
        "sourceName": payload.sourceName,
        "sourcePath": str(source.relative_to(ROOT)),
        "sourceVideoJobId": payload.videoJobId,
        "sourceKitJobId": payload.sourceKitJobId,
        "outputPath": str(output.relative_to(ROOT)),
        "config": _local_video_kit_config(payload),
        "externalCreditsUsed": False,
        "criadoEm": now,
        "atualizadoEm": now,
    }
    _save_local_video_kit_job(job)
    _launch_local_video_kit(job_id)
    return {"ok": True, "job": job}


@app.get("/api/local-video-kit")
def list_local_video_kit_jobs() -> dict:
    return {"jobs": _list_local_video_kit_jobs()}


@app.get("/api/local-video-kit/{job_id}")
def get_local_video_kit(job_id: str) -> dict:
    job = _get_local_video_kit_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Edição local não encontrada.")
    return {"job": job}


@app.post("/api/local-video-kit/{job_id}/retry")
def retry_local_video_kit(job_id: str) -> dict:
    """Retoma um render interrompido sem criar outro job para a interface."""
    job = _get_local_video_kit_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Edição local não encontrada.")
    source = _local_output_path(job.get("sourcePath"))
    if not source:
        raise HTTPException(status_code=404, detail="Vídeo original não encontrado.")
    if job.get("status") in {"fila", "processando"}:
        try:
            updated_at = datetime.fromisoformat(str(job.get("atualizadoEm") or ""))
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        except ValueError:
            age_seconds = 61
        if age_seconds < 60:
            raise HTTPException(status_code=409, detail="A edição local ainda está processando.")
    job.update(
        status="fila",
        progresso=2,
        etapa="Retomando edição local",
        atualizadoEm=_now(),
    )
    job.pop("erro", None)
    _save_local_video_kit_job(job)
    _launch_local_video_kit(job_id)
    return {"ok": True, "job": job}


@app.get("/api/local-video-kit/{job_id}/source")
def local_video_kit_source(job_id: str) -> FileResponse:
    job = _get_local_video_kit_job(job_id)
    path = _local_output_path((job or {}).get("sourcePath"))
    if not job or not path:
        raise HTTPException(status_code=404, detail="Vídeo original não encontrado.")
    return FileResponse(path, media_type="video/mp4", content_disposition_type="inline")


@app.get("/api/local-video-kit/{job_id}/result")
def local_video_kit_result(job_id: str, download: bool = False) -> FileResponse:
    job = _get_local_video_kit_job(job_id)
    path = _local_output_path((job or {}).get("outputPath"))
    if not job or job.get("status") != "pronto" or not path:
        raise HTTPException(status_code=404, detail="Vídeo editado ainda não está disponível.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


@app.get("/api/local-video-kit/{job_id}/cover")
def local_video_kit_cover(job_id: str, download: bool = False) -> FileResponse:
    job = _get_local_video_kit_job(job_id)
    path = _local_output_path((job or {}).get("coverPath"))
    if not job or job.get("status") != "pronto" or not path:
        raise HTTPException(status_code=404, detail="Capa ainda não está disponível.")
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"{job_id}-capa.png" if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


class CutCreateIn(BaseModel):
    requestId: str = Field(min_length=8, max_length=100)
    videoJobId: str | None = None
    uploadId: str | None = None
    youtubeUrl: str | None = Field(default=None, max_length=500)
    sourceName: str | None = Field(default=None, max_length=300)
    clipCount: int | None = Field(default=3)
    minDuration: int = Field(default=15, ge=8, le=90)
    maxDuration: int = Field(default=45, ge=10, le=120)
    durationMode: Literal["preset", "auto"] = "preset"
    analysisStartSeconds: float = Field(default=0, ge=0, le=7200)
    analysisEndSeconds: float | None = Field(default=None, gt=0, le=7200)
    captions: bool = True
    layout: Literal["fit", "fill"] = "fit"


@app.post("/api/cuts/uploads")
async def upload_cut_source(request: Request) -> dict:
    """Recebe um video local bruto sem carregar o arquivo inteiro na memoria."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Selecione um arquivo de video.")
    declared_size = int(request.headers.get("content-length") or 0)
    max_bytes = 2 * 1024 * 1024 * 1024
    if declared_size > max_bytes:
        raise HTTPException(status_code=413, detail="O video deve ter no maximo 2 GB.")
    upload_id = f"upload-{uuid.uuid4().hex[:16]}"
    CUT_UPLOADS.mkdir(parents=True, exist_ok=True)
    destination = CUT_UPLOADS / f"{upload_id}.video"
    temporary = destination.with_suffix(".part")
    written = 0
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail="O video deve ter no maximo 2 GB.")
                output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="O arquivo enviado esta vazio.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "ok": True,
        "uploadId": upload_id,
        "filename": request.headers.get("x-filename") or "video",
        "size": written,
    }


@app.get("/api/cuts")
def list_cut_projects() -> dict:
    return {"projects": _job_store().list("cut")}


@app.get("/api/cuts/{project_id}")
def get_cut_project(project_id: str) -> dict:
    project = _job_store().get("cut", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto de cortes nao encontrado.")
    return {"project": project}


def _launch_cut_worker(
    *,
    store: JobStore,
    project: dict[str, Any],
    source_url: str | None,
    youtube_url: str | None,
    source_path: Path | None,
) -> None:
    prepare_cut_job(str(project["id"]))
    worker = threading.Thread(
        target=process_cut_project,
        kwargs={
            "store": store,
            "job_id": project["id"],
            "root": ROOT,
            "output_root": CUT_OUTPUTS,
            "source_url": source_url,
            "youtube_url": youtube_url,
            "source_path": source_path,
            "compliance": _pack_compliance,
            "cache_get": _ai_cache_get,
            "cache_put": _ai_cache_put,
            "record_usage": _record_anthropic_usage,
        },
        daemon=True,
        name=f"cuts-{project['id']}",
    )
    worker.start()


def _cut_project_sources(
    project: dict[str, Any],
    store: JobStore,
) -> tuple[str | None, str | None, Path | None]:
    source_url: str | None = None
    source_path: Path | None = None
    youtube_url = str(project.get("youtubeUrl") or "").strip() or None
    if project.get("uploadId"):
        source_path = CUT_UPLOADS / f"{project['uploadId']}.video"
        if not source_path.is_file():
            raise RuntimeError("O video enviado nao esta mais disponivel.")
    elif project.get("videoJobId"):
        video_job = store.get("video", str(project["videoJobId"]))
        source_path = _local_output_path((video_job or {}).get("outputPath"))
        source_url = str(
            (video_job or {}).get("remoteVideoUrl") or (video_job or {}).get("videoUrl") or ""
        )
        if not source_path and not source_url:
            raise RuntimeError("O video produzido nao esta mais disponivel.")
    elif not youtube_url:
        raise RuntimeError("A origem deste projeto nao esta disponivel.")
    return source_url, youtube_url, source_path


def resume_interrupted_cut_projects() -> None:
    store = _job_store()
    for project in store.list("cut"):
        if project.get("status") not in {"fila", "processando"}:
            continue
        try:
            source_url, youtube_url, source_path = _cut_project_sources(project, store)
        except RuntimeError as exc:
            project.update(
                status="erro",
                progresso=0,
                etapa="Falha ao retomar processamento",
                erro=str(exc),
                atualizadoEm=_now(),
            )
            store.upsert("cut", project)
            continue
        project.update(etapa="Retomando processamento", atualizadoEm=_now())
        store.upsert("cut", project)
        _launch_cut_worker(
            store=store,
            project=project,
            source_url=source_url,
            youtube_url=youtube_url,
            source_path=source_path,
        )


def resume_interrupted_post_production_jobs() -> None:
    store = _job_store()
    for job in store.list("post_production"):
        status = job.get("status")
        if status not in {"queued", "transcribing", "planning", "preflight", "rendering_preview"}:
            continue
        source = POST_PRODUCTION_OUTPUTS / str(job["id"]) / "source.mp4"
        if not source.is_file():
            job.update(
                status="failed",
                etapa="Não foi possível retomar",
                erro="O vídeo original do job não está disponível.",
                atualizadoEm=_now(),
            )
            store.upsert("post_production", job)
            continue
        job.update(etapa="Retomando processamento", atualizadoEm=_now())
        store.upsert("post_production", job)
        if status == "rendering_preview":
            _launch_post_production_render(str(job["id"]))
        else:
            _launch_post_production_analysis(str(job["id"]))


@app.post("/api/cuts")
def create_cut_project(payload: CutCreateIn) -> dict:
    """Inicia transcricao, selecao editorial e renderizacao em segundo plano."""
    sources = [payload.videoJobId, payload.uploadId, payload.youtubeUrl]
    if sum(bool(source) for source in sources) != 1:
        raise HTTPException(
            status_code=400,
            detail="Escolha um video produzido, envie um arquivo ou informe um link do YouTube.",
        )
    if payload.maxDuration < payload.minDuration:
        raise HTTPException(status_code=422, detail="A duracao maxima deve superar a minima.")
    if payload.clipCount is not None and not 1 <= payload.clipCount <= 8:
        raise HTTPException(status_code=422, detail="A quantidade deve ficar entre 1 e 8 cortes.")
    if (
        payload.analysisEndSeconds is not None
        and payload.analysisEndSeconds <= payload.analysisStartSeconds
    ):
        raise HTTPException(status_code=422, detail="O fim do trecho deve ser posterior ao inicio.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(status_code=503, detail="FFmpeg nao esta instalado.")

    source_url: str | None = None
    youtube_url: str | None = None
    source_path: Path | None = None
    source_name = "Video enviado"
    if payload.videoJobId:
        video_job = _job_store().get("video", payload.videoJobId)
        if not video_job or video_job.get("status") != "pronto":
            raise HTTPException(status_code=409, detail="O video produzido ainda nao esta pronto.")
        source_path = _local_output_path(video_job.get("outputPath"))
        source_url = str(video_job.get("remoteVideoUrl") or video_job.get("videoUrl") or "")
        if not source_path:
            parsed = urlparse(source_url)
            hostname = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not (
                hostname == "heygen.ai" or hostname.endswith(".heygen.ai")
            ):
                raise HTTPException(status_code=409, detail="O arquivo do HeyGen nao esta disponivel.")
        try:
            source_name = _find_script(str(video_job.get("scriptId") or "")).get(
                "titulo", "Video produzido"
            )
        except HTTPException:
            source_name = "Video produzido"
    elif payload.uploadId:
        source_path = CUT_UPLOADS / f"{payload.uploadId}.video"
        if not source_path.is_file():
            raise HTTPException(status_code=404, detail="Upload de video nao encontrado.")
        source_name = payload.sourceName or "Video enviado"
    else:
        youtube_url = str(payload.youtubeUrl or "").strip()
        parsed = urlparse(youtube_url)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme != "https" or hostname not in {
            "youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }:
            raise HTTPException(status_code=422, detail="Informe um link valido do YouTube.")
        if not shutil.which("yt-dlp"):
            raise HTTPException(status_code=503, detail="O downloader do YouTube nao esta instalado.")
        source_name = payload.sourceName or "Video do YouTube"

    now = _now()
    project = {
        "id": f"cut-{uuid.uuid4().hex[:12]}",
        "status": "fila",
        "progresso": 0,
        "etapa": "Aguardando processamento",
        "sourceName": source_name,
        "videoJobId": payload.videoJobId,
        "uploadId": payload.uploadId,
        "youtubeUrl": youtube_url,
        "settings": payload.model_dump(
            exclude={"requestId", "videoJobId", "uploadId", "youtubeUrl", "sourceName"},
        ),
        "clips": [],
        "criadoEm": now,
        "atualizadoEm": now,
    }
    store = _job_store()
    project, reservation = store.reserve(
        "cut",
        project,
        idempotency_key=f"cut:{payload.requestId}",
    )
    if reservation == "duplicate":
        return {"ok": True, "duplicate": True, "project": project}
    _launch_cut_worker(
        store=store,
        project=project,
        source_url=source_url,
        youtube_url=youtube_url,
        source_path=source_path,
    )
    return {"ok": True, "project": project}


@app.post("/api/cuts/{project_id}/retry")
def retry_cut_project(project_id: str) -> dict:
    store = _job_store()
    project = store.get("cut", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto de cortes nao encontrado.")
    if project.get("status") not in {"erro", "cancelado"}:
        raise HTTPException(status_code=409, detail="Somente projetos parados ou com erro podem ser repetidos.")

    try:
        source_url, youtube_url, source_path = _cut_project_sources(project, store)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    project.update(
        status="fila",
        progresso=0,
        etapa="Aguardando novo processamento",
        clips=[],
        atualizadoEm=_now(),
    )
    project.pop("erro", None)
    store.upsert("cut", project)
    _launch_cut_worker(
        store=store,
        project=project,
        source_url=source_url,
        youtube_url=youtube_url,
        source_path=source_path,
    )
    return {"ok": True, "project": project}


@app.post("/api/cuts/{project_id}/cancel")
def cancel_cut_project(project_id: str) -> dict:
    store = _job_store()
    project = store.get("cut", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto de cortes nao encontrado.")
    if project.get("status") not in {"fila", "processando"}:
        return {"ok": True, "project": project}

    cancel_cut_worker(project_id)
    project.update(
        status="cancelado",
        progresso=0,
        etapa="Processamento interrompido",
        erro=None,
        atualizadoEm=_now(),
    )
    store.upsert("cut", project)
    return {"ok": True, "project": project}


@app.get("/api/cuts/{project_id}/files/{filename}")
def cut_file(project_id: str, filename: str, download: bool = False) -> FileResponse:
    project = _job_store().get("cut", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto de cortes nao encontrado.")
    allowed = {str(clip.get("filename")) for clip in project.get("clips", [])}
    if filename not in allowed or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Corte nao encontrado.")
    path = CUT_OUTPUTS / project_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do corte nao encontrado.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


def _run(script_args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *script_args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@app.post("/api/refresh")
def refresh() -> dict:
    """Re-sincroniza o snapshot local a partir do Google Sheets."""
    script = ROOT / "sync_sheets_snapshot.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="sync_sheets_snapshot.py nao encontrado")
    try:
        from integrations.google_sheets_rest_client import GoogleSheetsRestClient

        client = GoogleSheetsRestClient()
        for tab in TAB_RANGE:
            _ensure_tab_ids(client, tab)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao preparar IDs permanentes: {exc}")
    proc = _run([str(script)], timeout=120)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stderr or "falha ao sincronizar")
    scripts = map_scripts(_load_snapshot().get("sheets", {}).get("roteiros", []))
    migrated_jobs = _migrate_video_job_script_ids(scripts)
    return {
        "ok": True,
        "stdout": proc.stdout.strip()[-500:],
        "migratedVideoJobs": migrated_jobs,
    }


@app.post("/api/trends/hunt")
def hunt_trends() -> dict:
    """
    Pipeline real de captura: trend_hunter -> sync p/ Sheets -> refresh snapshot.
    Requer .env e .google_sheets_token.json na raiz para os passos 2 e 3.
    """
    antes = len(map_trends(_load_snapshot().get("sheets", {}).get("radar", [])))
    settings = _load_settings()
    radar_settings = settings.get("radar", {})
    query_terms = _clean_string_list(
        [
            *(settings.get("temasPrioritarios") or []),
            *(radar_settings.get("termosExtras") or []),
        ],
        limit=80,
    )
    trend_args = [str(ROOT / "trend_hunter" / "trend_hunter.py")]
    for term in query_terms:
        trend_args.extend(["--query", term])
    trend_args.extend(["--period", str(radar_settings.get("periodo") or "semana")])
    for source in radar_settings.get("fontes") or []:
        trend_args.extend(["--source", str(source)])
    sync_limit = int(radar_settings.get("limitePorBusca") or 20)

    steps = [
        ("trend_hunter", trend_args, 180),
        ("sync_sheets", [str(ROOT / "sync_trends_to_sheets.py"), "--limit", str(sync_limit)], 120),
        ("refresh_snapshot", [str(ROOT / "sync_sheets_snapshot.py")], 120),
    ]
    log: list[str] = []
    for index, (nome, args, timeout) in enumerate(steps):
        if not Path(args[0]).exists():
            raise HTTPException(status_code=404, detail=f"{nome}: script nao encontrado")
        try:
            proc = _run(args, timeout=timeout)
        except subprocess.TimeoutExpired:
            if index == 0:
                raise HTTPException(status_code=504, detail=f"{nome}: tempo esgotado")
            return _hunt_partial_result(log, query_terms, nome, "tempo esgotado")
        log.append(f"[{nome}] rc={proc.returncode}\n{(proc.stdout or proc.stderr)[-400:]}")
        if proc.returncode != 0:
            if index == 0:
                # Passo 1 falhou: nao ha nenhuma tendencia capturada, erro completo faz sentido.
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Falha no passo '{nome}'. Verifique .env e .google_sheets_token.json "
                        f"na raiz do projeto.\n{(proc.stderr or proc.stdout)[-400:]}"
                    ),
                )
            # Passos 2/3 falham sem credenciais (.env / token OAuth do Sheets), mas o
            # Trend Hunter (passo 1) ja capturou tendencias localmente: nao descartamos
            # esse trabalho so porque a sincronizacao com o Sheets falhou.
            return _hunt_partial_result(log, query_terms, nome, (proc.stderr or proc.stdout)[-400:])

    depois = len(map_trends(_load_snapshot().get("sheets", {}).get("radar", [])))
    return {
        "ok": True,
        "partial": False,
        "added": max(depois - antes, 0),
        "queries": query_terms,
        "log": "\n\n".join(log)[-1500:],
    }


def _hunt_partial_result(
    log: list[str], query_terms: list[str], failed_step: str, reason: str
) -> dict:
    """Passo 1 (captura) funcionou, mas um passo seguinte falhou. Devolve 200 com
    partial=True em vez de estourar erro, para o frontend nao esconder o que
    ja deu certo."""
    return {
        "ok": True,
        "partial": True,
        "added": 0,
        "queries": query_terms,
        "failedStep": failed_step,
        "detail": (
            f"Trend Hunter capturou tendencias localmente, mas o passo '{failed_step}' falhou "
            "antes de chegar ao Sheets. Verifique .env e .google_sheets_token.json e rode "
            f"'Buscar tendencias' de novo.\n{reason}"
        ),
        "log": "\n\n".join(log)[-1500:],
    }


# --------------------------------------------------------------------------- #
# Escrita de status de volta no Google Sheets
# --------------------------------------------------------------------------- #
TAB_RANGE = {
    "radar": "'Radar Tendencias'!A:L",
    "ideias": "'Ideias'!A:M",
    "roteiros": "'Roteiros'!A:V",
    "calendario": "'Calendario'!A:N",
}
TAB_TITLE = {
    "radar": "Radar Tendencias",
    "ideias": "Ideias",
    "roteiros": "Roteiros",
    "calendario": "Calendario",
}
TAB_PREFIX = {"radar": "t", "ideias": "i", "roteiros": "s", "calendario": "p"}

# Enum interno do frontend -> rotulo PT-BR gravado na planilha.
STATUS_LABELS = {
    "radar": {
        "novo": "Pendente",
        "em_analise": "Ideia gerada",
        "descartado": "Descartado",
    },
    "ideias": {
        "novo": "Nova",
        "em_analise": "Em análise",
        "aprovado": "Ideia gerada",
        "descartado": "Descartado",
    },
    "roteiros": {
        "aguardando_validacao": "Aguardando validação médica",
        "em_revisao": "Em revisão",
        "aprovado_clinicamente": "Aprovado clinicamente",
        "rejeitado": "Rejeitado",
    },
    "calendario": {
        "pendente": "Pendente",
        "agendado": "Agendado",
        "publicado": "Publicado",
    },
}


def _col_letter(idx0: int) -> str:
    s, n = "", idx0
    while True:
        s = chr(65 + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


class StatusUpdate(BaseModel):
    status: str


def _sheet_row_number(values: list[list[Any]], item_id: str, prefix: str) -> int:
    """Localiza pelo ID estavel; IDs posicionais antigos continuam funcionando."""
    if not values:
        raise HTTPException(status_code=404, detail="aba vazia")
    headers = [str(value).strip() for value in values[0]]
    id_col = headers.index("ID") if "ID" in headers else -1
    data_rows: list[tuple[int, list[Any]]] = []
    for rownum, row in enumerate(values[1:], start=2):
        if any(str(value).strip() for value in row):
            data_rows.append((rownum, row))
            if id_col >= 0 and id_col < len(row) and str(row[id_col]).strip() == item_id:
                return rownum

    match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", item_id)
    if match:
        index = int(match.group(1))
        if 0 <= index < len(data_rows):
            return data_rows[index][0]
    raise HTTPException(status_code=404, detail=f"item {item_id} nao encontrado")


def _update_snapshot_row(tab: str, item_id: str, patch: dict[str, Any]) -> None:
    snapshot = _load_snapshot()
    rows = snapshot.setdefault("sheets", {}).setdefault(tab, [])
    prefix = TAB_PREFIX[tab]
    target: dict[str, Any] | None = next(
        (row for index, row in enumerate(rows) if _row_id(row, prefix, index) == item_id),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} nao encontrado no snapshot")
    target.update(patch)
    snapshot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SNAPSHOT)


def _remove_snapshot_row(tab: str, item_id: str) -> None:
    snapshot = _load_snapshot()
    rows = snapshot.setdefault("sheets", {}).setdefault(tab, [])
    prefix = TAB_PREFIX[tab]
    target_index = next(
        (index for index, row in enumerate(rows) if _row_id(row, prefix, index) == item_id),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} nao encontrado no snapshot")
    rows.pop(target_index)
    snapshot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SNAPSHOT)


def _append_snapshot_row(tab: str, row: dict[str, Any]) -> None:
    snapshot = _load_snapshot()
    snapshot.setdefault("sheets", {}).setdefault(tab, []).append(row)
    snapshot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SNAPSHOT)


def _ensure_tab_ids(client: Any, tab: str) -> int:
    """Cria a coluna ID e preenche somente registros que ainda nao possuem ID."""
    values = client.get_values(TAB_RANGE[tab])
    if not values:
        return 0
    headers = [str(value).strip() for value in values[0]]
    id_col = headers.index("ID") if "ID" in headers else len(headers)
    ids: list[list[str]] = [["ID"]]
    created = 0
    for row in values[1:]:
        existing = str(row[id_col]).strip() if id_col < len(row) else ""
        has_data = any(str(value).strip() for index, value in enumerate(row) if index != id_col)
        if has_data and not existing:
            existing = f"{TAB_PREFIX[tab]}-{uuid.uuid4().hex[:12]}"
            created += 1
        ids.append([existing])
    column = _col_letter(id_col)
    client.update_values(f"'{TAB_TITLE[tab]}'!{column}1:{column}{len(ids)}", ids)
    return created


@app.post("/api/sheets/ensure-ids")
def ensure_sheet_ids() -> dict:
    """Migra as abas operacionais para IDs permanentes e atualiza o snapshot."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    try:
        client = GoogleSheetsRestClient()
        created = {tab: _ensure_tab_ids(client, tab) for tab in TAB_RANGE}
        proc = _run([str(ROOT / "sync_sheets_snapshot.py")], timeout=120)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao criar IDs permanentes: {exc}")
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stderr or "falha ao atualizar snapshot")
    scripts = map_scripts(_load_snapshot().get("sheets", {}).get("roteiros", []))
    migrated_jobs = _migrate_video_job_script_ids(scripts)
    return {"ok": True, "created": created, "migratedVideoJobs": migrated_jobs}


@app.post("/api/sheets/{tab}/{item_id}/status")
def set_status(tab: str, item_id: str, payload: StatusUpdate) -> dict:
    """Grava o novo status de um item (radar/ideias/roteiros) na planilha."""
    if tab not in TAB_RANGE:
        raise HTTPException(status_code=404, detail=f"aba desconhecida: {tab}")
    label = STATUS_LABELS.get(tab, {}).get(payload.status)
    if not label:
        raise HTTPException(status_code=400, detail=f"status invalido: {payload.status}")
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    try:
        client = GoogleSheetsRestClient()
        values = client.get_values(TAB_RANGE[tab])
    except Exception as exc:  # credenciais / rede
        raise HTTPException(status_code=503, detail=f"falha ao acessar Sheets: {exc}")
    headers = [str(v).strip() for v in values[0]]
    if "Status" not in headers:
        raise HTTPException(status_code=500, detail="coluna 'Status' nao encontrada")
    status_col = headers.index("Status")

    rownum = _sheet_row_number(values, item_id, TAB_PREFIX[tab])
    cell = f"'{TAB_TITLE[tab]}'!{_col_letter(status_col)}{rownum}"
    try:
        client.update_values(cell, [[label]])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao gravar: {exc}")
    _update_snapshot_row(tab, item_id, {"Status": label})
    return {"ok": True, "cell": cell, "status": label}


# --------------------------------------------------------------------------- #
# Escrita de NOVOS itens no Google Sheets (persistir ideias/roteiros gerados)
# --------------------------------------------------------------------------- #
_PRIORIDADE = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
_RISCO = {"alto": "Alto", "medio": "Médio", "baixo": "Baixo"}
_FAMILIA = {
    "medicamento": "Medicamento",
    "comportamento": "Comportamento",
    "metabolismo": "Metabolismo",
    "obesidade": "Obesidade",
    "educativo": "Educativo",
}
_IDEIA_STATUS = {
    "novo": "Nova",
    "em_analise": "Em análise",
    "aprovado": "Ideia gerada",
    "descartado": "Descartado",
}
_ROTEIRO_STATUS = {
    "aguardando_validacao": "Rascunho",
    "em_revisao": "Em edição",
    "aprovado_clinicamente": "Pronto",
    "rejeitado": "Arquivado",
}


class TrendIn(BaseModel):
    id: str | None = None
    titulo: str = Field(min_length=1, max_length=300)
    subtema: str | None = None
    sinal: str | None = None
    dorPublico: str | None = None
    fonte: str = Field(min_length=1, max_length=200)
    link: str | None = None
    potencial: int = Field(default=5, ge=0, le=10)
    prioridade: Literal["alta", "media", "baixa"] = "media"
    status: Literal["novo", "em_analise", "descartado"] = "novo"
    notas: str | None = None
    criadoEm: str | None = None


RADAR_HEADERS = [
    "Data",
    "Potencial Viral",
    "Tema",
    "Subtema",
    "Fonte",
    "Link referência",
    "Sinal de tendência",
    "Dor do público",
    "Prioridade",
    "Status",
    "Observações",
    "ID",
]


def _radar_date(value: str | None) -> str:
    raw = (value or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return datetime.now().date().isoformat()


class IdeaIn(BaseModel):
    id: str | None = None
    trendId: str | None = None
    titulo: str
    hook: str = ""
    angulo: str = ""
    tipo: str | None = None
    publicoDor: str | None = None
    cta: str = ""
    linkOrigem: str | None = None
    observacaoCompliance: str = ""
    prioridade: str = "media"
    status: str = "novo"
    criadoEm: str | None = None


class ExpandIdeasIn(BaseModel):
    seed: str = Field(min_length=8, max_length=10000)
    quantity: int = Field(default=3, ge=1, le=5)
    familia: Literal["medicamento", "comportamento", "metabolismo", "obesidade", "educativo"] = "educativo"
    prioridade: Literal["alta", "media", "baixa"] = "media"
    sourceUrl: str | None = Field(default=None, max_length=1000)


class CaptureHooksIn(BaseModel):
    trendId: str = Field(min_length=1, max_length=200)
    titulo: str = Field(min_length=3, max_length=500)
    subtema: str | None = Field(default=None, max_length=500)
    sinal: str | None = Field(default=None, max_length=2000)
    dorPublico: str | None = Field(default=None, max_length=1000)
    notas: str | None = Field(default=None, max_length=2000)
    familia: Literal["medicamento", "comportamento", "metabolismo", "obesidade", "educativo"] = "educativo"
    prioridade: Literal["alta", "media", "baixa"] = "media"
    sourceUrl: str | None = Field(default=None, max_length=1000)
    durationSeconds: Literal[10, 15] = 10
    editorialTone: Literal["positivo", "neutro", "apreensivo"] = "neutro"
    outro: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    requireClaude: bool = False


class TrendSummaryIn(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    sourceUrl: str = Field(min_length=10, max_length=1000)


class ArticleIdeasIn(BaseModel):
    # O texto pode vir do campo de colagem ou ser obtido a partir de uma URL,
    # DOI ou PMID informados no modal de importação.
    # Arquivos MHTML podem ser maiores que um texto colado. O conteúdo é
    # reduzido para texto editorial antes de seguir para a análise.
    article: str = Field(default="", max_length=8_000_000)
    sourceUrl: str | None = Field(default=None, max_length=1000)
    quantity: int = Field(default=5, ge=1, le=6)
    familia: Literal["medicamento", "comportamento", "metabolismo", "obesidade", "educativo"] = "medicamento"
    prioridade: Literal["alta", "media", "baixa"] = "alta"


class ScriptIn(BaseModel):
    id: str | None = None
    ideaId: str | None = None
    categoria: str = "educativo"
    tema: str = ""
    titulo: str
    hook: str = ""
    dorConflito: str = ""
    explicacaoSimples: str = ""
    virada: str = ""
    cta: str = ""
    cuidadosMedicos: str = ""
    risco: str = "medio"
    formatoSugerido: str = "Reels"
    aprovador: str | None = None
    validadoEm: str | None = None
    criadoEm: str | None = None
    link: str | None = None
    status: str = "aguardando_validacao"
    editorialTone: Literal["positivo", "neutro", "apreensivo"] | None = None
    textoFalado: str = ""
    outroText: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    generationProvider: Literal["claude", "fallback", "manual"] | None = None
    generationFlowVersion: str | None = Field(default=None, max_length=100)


class CalendarIn(BaseModel):
    id: str | None = None
    scriptId: str | None = None
    videoJobId: str | None = None
    titulo: str = Field(min_length=1, max_length=500)
    dataAgendada: str
    canal: Literal["instagram", "tiktok", "youtube_shorts"] = "instagram"
    status: Literal["pendente", "agendado", "publicado"] = "agendado"
    publicadoEm: str | None = None
    tema: str | None = None
    formato: str | None = None
    responsavel: str | None = None
    link: str | None = None


CALENDAR_HEADERS = [
    "Data publicação",
    "Canal",
    "Tema",
    "Formato",
    "Título/Hook",
    "Responsável",
    "Asset pronto?",
    "Status",
    "Link post",
    "Observações",
    "ID",
    "Roteiro ID",
    "Video Job ID",
    "Publicado em",
]

_CALENDAR_CHANNEL = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube_shorts": "YouTube Shorts",
}


def _calendar_date(value: str) -> str:
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Data de publicacao invalida.") from exc
    return parsed.strftime("%d/%m/%Y")


def _calendar_row(payload: CalendarIn, item_id: str) -> list[str]:
    published_at = payload.publicadoEm
    if payload.status == "publicado" and not published_at:
        published_at = _now()
    return [
        _calendar_date(payload.dataAgendada),
        _CALENDAR_CHANNEL[payload.canal],
        payload.tema or "",
        payload.formato or "Reel",
        payload.titulo,
        payload.responsavel or "",
        "Sim" if payload.videoJobId else "Não",
        STATUS_LABELS["calendario"][payload.status],
        payload.link or "",
        "",
        item_id,
        payload.scriptId or "",
        payload.videoJobId or "",
        published_at or "",
    ]


def _ensure_calendar_headers(client: Any) -> None:
    values = client.get_values(TAB_RANGE["calendario"])
    current = [str(value).strip() for value in values[0]] if values else []
    if current[: len(CALENDAR_HEADERS)] != CALENDAR_HEADERS:
        merged = CALENDAR_HEADERS.copy()
        for index, value in enumerate(current[: len(merged)]):
            if value and index < 11:
                merged[index] = value
        client.update_values("'Calendario'!A1:N1", [merged])


IDEA_HEADERS = [
    "Tema",
    "Hook",
    "Ângulo",
    "Tipo",
    "Público/Dor",
    "CTA",
    "Prioridade",
    "Status",
    "Link origem",
    "Observações",
    "ID",
    "Trend ID",
    "Criado em",
]

SCRIPT_HEADERS = [
    "Categoria",
    "Tema",
    "Título",
    "Hook",
    "Dor/Conflito",
    "Explicação simples",
    "Virada/Provocação",
    "CTA",
    "Cuidados médicos",
    "Risco",
    "Formato sugerido",
    "Status",
    "Aprovador",
    "Data aprovação",
    "Link doc/video",
    "ID",
    "Idea ID",
    "Tom editorial",
    "Texto falado",
    "Frase final",
    "Gerado por",
    "Versão do fluxo",
]


def _ensure_idea_headers(client: Any) -> None:
    values = client.get_values(TAB_RANGE["ideias"])
    current = [str(value).strip() for value in values[0]] if values else []
    if current[: len(IDEA_HEADERS)] == IDEA_HEADERS:
        return
    merged = IDEA_HEADERS.copy()
    for index, value in enumerate(current[: len(merged)]):
        if value and index < 11:
            merged[index] = value
    client.update_values("'Ideias'!A1:M1", [merged])


def _ensure_script_headers(client: Any) -> None:
    values = client.get_values(TAB_RANGE["roteiros"])
    current = [str(value).strip() for value in values[0]] if values else []
    if current[: len(SCRIPT_HEADERS)] == SCRIPT_HEADERS:
        return
    merged = SCRIPT_HEADERS.copy()
    for index, value in enumerate(current[:16]):
        if value:
            merged[index] = value
    client.update_values("'Roteiros'!A1:V1", [merged])


_EXPAND_IDEAS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "titulo": {"type": "string"},
                    "hook": {"type": "string"},
                    "angulo": {"type": "string"},
                    "tipo": {"type": "string"},
                    "publicoDor": {"type": "string"},
                    "cta": {"type": "string"},
                    "observacaoCompliance": {"type": "string"},
                    "prioridade": {"type": "string"},
                },
                "required": [
                    "titulo",
                    "hook",
                    "angulo",
                    "tipo",
                    "publicoDor",
                    "cta",
                    "observacaoCompliance",
                    "prioridade",
                ],
            },
        }
    },
    "required": ["ideas"],
}


_CAPTURE_HOOKS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "capturePotential": {"type": "integer"},
                "audienceReflex": {"type": "string"},
                "recommendedAngle": {"type": "string"},
                "riskNotes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["capturePotential", "audienceReflex", "recommendedAngle", "riskNotes"],
        },
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "strategy": {"type": "string"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "turn": {"type": "string"},
                    "spokenText": {"type": "string"},
                    "rationale": {"type": "string"},
                    "stopScore": {"type": "integer"},
                    "profileScore": {"type": "integer"},
                    "complianceNotes": {"type": "string"},
                },
                "required": [
                    "strategy",
                    "title",
                    "hook",
                    "turn",
                    "spokenText",
                    "rationale",
                    "stopScore",
                    "profileScore",
                    "complianceNotes",
                ],
            },
        },
    },
    "required": ["analysis", "variants"],
}


CAPTURE_HOOKS_PROMPT_VERSION = "2026-08-05-v4-claude-flow-validated"
def _capture_topic(title: str) -> str:
    words = re.sub(r"\s+", " ", title).strip().split()
    return " ".join(words[:7]).rstrip(" ,:;.!?") or "essa tendência"


def _capture_hooks_fallback(payload: CaptureHooksIn) -> dict[str, Any]:
    topic = _capture_topic(payload.titulo)
    rows = [
        {
            "strategy": "Quebra de padrão",
            "title": "O detalhe ignorado",
            "hook": f"Todo mundo está falando de {topic}.",
            "turn": "O detalhe ignorado muda a conversa.",
            "spokenText": f"Todo mundo está falando de {topic}. O detalhe que quase ninguém percebe muda completamente essa conversa.",
            "rationale": "Interrompe o padrão e abre uma lacuna de informação sem revelar toda a mensagem.",
            "stopScore": 8,
            "profileScore": 8,
            "complianceNotes": "Sem promessa, diagnóstico, prescrição ou transformação corporal.",
        },
        {
            "strategy": "Lacuna de informação",
            "title": "A parte que a manchete não mostra",
            "hook": f"A manchete sobre {topic} parece simples.",
            "turn": "A parte omitida é a mais importante.",
            "spokenText": f"A manchete sobre {topic} parece simples. Mas ela não mostra justamente a parte mais importante dessa história.",
            "rationale": "Cria curiosidade factual e convida a buscar o contexto completo no perfil.",
            "stopScore": 8,
            "profileScore": 9,
            "complianceNotes": "Não transforma a tendência em certeza clínica ou recomendação individual.",
        },
        {
            "strategy": "Contraste direto",
            "title": "Antes de repetir isso",
            "hook": f"Você ouviu falar de {topic}.",
            "turn": "Existe uma diferença crucial.",
            "spokenText": f"Você ouviu falar de {topic}. Mas existe uma diferença crucial que muda tudo agora.",
            "rationale": "Usa contraste e comando curto para produzir orientação imediata no scroll.",
            "stopScore": 9,
            "profileScore": 8,
            "complianceNotes": "Evita medo, urgência falsa, vergonha e linguagem prescritiva.",
        },
    ]
    if payload.durationSeconds == 15:
        for row in rows:
            row["spokenText"] = f'{row["spokenText"]} {payload.outro}'
    return {
        "analysis": {
            "capturePotential": 8,
            "audienceReflex": "Interromper o scroll por contraste e curiosidade, antes de entregar uma explicação profunda.",
            "recommendedAngle": "Abrir uma lacuna factual e direcionar a pessoa ao perfil para buscar contexto.",
            "riskNotes": ["Não prometer resultado.", "Não usar antes e depois.", "Não prescrever ou diagnosticar."],
        },
        "variants": rows,
    }


def _normalize_capture_hooks(payload: CaptureHooksIn, raw: Any) -> dict[str, Any]:
    fallback = _capture_hooks_fallback(payload)
    if not isinstance(raw, dict):
        raw = fallback
    raw_analysis = raw.get("analysis") if isinstance(raw.get("analysis"), dict) else {}
    try:
        capture_potential = max(1, min(10, int(raw_analysis.get("capturePotential") or 1)))
    except (TypeError, ValueError):
        capture_potential = fallback["analysis"]["capturePotential"]
    analysis = {
        "capturePotential": capture_potential,
        "audienceReflex": str(raw_analysis.get("audienceReflex") or fallback["analysis"]["audienceReflex"]).strip()[:600],
        "recommendedAngle": str(raw_analysis.get("recommendedAngle") or fallback["analysis"]["recommendedAngle"]).strip()[:600],
        "riskNotes": [str(item).strip()[:300] for item in raw_analysis.get("riskNotes", [])[:5] if str(item).strip()]
        or fallback["analysis"]["riskNotes"],
    }
    raw_variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    variants: list[dict[str, Any]] = []
    for index in range(3):
        base = fallback["variants"][index]
        item = raw_variants[index] if index < len(raw_variants) and isinstance(raw_variants[index], dict) else {}
        spoken_text = re.sub(r"\s+", " ", str(item.get("spokenText") or "")).strip()
        if payload.durationSeconds == 10:
            spoken_text = re.sub(
                r"\s*(?:veja|acesse|confira|siga|me\s+siga)\b.{0,80}$",
                "",
                spoken_text,
                flags=re.I,
            ).strip()
        else:
            spoken_text = _normalize_generated_outro(spoken_text, payload.outro)
        spoken_text = spoken_text if spoken_text else base["spokenText"]
        word_count = len(spoken_text.split())
        minimum_words, maximum_words = ((18, 24) if payload.durationSeconds == 10 else (25, 36))
        if word_count < minimum_words or word_count > maximum_words:
            spoken_text = base["spokenText"]

        def score(name: str) -> int:
            try:
                return max(1, min(10, int(item.get(name) or base[name])))
            except (TypeError, ValueError):
                return int(base[name])

        variants.append(
            {
                "variant": index + 1,
                "strategy": str(item.get("strategy") or base["strategy"]).strip()[:100],
                "title": str(item.get("title") or base["title"]).strip()[:160],
                "hook": str(item.get("hook") or base["hook"]).strip()[:400],
                "turn": str(item.get("turn") or base["turn"]).strip()[:400],
                "spokenText": spoken_text,
                "wordCount": len(spoken_text.split()),
                "rationale": str(item.get("rationale") or base["rationale"]).strip()[:600],
                "stopScore": score("stopScore"),
                "profileScore": score("profileScore"),
                "complianceNotes": str(item.get("complianceNotes") or base["complianceNotes"]).strip()[:600],
            }
        )
    return {"analysis": analysis, "variants": variants}


def _capture_hooks_system(duration_seconds: int, editorial_tone: str, outro: str) -> str:
    tone_direction = {
        "positivo": "Enquadre oportunidades de forma construtiva, sem prometer resultados.",
        "neutro": "Use linguagem jornalística, equilibrando achado, contexto e limite.",
        "apreensivo": "Destaque riscos reais e incertezas, sem alarmismo ou urgência falsa.",
    }.get(editorial_tone, "Use linguagem jornalística e equilibrada.")
    duration_rule = (
        "Cada spokenText deve ter entre 18 e 24 palavras. Videos de 10 segundos nao usam frase final ou CTA falado."
        if duration_seconds == 10
        else f'Cada spokenText deve ter entre 25 e 36 palavras e terminar exatamente com: "{outro}"'
    )
    return f"""Voce e um estrategista brasileiro de aquisicao para videos verticais.
Avalie uma tendencia e crie EXATAMENTE 3 roteiros independentes de captura, cada um com cerca de {duration_seconds} segundos.

Objetivo:
- interromper o scroll em menos de meio segundo;
- gerar surpresa ou curiosidade factual;
- levar a pessoa ao perfil, onde ela encontrara o conteudo aprofundado;
- testar tres hipoteses de gancho, nao resumir uma mensagem longa.

Regras obrigatorias:
- Escreva em portugues brasileiro, direto e natural.
- Tom editorial escolhido: {editorial_tone}. {tone_direction}
- {duration_rule}
- As tres estrategias precisam ser claramente diferentes: quebra de padrao, lacuna de informacao e contraste/pergunta.
- Comece pelo impacto. Nao use saudacao, apresentacao ou contextualizacao lenta.
- Baseie afirmacoes na tendencia e na fonte fornecida. Se um fato nao estiver sustentado, nao invente.
- Nao entregue toda a explicacao; abra uma lacuna honesta para o perfil.
- Nao use promessa de resultado, diagnostico, prescricao, dose, medo falso, body shaming ou transformacao corporal de antes/depois.
- Avalie potencial de captura, reflexo esperado, melhor angulo, riscos, poder de parada e chance de visita ao perfil.
- Responda somente no JSON solicitado.
"""

_EXPAND_IDEAS_SYSTEM = """Voce e estrategista editorial de videos curtos para um medico brasileiro.
Transforme uma ideia bruta em ideias melhores para Reels, TikTok e Shorts.

Regras obrigatorias:
- Conteudo educativo e nao prescritivo.
- Nao cite doses.
- Nao prometa resultado.
- Nao use cura, milagre, garantia ou sensacionalismo medico.
- Nao incentive uso de medicamento sem avaliacao individual.
- Crie titulos especificos, com dor clara, sem ficar generico.
- Se houver CONTEUDO DA FONTE, cada ideia deve usar pelo menos dois fatos concretos dessa fonte
  (nomes, numeros, indicacoes, mudancas regulatorias ou limites). Nao apenas repita a manchete.
- Diferencie com precisao registro/aprovacao, indicacao autorizada, disponibilidade comercial e promessa de resultado.
- O angulo deve entregar ao futuro roteirista contexto factual suficiente para explicar a noticia sem reabrir o link.
- Nao substitua fatos por avisos genericos de compliance. Compliance e uma camada, nao o assunto do video.
- Escreva hooks em fala natural brasileira.
- Contextualize a dor do publico e o angulo do roteiro.
- Extraia a tese central do briefing. Nao use frases como "perguntei se" ou pedacos de conversa como titulo.
- Quando houver estudo, congresso ou dado numerico, trate como "estudos sugerem/associam", nunca como certeza absoluta.
- Gere ideias diferentes entre si: uma de descoberta, uma de alerta/cuidado e uma de mito/limite.
- CTA deve ser simples e seguro.
- Responda somente no JSON solicitado."""


_ARTICLE_ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tituloArtigo": {"type": "string"},
                "achadoPrincipal": {"type": "string"},
                "tipoEstudo": {"type": "string"},
                "populacao": {"type": "string"},
                "amostra": {"type": "string"},
                "seguimento": {"type": "string"},
                "numerosChave": {"type": "array", "items": {"type": "string"}},
                "limitacoes": {"type": "array", "items": {"type": "string"}},
                "podeFalar": {"type": "array", "items": {"type": "string"}},
                "naoPodeFalar": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "tituloArtigo",
                "achadoPrincipal",
                "tipoEstudo",
                "populacao",
                "amostra",
                "seguimento",
                "numerosChave",
                "limitacoes",
                "podeFalar",
                "naoPodeFalar",
            ],
        },
        "ideas": _EXPAND_IDEAS_SCHEMA["properties"]["ideas"],
    },
    "required": ["analysis", "ideas"],
}

_ARTICLE_ANALYSIS_SYSTEM = """Voce e analista cientifico-editorial para um medico brasileiro.
Transforme artigo cientifico em ideias de videos curtos sem extrapolar evidência.

Regras obrigatorias:
- Diferencie associacao, causalidade, hipotese biologica e recomendacao clinica.
- Nunca diga que medicamento previne, cura ou trata cancer se o artigo nao for ensaio prospectivo desenhado para isso.
- Nao cite doses.
- Nao prescreva conduta.
- Destaque limites do estudo de forma simples.
- Gere ideias especificas, com titulos fortes mas nao sensacionalistas.
- Cada ideia deve ser pronta para virar roteiro educativo.
- No campo "angulo" de cada ideia, inclua um briefing completo para o avatar: tese central, dado principal, contexto da população, limite do estudo, virada narrativa e cuidado médico final.
- O avatar precisa conseguir falar o vídeo só com titulo, hook, angulo, publicoDor, cta e observacaoCompliance.
- Priorize a notícia: use cerca de 80% da ideia para o fato central, exemplos concretos e o motivo de ele importar para quem assiste.
- Para temas de risco/efeito adverso, dê exemplos específicos que estejam no artigo e separe o que é comum do que merece atenção. Evite uma lista longa e não invente sintomas.
- O alerta clínico entra somente no fechamento, em uma frase curta de segurança; ele não pode dominar hook, título ou explicação.
- Busque potencial de atenção sem sensacionalismo: comece por contraste, surpresa, dúvida real ou consequência prática verificável na fonte.
- Use exclusivamente o artigo recebido nesta chamada. Antes de escrever, identifique o tema no título ou no primeiro parágrafo; cada título e hook deve repetir termos ou conclusões verificáveis dessa fonte.
- Se a fonte não mencionar GLP-1, medicamentos, câncer ou outro assunto clínico, não introduza esses assuntos nas ideias.
- Responda somente no JSON solicitado."""


def _article_compact_text(text: str, limit: int = 24000) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    head = cleaned[: int(limit * 0.58)]
    tail = cleaned[-int(limit * 0.32):]
    return f"{head}\n\n[... trecho intermediario omitido para caber na analise ...]\n\n{tail}"


def _article_source_text(text: str) -> str:
    """Remove pedacos da UI quando o usuario cola o modal inteiro por acidente."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Arquivos .mhtml carregam HTML e imagens em MIME/quoted-printable. Ao
    # colar seu conteúdo, extraímos somente o texto legível da página antes de
    # analisar; assim o Claude não recebe cabeçalhos técnicos ou páginas antigas.
    if "MIME-Version:" in cleaned and "Content-Type:" in cleaned:
        try:
            message = Parser(policy=policy.default).parsestr(cleaned)
            html_parts: list[str] = []
            text_parts: list[str] = []
            for part in message.walk():
                if part.is_multipart():
                    continue
                content_type = part.get_content_type()
                if content_type not in {"text/html", "text/plain"}:
                    continue
                content = part.get_content()
                if not isinstance(content, str):
                    continue
                if content_type == "text/html":
                    html_parts.append(content)
                else:
                    text_parts.append(content)
            if html_parts:
                parser = _ArticleTextParser()
                parser.feed(max(html_parts, key=len))
                extracted = parser.text()
                if len(extracted) >= 120:
                    cleaned = extracted
            elif text_parts:
                extracted = max(text_parts, key=len).strip()
                if len(extracted) >= 120:
                    cleaned = extracted
        except Exception:
            # Se o arquivo estiver incompleto, o fluxo abaixo ainda tenta
            # aproveitar o texto colado sem impedir a importação.
            pass
    cut_markers = [
        "\nLink, DOI ou PubMed",
        "\nO que a IA entendeu",
        "\nIdeias a partir do artigo",
        "\nAnalisar artigo\nO que a IA entendeu",
    ]
    cut_positions = [cleaned.find(marker) for marker in cut_markers if cleaned.find(marker) >= 0]
    if cut_positions:
        cleaned = cleaned[: min(cut_positions)]
    lines = [line.strip() for line in cleaned.splitlines()]
    drop_prefixes = {
        "Importar artigo",
        "Cole artigo, resumo, abstract, link ou DOI",
    }
    useful_lines = [
        line
        for line in lines
        if line
        and line not in drop_prefixes
        and not re.fullmatch(r"\d{1,5}/50000", line)
    ]
    return "\n".join(useful_lines).strip()


def _extract_article_numbers(text: str) -> list[str]:
    normalized = (
        text.replace("\u2009", " ")
        .replace("\u202f", " ")
        .replace("–", "-")
        .replace("−", "-")
    )
    patterns = [
        r"\b(?:HR|hazard ratio)\s*(?:was|of|=|:)?\s*\d+(?:[\.,]\d+)?(?:\s*,?\s*95%\s*(?:CI|confidence interval)?\s*(?:of)?\s*\d+(?:[\.,]\d+)?\s*(?:-|to)\s*\d+(?:[\.,]\d+)?)?",
        r"\bmedian follow-up\s+(?:of\s+)?\d+(?:[\.,]\d+)?\s+years?\b",
        r"\b\d{2,3}(?:[ ,]\d{3})+\s+(?:patients|individuals|participants|people)\b",
        r"\bcohort included\s+\d{2,3}(?:[ ,]\d{3})+\s+(?:patients|individuals|participants|people)\b",
        r"\b\d+(?:[\.,]\d+)?%\s*\([^)]{0,40}\)",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.I):
            value = re.sub(r"\s+", " ", match.group(0)).strip(" .,;")
            value = _format_article_number(value)
            if value and value not in found:
                found.append(value)
    return found[:6]


def _format_article_number(value: str) -> str:
    formatted = value
    formatted = re.sub(r"\bhazard ratio\b", "HR", formatted, flags=re.I)
    formatted = re.sub(r"\b95%\s*confidence interval\b", "IC 95%", formatted, flags=re.I)
    formatted = re.sub(r"\b95%\s*CI\b", "IC 95%", formatted, flags=re.I)
    formatted = re.sub(r"\bmedian follow-up of ([\d\.,]+) years?\b", r"seguimento mediano de \1 anos", formatted, flags=re.I)
    formatted = re.sub(r"\bmedian follow-up ([\d\.,]+) years?\b", r"seguimento mediano de \1 anos", formatted, flags=re.I)
    formatted = re.sub(r"\bcohort included\b", "coorte incluiu", formatted, flags=re.I)
    formatted = re.sub(r"\bpatients\b", "pacientes", formatted, flags=re.I)
    formatted = re.sub(r"\bindividuals\b", "individuos", formatted, flags=re.I)
    formatted = re.sub(r"\bparticipants\b", "participantes", formatted, flags=re.I)
    formatted = re.sub(r"\bpeople\b", "pessoas", formatted, flags=re.I)
    return formatted


def _article_idea(
    payload: ArticleIdeasIn,
    title: str,
    hook: str,
    angle: str,
    pain: str,
    compliance: str,
    cta: str,
) -> dict[str, Any]:
    return {
        "id": f"i-{uuid.uuid4().hex[:12]}",
        "titulo": title,
        "familia": payload.familia,
        "hook": hook,
        "angulo": angle,
        "tipo": "Reel artigo cientifico",
        "publicoDor": pain,
        "cta": cta,
        "linkOrigem": payload.sourceUrl,
        "observacaoCompliance": compliance,
        "prioridade": payload.prioridade,
        "status": "novo",
        "criadoEm": _now(),
    }


def _article_skin_ideas(payload: ArticleIdeasIn, compliance: str) -> list[dict[str, Any]]:
    context = (
        "Contexto para o avatar: explique que perda de peso importante pode mudar sustentacao "
        "facial, flacidez e qualidade da pele. A mensagem nao e que a tirzepatida envelhece a pele, "
        "mas que o corpo inteiro se adapta ao emagrecimento. Reforce acompanhamento individual, "
        "nutricao, massa muscular e dermatologia quando fizer sentido."
    )
    return [
        _article_idea(
            payload,
            "A caneta emagrece, mas a pele acompanha?",
            "Quando o peso cai rápido, a pele nem sempre acompanha no mesmo ritmo.",
            f"{context} Estrutura da fala: comece pela pergunta do espelho, explique perda de gordura de suporte, acolha a surpresa do paciente e finalize com cuidado integrado.",
            "Pessoa que emagreceu ou quer emagrecer com caneta e tem medo de flacidez, rosto cansado ou mudanca na imagem.",
            compliance,
            "Salve para lembrar que emagrecer tambem pede cuidado com pele e massa muscular.",
        ),
        _article_idea(
            payload,
            "Tirzepatida não envelhece a pele",
            "A tirzepatida envelhece a pele? Não é bem assim.",
            f"{context} Estrutura da fala: desmonte o mito, explique que a mudanca visual vem da perda de volume e mostre por que planejar o acompanhamento evita sustos.",
            "Pessoa que ouviu falar em rosto envelhecido depois de emagrecer e quer entender sem panico.",
            compliance,
            "Compartilhe com quem acha que toda mudança no espelho é culpa direta do remédio.",
        ),
        _article_idea(
            payload,
            "O emagrecimento que aparece no rosto",
            "Tem um efeito do emagrecimento que quase ninguém conversa antes: o rosto muda.",
            f"{context} Estrutura da fala: mostre que gordura tambem sustenta tecido, explique sulcos e flacidez em linguagem simples e conecte com prevencao dermatologica sem vender procedimento.",
            "Paciente que esta focado apenas na balanca e nao espera mudancas esteticas durante o processo.",
            compliance,
            "Me siga para entender o tratamento inteiro, não só o número da balança.",
        ),
        _article_idea(
            payload,
            "Pele não é detalhe no tratamento",
            "Cuidar da pele durante o emagrecimento não é vaidade. Pode ser parte do cuidado.",
            f"{context} Estrutura da fala: tire a pele do campo da vaidade, conecte imagem corporal, bem-estar, qualidade da pele e acompanhamento seguro.",
            "Pessoa que acha que cuidado dermatologico so entra depois que o peso alvo chegou.",
            compliance,
            "Salve para conversar sobre isso antes, não só depois.",
        ),
        _article_idea(
            payload,
            "Nem toda mudança é efeito colateral",
            "Nem toda mudança no espelho durante o uso da caneta é efeito colateral direto.",
            f"{context} Estrutura da fala: diferencie efeito direto da medicação, efeito da perda de peso e adaptacao do corpo; finalize orientando avaliacao individual.",
            "Paciente preocupado em abandonar tratamento ao notar flacidez ou rosto mais cansado.",
            compliance,
            "Procure avaliação individual antes de transformar susto em decisão.",
        ),
    ][: payload.quantity]


def _article_generic_ideas(payload: ArticleIdeasIn, text: str, compliance: str) -> dict[str, Any]:
    """Fallback determinístico estritamente ancorado no texto importado.

    Não reutiliza temas clínicos de artigos anteriores quando Claude não está
    disponível. Isso é especialmente importante para textos educativos ou
    links que não tratam de GLP-1.
    """
    clean_lines = [
        re.sub(r"^(?:#{1,6}\s+|[>*-]\s+|\d+[.)]\s+)", "", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]
    heading = next((line for line in clean_lines if len(line) >= 8), "Conteúdo importado")
    body_lines = [line for line in clean_lines if line != heading and len(line) >= 30]
    source_sentence = next(
        (
            sentence.strip()
            for line in body_lines
            for sentence in re.split(r"(?<=[.!?])\s+", line)
            if len(sentence.strip()) >= 35
        ),
        heading,
    )
    subject = re.sub(r"\s+", " ", heading).strip(" .:;—-")[:90]
    source_sentence = re.sub(r"\s+", " ", source_sentence).strip()[:260]
    secondary = next((line for line in body_lines if line != source_sentence), source_sentence)[:220]
    common_angle = (
        "Contexto para o avatar: use somente os pontos apresentados na fonte. "
        f"Trecho-base: {source_sentence} "
        "Explique em linguagem simples, sem transformar a orientação geral em promessa ou prescrição individual."
    )
    analysis = {
        "tituloArtigo": subject,
        "achadoPrincipal": source_sentence,
        "tipoEstudo": "Conteúdo importado para educação",
        "populacao": "Público descrito na fonte importada.",
        "amostra": "Não informada no texto importado.",
        "seguimento": "Não informado no texto importado.",
        "numerosChave": _extract_article_numbers(text) or ["A fonte não trouxe números-chave verificáveis."],
        "limitacoes": [
            "O texto importado pode ser educativo, editorial ou um resumo; não o trate como evidência clínica conclusiva.",
            "Recomendações de saúde precisam respeitar contexto e avaliação individual.",
        ],
        "podeFalar": [
            "O artigo destaca: " + source_sentence,
            "Hábitos consistentes podem ser apresentados como orientação geral, sem prometer resultado.",
        ],
        "naoPodeFalar": [
            "Esta dica garante emagrecimento.",
            "Todo mundo deve seguir a mesma estratégia.",
        ],
    }
    ideas = [
        _article_idea(
            payload,
            subject,
            source_sentence,
            f"{common_angle} Estruture a fala a partir do ponto central do artigo e finalize convidando a pessoa a adaptar o cuidado à própria rotina.",
            "Pessoa que busca entender o tema do artigo sem fórmulas milagrosas.",
            compliance,
            "Salve para revisar este ponto com calma.",
        ),
        _article_idea(
            payload,
            f"{subject}: por onde começar",
            f"O artigo começa com uma ideia simples: {source_sentence}",
            f"{common_angle} Mostre um primeiro passo realista citado na fonte: {secondary}",
            "Pessoa que quer transformar informação em um primeiro passo possível.",
            compliance,
            "Compartilhe com quem precisa de um começo mais realista.",
        ),
        _article_idea(
            payload,
            "O que não dá para concluir só com uma dica",
            f"Uma boa orientação não precisa virar regra para todo mundo. O artigo fala de: {subject}.",
            f"{common_angle} Diferencie informação geral de decisão individual e evite tom de cobrança.",
            "Pessoa cansada de promessas rápidas ou regras universais de saúde.",
            compliance,
            "Salve para lembrar: contexto também faz parte do cuidado.",
        ),
    ][: payload.quantity]
    return {"analysis": analysis, "ideas": ideas}


def _article_adverse_effect_ideas(
    payload: ArticleIdeasIn,
    text: str,
    compliance: str,
) -> dict[str, Any]:
    """Ideias curtas e factuais para notícias sobre efeitos adversos de GLP-1.

    A notícia e os exemplos da fonte ocupam a maior parte da narrativa. A
    orientação clínica fica restrita ao fechamento, sem tomar o lugar do fato.
    """
    lowered = text.lower()
    examples: list[str] = []
    for label, pattern in [
        # Alguns MHTML antigos chegam com acentos substituídos por caracteres
        # de reparação; a forma flexível preserva o fato sem inventar nada.
        ("náusea", r"n(?:[aá]|[^\s]{1,4}usea)"),
        ("diarreia", r"diarreia"),
        ("prisão de ventre", r"pris[aã]o de ventre|constipa"),
        ("hipoglicemia", r"hipoglicemia"),
        ("pancreatite", r"pancreatite"),
        ("problemas na vesícula", r"ves[ií]cula"),
    ]:
        if re.search(pattern, lowered) and label not in examples:
            examples.append(label)
    common = [item for item in examples if item in {"náusea", "diarreia", "prisão de ventre"}]
    attention = [item for item in examples if item not in common]
    common_text = ", ".join(common[:3]) or "os efeitos mais citados pela matéria"
    attention_text = ", ".join(attention[:3]) or "sinais que merecem atenção"
    source_lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 35]
    source_fact = next(
        (line for line in source_lines if any(item in line.lower() for item in examples)),
        "A matéria separa desconfortos frequentes de sinais que não devem ser ignorados.",
    )
    source_fact = re.sub(r"\s+", " ", source_fact)[:320]
    subject = "Efeitos colaterais do Mounjaro" if "mounjaro" in lowered else "Efeitos colaterais das canetas para emagrecer"
    context = (
        "Contexto para o avatar: abra pela notícia, não pelo aviso médico. "
        f"Explique que a fonte cita {common_text} entre os efeitos mais conhecidos e traz {attention_text} como exemplos que mudam a conversa. "
        "Use exemplos concretos da matéria, em ritmo de notícia, e deixe o cuidado clínico apenas na última frase."
    )
    analysis = {
        "tituloArtigo": subject,
        "achadoPrincipal": source_fact,
        "tipoEstudo": "Artigo de saúde importado",
        "populacao": "Leitores e pacientes descritos na fonte importada.",
        "amostra": "Não aplicável ao artigo informativo importado.",
        "seguimento": "Não aplicável ao artigo informativo importado.",
        "numerosChave": _extract_article_numbers(text) or ["A fonte foi usada como notícia explicativa, sem número central destacado."],
        "limitacoes": [
            "O artigo informativo não substitui bula, avaliação de sintomas ou orientação individual.",
            "Os exemplos precisam ser apresentados como riscos possíveis, nunca como diagnóstico ou certeza para todos.",
        ],
        "podeFalar": [
            f"A fonte cita {common_text} como efeitos que costumam aparecer na conversa sobre o medicamento.",
            f"A matéria também chama atenção para {attention_text}, sem transformar isso em pânico.",
        ],
        "naoPodeFalar": [
            "Todo usuário terá um efeito grave.",
            "Interrompa ou comece medicamento por conta própria.",
        ],
    }
    closing = "Se aparecer um sintoma forte, persistente ou diferente do esperado, procure orientação médica."
    ideas = [
        _article_idea(
            payload,
            "O efeito do Mounjaro que vai além da náusea",
            f"Náusea é o que todo mundo comenta. Mas a matéria mostra que {attention_text} também entram na conversa sobre Mounjaro.",
            f"{context} Estrutura da fala: 1) contraste a náusea com os outros riscos citados; 2) dê exemplos em linguagem simples; 3) explique por que a lista não é motivo para pânico, mas para informação. Feche somente com: {closing}",
            "Pessoa que conhece o remédio pelas redes sociais e quer entender riscos sem alarmismo.",
            compliance,
            "Salve para reconhecer o que vale conversar no acompanhamento.",
        ),
        _article_idea(
            payload,
            "Nem todo efeito colateral tem o mesmo peso",
            f"A matéria fala de {common_text}; mas também cita {attention_text}. E essa diferença importa.",
            f"{context} Estrutura da fala: mostre a diferença entre desconforto comum e sinal de atenção sem ensinar diagnóstico. Use a notícia como guia e reserve uma única frase final: {closing}",
            "Pessoa que ouviu relatos soltos e não sabe como interpretar o que é frequente e o que pede atenção.",
            compliance,
            "Envie para quem só ouviu falar da náusea.",
        ),
        _article_idea(
            payload,
            "O que a notícia sobre Mounjaro deixa claro",
            f"Não é só sobre emagrecer: a fonte relembra efeitos como {common_text} e riscos como {attention_text}.",
            f"{context} Estrutura da fala: mantenha o foco nos fatos do artigo, com exemplos curtos e diretos. Encerramento em uma linha: {closing}",
            "Pessoa avaliando o tema a partir de manchetes e relatos nas redes sociais.",
            compliance,
            "Compartilhe para a conversa sair do boato e ir para informação.",
        ),
    ][: payload.quantity]
    return {"analysis": analysis, "ideas": ideas}


def _manual_article_analysis(payload: ArticleIdeasIn) -> dict[str, Any]:
    text = _article_source_text(payload.article)
    lowered = text.lower()
    glp = bool(re.search(r"glp|semaglutide|semaglutida|tirzepatide|tirzepatida|mounjaro|ozempic", lowered))
    cancer = bool(re.search(r"cancer|câncer|tumou?r|oncolog|malignan|neoplasm", lowered))
    skin = bool(re.search(r"pele|flacidez|col[aá]geno|rosto|dermatolog|cut[aâ]ne|cicatriz|hidradenite|psor[ií]ase|queda de cabelo", lowered))
    adverse_effects = bool(re.search(r"efeitos? colaterais|adverse|hipoglicemia|pancreatite|ves[ií]cula|n[aá]usea", lowered))
    observational = bool(re.search(r"cohort|observational|retrospective|target trial emulation|trinetx", lowered))
    numbers = _extract_article_numbers(text)
    sample = next(
        (
            n
            for n in numbers
            if re.search(
                r"patients|pacientes|individuals|individuos|participants|participantes|people|pessoas",
                n,
                re.I,
            )
        ),
        "Amostra descrita no artigo.",
    )
    follow_up = next(
        (n for n in numbers if "follow-up" in n.lower() or "seguimento" in n.lower()),
        "Seguimento descrito no artigo.",
    )
    primary_hr = next((n for n in numbers if re.search(r"\b(?:HR|hazard ratio)\b", n, re.I)), "")
    study_type = (
        "Coorte observacional com emulação de ensaio-alvo"
        if "target trial emulation" in lowered
        else "Estudo observacional"
        if observational
        else "Artigo de opinião/revisão editorial"
        if "opinião" in lowered or "opinion" in lowered
        else "Artigo cientifico"
    )
    finding = (
        "Uso de GLP-1RA foi associado a menor incidência de cânceres relacionados à obesidade no curto prazo."
        if glp and cancer
        else "Perda de peso importante com tirzepatida pode trazer mudanças perceptíveis na pele e no rosto, exigindo cuidado integrado."
        if glp and skin
        else "O artigo traz um achado promissor, mas precisa ser comunicado como evidência em contexto."
    )
    compliance = (
        "Tratar como associacao observacional; nao afirmar prevencao, tratamento ou protecao garantida; reforcar avaliacao individual e exames de rastreio."
        if glp and cancer
        else "Nao afirmar que o medicamento envelhece a pele; nao prometer resultado estetico; reforcar avaliacao individual, nutricao, massa muscular e acompanhamento dermatologico quando indicado."
        if glp and skin
        else "Nao extrapolar o artigo; separar achado, limite e orientacao individual."
    )
    # Em páginas longas, itens de navegação podem conter a palavra "pele".
    # Quando a matéria é claramente sobre efeitos adversos, esse assunto deve
    # prevalecer sobre um falso sinal de conteúdo dermatológico.
    if glp and adverse_effects and not cancer:
        return _article_adverse_effect_ideas(payload, text, compliance)
    if glp and skin and not cancer:
        analysis = {
            "tituloArtigo": "Tirzepatida, emagrecimento e pele",
            "achadoPrincipal": finding,
            "tipoEstudo": study_type,
            "populacao": "Pessoas em tratamento de emagrecimento com tirzepatida ou GLP-1/GIP, conforme texto importado.",
            "amostra": sample,
            "seguimento": follow_up,
            "numerosChave": numbers or ["Texto editorial sem numeros principais; revisar fontes cientificas antes de publicar como evidência."],
            "limitacoes": [
                "Texto de opinião/editorial não prova causalidade.",
                "Mudanças na pele dependem de velocidade de perda de peso, idade, genética, massa muscular e histórico individual.",
                "Relatos sobre melhora de doenças cutâneas ainda não devem virar recomendação clínica geral.",
            ],
            "podeFalar": [
                "Perda de peso relevante pode reduzir volume de suporte e deixar flacidez ou sulcos mais perceptíveis.",
                "A medicação não deve ser descrita como causa direta de envelhecimento da pele.",
                "Acompanhamento nutricional, muscular e dermatológico pode ajudar a planejar melhor o processo.",
            ],
            "naoPodeFalar": [
                "Tirzepatida envelhece a pele.",
                "Todo paciente precisa fazer procedimento estético.",
                "Protocolo de colágeno resolve ou previne flacidez para todos.",
            ],
        }
        return {"analysis": analysis, "ideas": _article_skin_ideas(payload, compliance)}
    if not (glp and cancer):
        return _article_generic_ideas(payload, text, compliance)
    follow_up_context = (
        f"com {follow_up.lower()}"
        if follow_up != "Seguimento descrito no artigo."
        else "com seguimento descrito no artigo"
    )
    evidence_context = (
        "Contexto para o avatar: explique que foi uma coorte observacional em adultos com obesidade sem diabetes. "
        f"O dado central foi {primary_hr or 'uma associacao estatistica favoravel'}, {follow_up_context}. "
        "Deixe claro que isso não prova causalidade, não substitui rastreio e não vira indicação de remédio."
    )
    analysis = {
        "tituloArtigo": "Artigo importado",
        "achadoPrincipal": finding,
        "tipoEstudo": study_type,
        "populacao": "Adultos com obesidade, sem diabetes, conforme texto importado." if glp and cancer else "Populacao descrita no artigo importado.",
        "amostra": sample,
        "seguimento": follow_up,
        "numerosChave": numbers or ["Extrair numeros principais antes de publicar."],
        "limitacoes": [
            "Desenho observacional nao prova causalidade.",
            "Seguimento curto pode nao capturar desfechos de longo prazo.",
            "Pode haver confundimento residual mesmo com ajuste estatistico.",
        ],
        "podeFalar": [
            "O estudo encontrou associacao com menor incidencia, nao prova de protecao garantida.",
            "Os autores pedem estudos prospectivos para confirmar causalidade.",
            "Exames preventivos e acompanhamento medico continuam necessarios.",
        ],
        "naoPodeFalar": [
            "Caneta previne câncer.",
            "GLP-1 trata câncer.",
            "Todo paciente deve usar medicamento por esse motivo.",
        ],
    }
    ideas = [
        _article_idea(
            payload,
            "Canetas reduzem risco de câncer? Calma.",
            "Caneta emagrecedora pode reduzir risco de câncer? A resposta honesta começa com uma palavra: associação.",
            f"{evidence_context} Estrutura da fala: comece pela dúvida da manchete, traduza o estudo em linguagem simples, explique a diferença entre associação e prevenção, e finalize dizendo que a decisão continua individual.",
            "Pessoa que viu manchete sobre GLP-1 e câncer e quer saber se isso muda sua conduta.",
            compliance,
            "Salve para lembrar: artigo promissor não substitui avaliação individual.",
        ),
        _article_idea(
            payload,
            "O rodapé que a manchete não conta",
            "A manchete fala em menos câncer. Mas o rodapé do estudo é onde mora a parte mais importante.",
            f"{evidence_context} Estrutura da fala: mostre o achado principal, depois puxe o espectador para o rodapé: população estudada, comparador, seguimento curto e pedido dos autores por estudos prospectivos.",
            "Pessoa animada com novidade científica, mas sem repertório para interpretar limite de estudo.",
            compliance,
            "Compartilhe com alguém que precisa entender a notícia inteira.",
        ),
        _article_idea(
            payload,
            "HR 0,59 não é escudo contra câncer",
            "Quando um estudo fala em HR 0,59, isso não significa que você ganhou um escudo contra câncer.",
            f"{evidence_context} Estrutura da fala: explique o número sem aula estatística longa, traduza como menor incidência observada no grupo estudado e deixe claro que número populacional não é promessa individual.",
            "Pessoa que se impressiona com número científico e pode transformar estatística em promessa pessoal.",
            compliance,
            "Me siga para entender estudo sem cair em promessa bonita demais.",
        ),
        _article_idea(
            payload,
            "GLP-1, obesidade e câncer: o que dá para dizer",
            "Existe uma conversa séria entre obesidade, inflamação, GLP-1 e câncer. Mas séria não quer dizer mágica.",
            f"{evidence_context} Estrutura da fala: conecte obesidade e risco oncológico com cautela, cite que há hipóteses biológicas em estudo e separe isso de uma afirmação de tratamento ou prevenção.",
            "Paciente tentando entender se emagrecer muda risco de saúde além da balança.",
            compliance,
            "Salve para conversar com seu médico com mais contexto.",
        ),
        _article_idea(
            payload,
            "Caneta não substitui rastreio",
            "Mesmo que um estudo seja promissor, ele não cancela mamografia, colonoscopia ou acompanhamento médico.",
            f"{evidence_context} Estrutura da fala: use o artigo como gancho para explicar que tratamento de obesidade e prevenção oncológica são complementares; exame de rastreio não sai da rotina por causa de uma manchete.",
            "Pessoa inclinada a abandonar exame preventivo por confiar demais em uma medicação.",
            compliance,
            "Encaminhe para quem transforma manchete em decisão de saúde.",
        ),
    ]
    return {"analysis": analysis, "ideas": ideas[: payload.quantity]}


def _manual_idea_fallback(payload: ExpandIdeasIn) -> list[dict[str, Any]]:
    seed = re.sub(r"\s+", " ", payload.seed).strip()
    lowered = seed.lower()
    medication = bool(
        re.search(
            r"glp|mounjaro|ozempic|wegovy|semaglutida|tirzepatida|rem[eé]dio|medica[cç][aã]o|caneta",
            lowered,
        )
    )
    family = "medicamento" if medication else payload.familia
    compliance = (
        "Nao prescrever, nao citar dose, nao prometer resultado e reforcar avaliacao individual."
        if medication
        else "Evitar promessa de resultado, diagnostico direto e culpabilizacao."
    )
    if re.search(r"c[aâ]ncer|tumor|oncolog|asco|met[aá]stase", lowered) and medication:
        return _manual_glp_cancer_ideas(payload, family, compliance, _research_context_for_seed(seed))
    if re.search(r"contraindica|nem2|tireoide|pirataria|falsificad|sem registro|receita", lowered) and medication:
        return _manual_medication_safety_ideas(payload, family, compliance, _research_context_for_seed(seed))
    topic = _idea_seed_topic(seed)
    angles = [
        (
            f"{topic}: o erro que quase ninguem percebe",
            f"Tem uma parte sobre {topic} que parece simples, mas costuma ser explicada do jeito errado.",
            "Abrir com a crenca comum, mostrar o contexto que falta e virar para uma orientacao educativa.",
            "Pessoa que viu uma explicacao curta demais e quer entender sem cair em atalho.",
        ),
        (
            f"{topic}: antes de transformar isso em regra",
            f"Antes de transformar {topic} em regra para todo mundo, vale olhar para o contexto.",
            "Explorar quando a dica faz sentido, quando pode confundir e por que avaliacao individual importa.",
            "Pessoa tentando copiar uma conduta pronta da internet para a propria rotina.",
        ),
        (
            f"{topic}: a verdade menos conveniente",
            f"A verdade sobre {topic} talvez seja menos chamativa, mas e bem mais util.",
            "Trocar promessa facil por explicacao pratica, segura e conectada ao comportamento.",
            "Pessoa cansada de promessas rapidas e procurando um criterio mais realista.",
        ),
    ]
    return [
        {
            "id": f"i-{uuid.uuid4().hex[:12]}",
            "titulo": title,
            "familia": family,
            "hook": hook,
            "angulo": angle,
            "tipo": "Reel educativo contextualizado",
            "publicoDor": pain,
            "cta": "Salve para rever antes de transformar conteudo curto em decisao de saude.",
            "linkOrigem": payload.sourceUrl,
            "observacaoCompliance": compliance,
            "prioridade": payload.prioridade,
            "status": "novo",
            "criadoEm": _now(),
        }
        for title, hook, angle, pain in angles[: payload.quantity]
    ]


def _idea_base(
    payload: ExpandIdeasIn,
    family: str,
    compliance: str,
    title: str,
    hook: str,
    angle: str,
    pain: str,
    cta: str,
    tipo: str = "Reel educativo contextualizado",
) -> dict[str, Any]:
    return {
        "id": f"i-{uuid.uuid4().hex[:12]}",
        "titulo": title,
        "familia": family,
        "hook": hook,
        "angulo": angle,
        "tipo": tipo,
        "publicoDor": pain,
        "cta": cta,
        "linkOrigem": payload.sourceUrl,
        "observacaoCompliance": compliance,
        "prioridade": payload.prioridade,
        "status": "novo",
        "criadoEm": _now(),
    }


def _manual_glp_cancer_ideas(
    payload: ExpandIdeasIn,
    family: str,
    compliance: str,
    research_context: str = "",
) -> list[dict[str, Any]]:
    suffix = f" Fontes para checagem: {research_context}" if research_context else ""
    ideas = [
        _idea_base(
            payload,
            family,
            compliance + " Tratar reducao de risco como associacao/estudo promissor, nao como promessa de protecao.",
            "Canetas emagrecedoras reduzem risco de câncer?",
            "Caneta emagrecedora pode diminuir risco de câncer? A resposta curta é: talvez, mas não do jeito mágico que parece.",
            "Explicar que estudos recentes apontam associacao entre GLP-1/perda de peso e menor risco de alguns tumores, mas sem vender a medicacao como prevencao oncologica. Separar efeito do emagrecimento, reducao de inflamacao e hipoteses biologicas ainda em estudo." + suffix,
            "Pessoa que viu uma manchete forte sobre GLP-1 e câncer e quer saber se isso significa protecao garantida.",
            "Salve para lembrar: estudo promissor não é autorização para usar remédio sem avaliação médica.",
        ),
        _idea_base(
            payload,
            family,
            compliance + " Nao dizer que trata cancer; reforcar acompanhamento com medico e exames preventivos.",
            "O que ninguém contou sobre GLP-1 e câncer",
            "A manchete fala em menos câncer. Mas a parte mais importante está no rodapé.",
            "Usar o gancho dos dados de congresso/estudos para mostrar limites: quem foi estudado, que tipo de associacao apareceu, por que isso nao substitui rastreio, consulta, mamografia, colonoscopia ou acompanhamento oncologico quando indicado." + suffix,
            "Pessoa animada com a noticia e inclinada a transformar um achado cientifico em regra pessoal.",
            "Compartilhe com alguém que precisa entender a notícia inteira, não só o título.",
        ),
        _idea_base(
            payload,
            family,
            compliance + " Evitar promessa de emagrecimento, prevencao ou sobrevida.",
            "Caneta não é escudo contra câncer",
            "Se alguém te vendeu caneta emagrecedora como escudo contra câncer, acenda o alerta.",
            "Contrapor marketing simplista com educacao: obesidade e risco oncologico têm relacao, emagrecer pode reduzir fatores de risco, mas medicamento tem indicacao, contraindicações e acompanhamento. Incluir alerta sobre falsificados e uso sem receita." + suffix,
            "Pessoa exposta a promessa agressiva, pirataria ou venda irregular de canetas.",
            "Me siga para entender saúde sem cair em promessa bonita demais.",
        ),
    ]
    return ideas[: payload.quantity]


def _manual_medication_safety_ideas(
    payload: ExpandIdeasIn,
    family: str,
    compliance: str,
    research_context: str = "",
) -> list[dict[str, Any]]:
    suffix = f" Fontes para checagem: {research_context}" if research_context else ""
    ideas = [
        _idea_base(
            payload,
            family,
            compliance,
            "Caneta emagrecedora não começa pelo clique",
            "Se a sua caneta emagrecedora começou num link aleatório, o problema já começou antes da primeira aplicação.",
            "Explorar risco de versões falsificadas, necessidade de receita legitima, acompanhamento e avaliacao de contraindicações antes do uso." + suffix,
            "Pessoa seduzida por compra online, preço baixo ou indicação de terceiros.",
            "Salve para lembrar: medicamento sério exige caminho sério.",
        ),
        _idea_base(
            payload,
            family,
            compliance,
            "Quem não deve usar canetas emagrecedoras?",
            "Tem gente que não deveria usar caneta emagrecedora, mesmo querendo muito emagrecer.",
            "Explicar de forma educativa que historico pessoal/familiar, contraindicações e riscos individuais mudam a indicacao. Evitar listar como prescricao definitiva; orientar consulta." + suffix,
            "Pessoa que acha que todo medicamento famoso serve para todo mundo.",
            "Procure avaliação individual antes de transformar vídeo em decisão médica.",
        ),
        _idea_base(
            payload,
            family,
            compliance,
            "Caneta não substitui exame",
            "Usar medicação não te dá licença para abandonar exames de rotina.",
            "Mostrar que tratamento de peso e prevencao sao trilhos complementares: acompanhamento, exames indicados, rastreios e seguranca continuam importantes." + suffix,
            "Pessoa que confunde estar em tratamento com estar protegida de outros riscos de saúde.",
            "Salve para revisar seus cuidados com acompanhamento profissional.",
        ),
    ]
    return ideas[: payload.quantity]


class _ArticleTextParser(HTMLParser):
    """Extrai texto editorial sem depender de bibliotecas pesadas."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0
        self._capture = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer", "header", "aside", "form"}:
            self._ignored += 1
        if tag in {"article", "main", "p", "h1", "h2", "li"}:
            self._capture += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "header", "aside", "form"}:
            self._ignored = max(0, self._ignored - 1)
        if tag in {"article", "main", "p", "h1", "h2", "li"}:
            self._capture = max(0, self._capture - 1)
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored and self._capture and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def _validate_public_article_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Link da fonte invalido.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Nao foi possivel localizar a fonte.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("A fonte precisa ser um endereco publico.")
    return raw_url.strip()


def _normalize_article_source_url(raw_source: str | None) -> str | None:
    """Aceita URL, DOI ou PMID e devolve uma URL pública para leitura."""
    source = (raw_source or "").strip()
    if not source:
        return None
    source = re.sub(r"^pmid\s*:\s*", "", source, flags=re.I)
    if re.fullmatch(r"\d{6,10}", source):
        return f"https://pubmed.ncbi.nlm.nih.gov/{source}/"
    source = re.sub(r"^doi\s*:\s*", "", source, flags=re.I)
    if re.fullmatch(r"10\.\d{4,9}/\S+", source, flags=re.I):
        return f"https://doi.org/{source}"
    return source


def _fetch_article_context(source_url: str | None) -> str:
    """Baixa somente texto útil da matéria, com limites de rede e de tokens."""
    if not source_url:
        return ""
    try:
        normalized_source = _normalize_article_source_url(source_url)
        if not normalized_source:
            return ""
        url = _validate_public_article_url(resolve_google_news_url(normalized_source))
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VTRVideoCreator/1.0)"},
            timeout=(4, 10),
            stream=True,
        )
        response.raise_for_status()
        _validate_public_article_url(response.url)
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            return ""
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(32_768):
            total += len(chunk)
            if total > 1_500_000:
                break
            chunks.append(chunk)
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    except (requests.RequestException, ValueError):
        return ""

    parser = _ArticleTextParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in " ".join(parser.parts).splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        key = _norm(line)
        if len(line) < 35 or key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)[:12_000]


_TREND_SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "keyPoints": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "keyPoints"],
}


def _trend_summary_fallback(title: str, article: str) -> dict[str, Any]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", article)
        if len(sentence.strip()) >= 55
        and "publicidade" not in _norm(sentence)
        and "leia tambem" not in _norm(sentence)
    ]
    selected = sentences[:4]
    return {
        "summary": " ".join(selected[:2])[:700] or title,
        "keyPoints": [sentence[:260] for sentence in selected[1:4]],
    }


@app.post("/api/trends/summarize")
def summarize_trend_source(payload: TrendSummaryIn) -> dict:
    """Resume a matéria sob demanda e reutiliza o resultado para a mesma URL."""
    article = _fetch_article_context(payload.sourceUrl)
    if not article:
        raise HTTPException(status_code=422, detail="Nao foi possivel ler o conteudo da referencia.")
    cache_payload = {
        "title": payload.title,
        "sourceUrl": payload.sourceUrl,
        "articleHash": hashlib.sha256(article.encode("utf-8")).hexdigest(),
    }
    cached = _ai_cache_get("trends.summarize", cache_payload, max_age_seconds=604800)
    if cached:
        return cached
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"ok": True, "provider": "fallback", **_trend_summary_fallback(payload.title, article)}

    import anthropic

    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=650,
            system=(
                "Resuma noticias de saude em portugues brasileiro claro. "
                "O resumo deve explicar o fato principal, quem foi afetado e o que a manchete pode confundir. "
                "Crie exatamente tres pontos-chave factuais. Nao prescreva, nao invente e nao transforme "
                "registro regulatorio em promessa de eficacia, disponibilidade ou nova indicacao. "
                "Responda somente no JSON solicitado."
            ),
            output_config={"format": {"type": "json_schema", "schema": _TREND_SUMMARY_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": f"TITULO:\n{payload.title}\n\nCONTEUDO DA FONTE:\n{article[:9000]}",
                }
            ],
        )
        parsed = json.loads("".join(getattr(block, "text", "") for block in message.content))
        response = {
            "ok": True,
            "provider": "claude",
            "summary": str(parsed.get("summary") or "").strip()[:900],
            "keyPoints": [str(point).strip()[:300] for point in parsed.get("keyPoints", [])[:3]],
        }
        _record_anthropic_usage("trends.summarize", model, message)
        _ai_cache_put("trends.summarize", cache_payload, response)
        return response
    except Exception:
        return {"ok": True, "provider": "fallback", **_trend_summary_fallback(payload.title, article)}


def _research_context_for_seed(seed: str) -> str:
    query = _research_query_from_seed(seed)
    if not query:
        return ""
    sources = _fetch_google_news_context(query) + _fetch_pubmed_context(query)
    seen: set[str] = set()
    unique: list[str] = []
    for source in sources:
        key = _norm(source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return " | ".join(unique[:5])


def _research_query_from_seed(seed: str) -> str:
    lowered = seed.lower()
    if re.search(r"c[aâ]ncer|tumor|oncolog|asco", lowered) and re.search(
        r"glp|tirzepatida|tirzepatide|semaglutida|semaglutide|caneta|ozempic|mounjaro|wegovy",
        lowered,
    ):
        return "GLP-1 semaglutide tirzepatide cancer risk obesity"
    if re.search(r"pirataria|falsificad|sem registro|receita", lowered):
        return "canetas emagrecedoras falsificadas sem receita risco"
    if re.search(r"contraindica|nem2|tireoide", lowered):
        return "GLP-1 contraindication medullary thyroid carcinoma MEN2"
    return ""


def _fetch_google_news_context(query: str) -> list[str]:
    try:
        import feedparser
    except Exception:
        return []
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query + ' when:30d')}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    out: list[str] = []
    for entry in getattr(feed, "entries", [])[:3]:
        title = str(entry.get("title") or "").strip()
        link = str(entry.get("link") or "").strip()
        if title:
            out.append(f"Google News: {title}" + (f" ({link})" if link else ""))
    return out


def _fetch_pubmed_context(query: str) -> list[str]:
    cancer_query = bool(re.search(r"cancer|tumor|oncolog", query, re.I))
    try:
        search = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "sort": "pub date",
                "retmax": 3,
                "reldate": 365,
                "datetype": "pdat",
            },
            timeout=8,
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        summary = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=8,
        )
        summary.raise_for_status()
        result = summary.json().get("result", {})
    except (requests.RequestException, ValueError):
        return []
    out: list[str] = []
    for pubmed_id in ids:
        row = result.get(pubmed_id) or {}
        title = str(row.get("title") or "").strip().rstrip(".")
        if cancer_query and not re.search(r"cancer|tumou?r|neoplasm|oncolog|risk", title, re.I):
            continue
        if title:
            out.append(f"PubMed: {title} (https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/)")
    return out


def _idea_seed_topic(seed: str) -> str:
    cleaned = re.sub(
        r"^(quero falar que|quero falar sobre|minha ideia e|minha ideia é|pensei em|falar sobre|falar que|quero|queria)\s+",
        "",
        seed.strip(),
        flags=re.I,
    )
    question_match = re.search(r"(canetas? emagrecedoras?.{0,80}c[aâ]ncer|glp-?1.{0,80}c[aâ]ncer|mounjaro.{0,80}c[aâ]ncer|ozempic.{0,80}c[aâ]ncer)", cleaned, re.I)
    if question_match:
        return "canetas emagrecedoras e risco de câncer"
    cleaned = cleaned.split(".")[0].split("?")[0].strip(" ,:;")
    cleaned = re.split(r":|;|\bcasos proibidos\b|\bn[aã]o substitui\b|\balerta\b", cleaned, flags=re.I)[0].strip(" ,:;")
    words = cleaned.split()
    if len(words) > 10:
        cleaned = " ".join(words[:10])
    return cleaned[:90].rstrip(" ,:;.") or "essa ideia"


def _normalize_expanded_ideas(payload: ExpandIdeasIn, rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return _manual_idea_fallback(payload)
    out: list[dict[str, Any]] = []
    for item in rows[: payload.quantity]:
        if not isinstance(item, dict):
            continue
        raw_priority = _norm(item.get("prioridade") or payload.prioridade)
        if "alt" in raw_priority:
            priority = "alta"
        elif "baix" in raw_priority:
            priority = "baixa"
        else:
            priority = payload.prioridade
        family = payload.familia
        if re.search(
            r"glp|mounjaro|ozempic|wegovy|semaglutida|tirzepatida|rem[eé]dio|medica[cç][aã]o|caneta",
            json.dumps(item, ensure_ascii=False),
            re.I,
        ):
            family = "medicamento"
        out.append(
            {
                "id": f"i-{uuid.uuid4().hex[:12]}",
                "titulo": str(item.get("titulo") or "Ideia contextualizada").strip()[:180],
                "familia": family,
                "hook": str(item.get("hook") or "").strip()[:500],
                "angulo": str(item.get("angulo") or "").strip()[:1000],
                "tipo": str(item.get("tipo") or "Reel educativo contextualizado").strip()[:120],
                "publicoDor": str(item.get("publicoDor") or "").strip()[:500],
                "cta": str(item.get("cta") or "Salve para rever com calma.").strip()[:300],
                "linkOrigem": payload.sourceUrl,
                "observacaoCompliance": str(item.get("observacaoCompliance") or "Revisar linguagem antes de gravar.").strip()[:600],
                "prioridade": priority,
                "status": "novo",
                "criadoEm": _now(),
            }
        )
    return out or _manual_idea_fallback(payload)


@app.post("/api/ideas/expand")
def expand_manual_ideas(payload: ExpandIdeasIn) -> dict:
    """Expande uma ideia livre em opcoes editoriais prontas para virar roteiro."""
    research_context = _research_context_for_seed(payload.seed)
    article_context = _fetch_article_context(payload.sourceUrl)
    if not os.getenv("ANTHROPIC_API_KEY"):
        ideas = _manual_idea_fallback(payload)
        for idea in ideas:
            idea["linkOrigem"] = payload.sourceUrl
        return {"ok": True, "provider": "fallback", "ideas": ideas}

    cache_payload = {
        **payload.model_dump(),
        "researchContext": research_context,
        "articleHash": hashlib.sha256(article_context.encode("utf-8")).hexdigest() if article_context else "",
    }
    cached = _ai_cache_get("ideas.expand", cache_payload)
    if cached:
        return cached

    import anthropic

    prompt = (
        f"IDEIA BRUTA:\n{payload.seed}\n\n"
        f"Quantidade: {payload.quantity}\n"
        f"Familia sugerida: {payload.familia}\n"
        f"Prioridade sugerida: {payload.prioridade}\n"
        f"URL DA FONTE: {payload.sourceUrl or 'Nao informada'}\n"
        f"CONTEUDO DA FONTE (use como base factual principal):\n{article_context or 'Conteudo indisponivel; use apenas o briefing e as fontes recentes.'}\n\n"
        f"FONTES RECENTES PARA CONTEXTUALIZAR, SE RELEVANTES:\n{research_context or 'Nenhuma fonte externa encontrada rapidamente.'}\n"
        "Crie variacoes distintas, especificas e prontas para virar roteiro. "
        "Antes de responder, confira se titulo, hook e angulo representam o fato central real da fonte."
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=1800,
            system=_EXPAND_IDEAS_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _EXPAND_IDEAS_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = json.loads(raw_text)
    except anthropic.APIStatusError:
        ideas = _manual_idea_fallback(payload)
        for idea in ideas:
            idea["linkOrigem"] = payload.sourceUrl
        return {"ok": True, "provider": "fallback", "ideas": ideas}
    except Exception:
        ideas = _manual_idea_fallback(payload)
        for idea in ideas:
            idea["linkOrigem"] = payload.sourceUrl
        return {"ok": True, "provider": "fallback", "ideas": ideas}

    response = {
        "ok": True,
        "provider": "claude",
        "ideas": _normalize_expanded_ideas(payload, parsed.get("ideas")),
    }
    _record_anthropic_usage("ideas.expand", model, message)
    _ai_cache_put("ideas.expand", cache_payload, response)
    return response


@app.post("/api/trends/capture-hooks")
def generate_capture_hooks(payload: CaptureHooksIn) -> dict:
    """Avalia uma tendencia e cria tres roteiros curtos para testar captacao."""
    article_context = _fetch_article_context(payload.sourceUrl)
    seed = "\n".join(
        value
        for value in [payload.titulo, payload.subtema, payload.sinal, payload.dorPublico, payload.notas]
        if value
    )
    research_context = _research_context_for_seed(seed)
    cache_payload = {
        "promptVersion": CAPTURE_HOOKS_PROMPT_VERSION,
        **payload.model_dump(),
        "researchContext": research_context,
        "articleHash": hashlib.sha256(article_context.encode("utf-8")).hexdigest() if article_context else "",
    }
    cached = _ai_cache_get("trends.capture_hooks", cache_payload)
    if cached:
        return cached

    if not os.getenv("ANTHROPIC_API_KEY"):
        if payload.requireClaude:
            raise HTTPException(
                status_code=503,
                detail="Claude não está configurado. Nenhum roteiro de captura foi salvo.",
            )
        return {
            "ok": True,
            "provider": "fallback",
            **_normalize_capture_hooks(payload, _capture_hooks_fallback(payload)),
        }

    import anthropic

    prompt = (
        f"TENDENCIA: {payload.titulo}\n"
        f"SUBTEMA: {payload.subtema or 'Nao informado'}\n"
        f"SINAL OBSERVADO: {payload.sinal or 'Nao informado'}\n"
        f"DOR DO PUBLICO: {payload.dorPublico or 'Nao informada'}\n"
        f"NOTAS: {payload.notas or 'Nenhuma'}\n"
        f"FAMILIA EDITORIAL: {payload.familia}\n"
        f"URL DA FONTE: {payload.sourceUrl or 'Nao informada'}\n\n"
        "CONTEUDO DA FONTE (base factual principal):\n"
        f"{article_context or 'Conteudo indisponivel; nao invente numeros ou conclusoes.'}\n\n"
        "CONTEXTO RECENTE COMPLEMENTAR:\n"
        f"{research_context or 'Nenhuma fonte complementar encontrada.'}\n\n"
        "Crie tres testes de captura independentes. Eles devem provocar orientacao e curiosidade, "
        "nao explicar toda a mensagem."
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=1800,
            system=_capture_hooks_system(
                payload.durationSeconds, payload.editorialTone, payload.outro
            ),
            output_config={"format": {"type": "json_schema", "schema": _CAPTURE_HOOKS_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = json.loads(raw_text)
    except anthropic.APIStatusError as exc:
        if payload.requireClaude:
            raise HTTPException(
                status_code=502,
                detail=f"Claude respondeu {exc.status_code}. Nenhum roteiro de captura foi salvo.",
            )
        return {
            "ok": True,
            "provider": "fallback",
            **_normalize_capture_hooks(payload, _capture_hooks_fallback(payload)),
        }
    except Exception as exc:
        if payload.requireClaude:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao gerar capturas com Claude: {exc}. Nenhum dado foi salvo.",
            )
        return {
            "ok": True,
            "provider": "fallback",
            **_normalize_capture_hooks(payload, _capture_hooks_fallback(payload)),
        }

    raw_variants = parsed.get("variants") if isinstance(parsed, dict) else None
    if payload.requireClaude and (
        not isinstance(raw_variants, list)
        or len(raw_variants) != 3
        or any(not isinstance(item, dict) or not str(item.get("spokenText") or "").strip() for item in raw_variants)
    ):
        raise HTTPException(
            status_code=502,
            detail="Claude não retornou exatamente três roteiros completos. Nenhum dado foi salvo.",
        )

    if payload.requireClaude:
        raw_capture_issues: list[str] = []
        for index, item in enumerate(raw_variants or []):
            raw_spoken_text = re.sub(r"\s+", " ", str(item.get("spokenText") or "")).strip()
            issues = _narration_quality_issues(
                raw_spoken_text, payload.durationSeconds, payload.outro
            )
            if payload.durationSeconds == 10 and (
                _strip_video_outros(raw_spoken_text) != raw_spoken_text
                or re.search(r"\b(?:acesse|confira|siga|me siga|veja no perfil)\b", raw_spoken_text, re.I)
            ):
                issues.append("Vídeo de 10s não pode ter encerramento ou CTA falado")
            if issues:
                raw_capture_issues.append(f"Teste {index + 1}: {'; '.join(dict.fromkeys(issues))}")
        if raw_capture_issues:
            raise HTTPException(
                status_code=502,
                detail="Os roteiros do Claude não passaram pela validação de fala: "
                + " | ".join(raw_capture_issues)
                + ". Nenhum dado foi salvo.",
            )

    normalized = _normalize_capture_hooks(payload, parsed)
    if payload.requireClaude:
        capture_issues: list[str] = []
        for item in normalized["variants"]:
            issues = _narration_quality_issues(
                item["spokenText"], payload.durationSeconds, payload.outro
            )
            if issues:
                capture_issues.append(f'Teste {item["variant"]}: {"; ".join(issues)}')
        if capture_issues:
            raise HTTPException(
                status_code=502,
                detail="Os roteiros do Claude não passaram pela validação de fala: "
                + " | ".join(capture_issues)
                + ". Nenhum dado foi salvo.",
            )

    response = {
        "ok": True,
        "provider": "claude",
        **normalized,
    }
    _record_anthropic_usage("trends.capture_hooks", model, message)
    _ai_cache_put("trends.capture_hooks", cache_payload, response)
    return response


@app.post("/api/articles/analyze")
def analyze_article_for_ideas(payload: ArticleIdeasIn) -> dict:
    """Analisa artigo cientifico e devolve contexto + ideias prontas para roteiro."""
    source_article = _article_source_text(payload.article)
    if len(source_article) < 120:
        source_article = _fetch_article_context(payload.sourceUrl)
    if len(source_article) < 120:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível ler texto suficiente desse link. Cole o abstract ou o texto do artigo para continuar.",
        )
    clean_payload = payload.model_copy(update={"article": source_article})
    if not os.getenv("ANTHROPIC_API_KEY"):
        result = _manual_article_analysis(clean_payload)
        return {"ok": True, "provider": "fallback", **result}

    # Versão entra na chave para impedir que respostas antigas (inclusive o
    # fallback histórico de GLP-1/câncer) reapareçam para uma fonte diferente.
    cache_payload = {"analyzerVersion": "source-grounded-v2", **clean_payload.model_dump()}
    cached = _ai_cache_get("articles.analyze", cache_payload)
    if cached:
        return cached

    import anthropic

    prompt = (
        f"ARTIGO OU RESUMO:\n{_article_compact_text(clean_payload.article)}\n\n"
        f"Link/DOI informado: {payload.sourceUrl or 'nao informado'}\n"
        f"Quantidade de ideias: {payload.quantity}\n"
        f"Familia editorial sugerida: {payload.familia}\n"
        f"Prioridade sugerida: {payload.prioridade}\n\n"
        "Analise o estudo e gere ideias prontas para roteiro em portugues brasileiro."
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=2600,
            system=_ARTICLE_ANALYSIS_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _ARTICLE_ANALYSIS_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = json.loads(raw_text)
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        ideas = _normalize_expanded_ideas(
            ExpandIdeasIn(
                seed=clean_payload.article[:10000],
                quantity=payload.quantity,
                familia=payload.familia,
                prioridade=payload.prioridade,
            ),
            parsed.get("ideas"),
        )
    except anthropic.APIStatusError:
        result = _manual_article_analysis(clean_payload)
        return {"ok": True, "provider": "fallback", **result}
    except Exception:
        result = _manual_article_analysis(clean_payload)
        return {"ok": True, "provider": "fallback", **result}

    for idea in ideas:
        idea["linkOrigem"] = payload.sourceUrl
    response = {"ok": True, "provider": "claude", "analysis": analysis, "ideas": ideas}
    _record_anthropic_usage("articles.analyze", model, message)
    _ai_cache_put("articles.analyze", cache_payload, response)
    return response


def _append(tab: str, row: list) -> None:
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    try:
        client = GoogleSheetsRestClient()
        _ensure_tab_ids(client, tab)
        if tab == "ideias":
            _ensure_idea_headers(client)
        elif tab == "roteiros":
            _ensure_script_headers(client)
        client.append_rows(TAB_RANGE[tab], [row])
    except Exception as exc:  # credenciais / rede
        raise HTTPException(status_code=503, detail=f"falha ao gravar no Sheets: {exc}")


@app.post("/api/sheets/radar")
def append_trend(payload: TrendIn) -> dict:
    """Grava uma tendencia cadastrada manualmente na aba 'Radar Tendencias'."""
    item_id = payload.id or f"t-{uuid.uuid4().hex[:12]}"
    row = [
        _radar_date(payload.criadoEm),                    # Data
        payload.potencial,                                # Potencial Viral
        payload.titulo,                                   # Tema
        payload.subtema or "",                             # Subtema
        payload.fonte,                                     # Fonte
        payload.link or "",                                # Link referência
        payload.sinal or "",                               # Sinal de tendência
        payload.dorPublico or "",                          # Dor do público
        _PRIORIDADE.get(payload.prioridade, "Média"),      # Prioridade
        STATUS_LABELS["radar"].get(payload.status, "Pendente"),  # Status
        payload.notas or "",                               # Observações
        item_id,                                           # ID permanente
    ]
    _append("radar", row)
    raw = dict(zip(RADAR_HEADERS, row))
    _append_snapshot_row("radar", raw)
    return {"ok": True, "trend": map_trends([raw])[0]}


@app.post("/api/sheets/ideias")
def append_idea(payload: IdeaIn) -> dict:
    """Grava uma nova ideia na aba 'Ideias' (colunas reais)."""
    item_id = payload.id or f"i-{uuid.uuid4().hex[:12]}"
    existing = next(
        (
            row
            for index, row in enumerate(_load_snapshot().get("sheets", {}).get("ideias", []))
            if _row_id(row, "i", index) == item_id
        ),
        None,
    )
    if existing:
        return {"ok": True, "idea": map_ideas([existing])[0], "deduplicated": True}
    row = [
        payload.titulo,                       # Tema
        payload.hook,                         # Hook
        payload.angulo,                       # Ângulo
        payload.tipo or "",                   # Tipo
        payload.publicoDor or "",             # Público/Dor
        payload.cta,                          # CTA
        _PRIORIDADE.get(payload.prioridade, "Média"),   # Prioridade
        _IDEIA_STATUS.get(payload.status, "Nova"),      # Status
        payload.linkOrigem or "",             # Link origem
        payload.observacaoCompliance,         # Observações
        item_id,                              # ID permanente
        payload.trendId or "",                # Trend ID
        payload.criadoEm or _now(),           # Criado em
    ]
    _append("ideias", row)
    raw = dict(zip(IDEA_HEADERS, row))
    _append_snapshot_row("ideias", raw)
    return {"ok": True, "idea": map_ideas([raw])[0]}


@app.put("/api/sheets/ideias/{item_id}")
def update_idea(item_id: str, payload: IdeaIn) -> dict:
    """Atualiza uma ideia completa, inclusive o contexto recuperado da fonte."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    item_id = payload.id or item_id
    row = [
        payload.titulo,
        payload.hook,
        payload.angulo,
        payload.tipo or "",
        payload.publicoDor or "",
        payload.cta,
        _PRIORIDADE.get(payload.prioridade, "Média"),
        _IDEIA_STATUS.get(payload.status, "Nova"),
        payload.linkOrigem or "",
        payload.observacaoCompliance,
        item_id,
        payload.trendId or "",
        payload.criadoEm or _now(),
    ]
    try:
        client = GoogleSheetsRestClient()
        _ensure_tab_ids(client, "ideias")
        values = client.get_values(TAB_RANGE["ideias"])
        rownum = _sheet_row_number(values, item_id, "i")
        client.update_values(f"'Ideias'!A{rownum}:M{rownum}", [row])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao atualizar ideia: {exc}")
    raw = dict(zip(IDEA_HEADERS, row))
    _update_snapshot_row("ideias", item_id, raw)
    return {"ok": True, "idea": map_ideas([raw])[0]}


@app.post("/api/sheets/roteiros")
def append_script(payload: ScriptIn) -> dict:
    """Grava um novo roteiro e garante automaticamente as colunas do fluxo com IA."""
    item_id = payload.id or f"s-{uuid.uuid4().hex[:12]}"
    existing = next(
        (
            row
            for index, row in enumerate(_load_snapshot().get("sheets", {}).get("roteiros", []))
            if _row_id(row, "s", index) == item_id
        ),
        None,
    )
    if existing:
        return {"ok": True, "script": map_scripts([existing])[0], "deduplicated": True}
    row = [
        _FAMILIA.get(payload.categoria, "Educativo"),   # Categoria
        payload.tema,                         # Tema
        payload.titulo,                       # Título
        payload.hook,                         # Hook
        payload.dorConflito,                  # Dor/Conflito
        payload.explicacaoSimples,            # Explicação simples
        payload.virada,                       # Virada/Provocação
        payload.cta,                          # CTA
        payload.cuidadosMedicos,              # Cuidados médicos
        _RISCO.get(payload.risco, "Médio"),   # Risco
        payload.formatoSugerido,              # Formato sugerido
        _ROTEIRO_STATUS.get(payload.status, "Rascunho"),  # Status
        payload.aprovador or "",              # Aprovador
        payload.validadoEm or "",             # Data aprovação
        payload.link or "",                   # Link doc/video
        item_id,                               # ID permanente
        payload.ideaId or "",                 # Idea ID
        payload.editorialTone or "",           # Tom editorial
        payload.textoFalado or "",             # Texto falado
        payload.outroText,                     # Frase final
        payload.generationProvider or "",      # Gerado por
        payload.generationFlowVersion or "",   # Versão do fluxo
    ]
    _append("roteiros", row)
    raw = dict(zip(SCRIPT_HEADERS, row))
    raw["Criado em"] = payload.criadoEm or _now()
    _append_snapshot_row("roteiros", raw)
    saved_script = map_scripts([raw])[0]
    _script_editor_state(item_id, saved_script)
    return {"ok": True, "script": saved_script}


@app.post("/api/sheets/calendario")
def append_calendar_post(payload: CalendarIn) -> dict:
    """Agenda uma publicacao no Sheets e atualiza imediatamente o snapshot."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    item_id = payload.id or f"p-{uuid.uuid4().hex[:12]}"
    row = _calendar_row(payload, item_id)
    try:
        client = GoogleSheetsRestClient()
        _ensure_calendar_headers(client)
        client.append_rows(TAB_RANGE["calendario"], [row])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao agendar no Sheets: {exc}")
    raw = dict(zip(CALENDAR_HEADERS, row))
    _append_snapshot_row("calendario", raw)
    return {"ok": True, "post": map_calendar([raw])[0]}


@app.put("/api/sheets/calendario/{item_id}")
def update_calendar_post(item_id: str, payload: CalendarIn) -> dict:
    """Reagenda ou publica um item existente, persistindo a linha completa."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    item_id = payload.id or item_id
    row = _calendar_row(payload, item_id)
    try:
        client = GoogleSheetsRestClient()
        _ensure_calendar_headers(client)
        values = client.get_values(TAB_RANGE["calendario"])
        rownum = _sheet_row_number(values, item_id, "p")
        client.update_values(f"'Calendario'!A{rownum}:N{rownum}", [row])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao atualizar calendario: {exc}")
    raw = dict(zip(CALENDAR_HEADERS, row))
    _update_snapshot_row("calendario", item_id, raw)
    return {"ok": True, "post": map_calendar([raw])[0]}


@app.put("/api/sheets/roteiros/{item_id}")
def update_script(item_id: str, payload: ScriptIn) -> dict:
    """Atualiza o roteiro completo no Sheets e no snapshot usado pela producao."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    item_id = payload.id or item_id
    with _paid_generation_lock(item_id):
        row = [
            _FAMILIA.get(payload.categoria, "Educativo"), payload.tema, payload.titulo,
            payload.hook, payload.dorConflito, payload.explicacaoSimples, payload.virada,
            payload.cta, payload.cuidadosMedicos, _RISCO.get(payload.risco, "Médio"),
            payload.formatoSugerido, _ROTEIRO_STATUS.get(payload.status, "Rascunho"),
            payload.aprovador or "", payload.validadoEm or "", payload.link or "", item_id,
            payload.ideaId or "",
            payload.editorialTone or "", payload.textoFalado or "",
            payload.outroText,
            payload.generationProvider or "",
            payload.generationFlowVersion or "",
        ]
        try:
            client = GoogleSheetsRestClient()
            _ensure_tab_ids(client, "roteiros")
            _ensure_script_headers(client)
            values = client.get_values(TAB_RANGE["roteiros"])
            rownum = _sheet_row_number(values, item_id, "s")
            client.update_values(f"'Roteiros'!A{rownum}:V{rownum}", [row])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"falha ao atualizar roteiro: {exc}")
        raw = dict(zip(SCRIPT_HEADERS, row))
        _update_snapshot_row("roteiros", item_id, raw)
        saved_script = map_scripts([raw])[0]
        _script_editor_state(item_id, saved_script)
    return {"ok": True, "script": saved_script}


def _delete_script_local_data(script_id: str) -> dict[str, Any]:
    deleted_rows = 0
    conn = _ai_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table in (
            "script_editor_states",
            "production_profiles",
            "scene_plans",
            "visual_plans",
            "video_slide_renders",
            "visual_packs",
        ):
            cursor = conn.execute(f"DELETE FROM {table} WHERE script_id = ?", (script_id,))
            deleted_rows += max(cursor.rowcount, 0)
        conn.commit()
    finally:
        conn.close()

    slide_directory = _video_slide_output_dir(script_id)
    slides_removed = False
    cleanup_warning: str | None = None
    if slide_directory.exists():
        try:
            resolved_root = VIDEO_SLIDE_OUTPUTS.resolve()
            resolved_target = slide_directory.resolve()
            if resolved_target.parent != resolved_root:
                raise RuntimeError("Diretorio de slides fora da raiz permitida.")
            shutil.rmtree(resolved_target)
            slides_removed = True
        except (OSError, RuntimeError) as exc:
            cleanup_warning = str(exc)
    return {
        "localRowsRemoved": deleted_rows,
        "slidesRemoved": slides_removed,
        "cleanupWarning": cleanup_warning,
    }


@app.delete("/api/sheets/roteiros/{item_id}")
def delete_script(item_id: str) -> dict:
    """Exclui um roteiro sem deixar referencias de producao ou agenda quebradas."""
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    script = _find_script(item_id)
    linked_jobs = [
        job
        for job in _load_video_jobs()
        if job.get("scriptId") == item_id and job.get("status") != "erro"
    ]
    if linked_jobs:
        raise HTTPException(
            status_code=409,
            detail="Este roteiro possui vídeo ou prévia de produção. Preserve o roteiro para manter o histórico do vídeo.",
        )

    snapshot = _load_snapshot()
    linked_posts = [
        post
        for post in map_calendar(snapshot.get("sheets", {}).get("calendario", []))
        if post.get("scriptId") == item_id
    ]
    if linked_posts:
        raise HTTPException(
            status_code=409,
            detail="Este roteiro está ligado ao Calendário. Remova ou altere o agendamento antes de excluir.",
        )

    try:
        client = GoogleSheetsRestClient()
        _ensure_tab_ids(client, "roteiros")
        _ensure_script_headers(client)
        values = client.get_values(TAB_RANGE["roteiros"])
        row_number = _sheet_row_number(values, item_id, "s")
        client.delete_row(TAB_TITLE["roteiros"], row_number)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao excluir roteiro do Sheets: {exc}") from exc

    _remove_snapshot_row("roteiros", item_id)
    cleanup = _delete_script_local_data(item_id)
    return {
        "ok": True,
        "id": item_id,
        "title": script.get("titulo") or "Roteiro",
        **cleanup,
    }


# --------------------------------------------------------------------------- #
# Geracao real do Pack de Conteudo com Claude (server-side)
# --------------------------------------------------------------------------- #
class PackIn(BaseModel):
    scriptId: str | None = Field(default=None, max_length=120)
    titulo: str
    tema: str = ""
    categoria: str = "educativo"
    hook: str = ""
    dorConflito: str = ""
    explicacaoSimples: str = ""
    virada: str = ""
    cta: str = ""
    cuidadosMedicos: str = ""
    formatoSugerido: str = "Reels"


class PackSlideLayoutIn(BaseModel):
    layout: str = Field(min_length=1, max_length=80)


class PackSlidePhotoIn(BaseModel):
    photoAssetId: str | None = Field(default=None, max_length=120)


def _pack_text(pack: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(pack)
    return "\n".join(values)


def _pack_compliance(pack: dict[str, Any]) -> dict[str, Any]:
    text = _norm(_pack_text(pack))
    issues: list[str] = []
    for term in DEFAULT_SETTINGS["palavrasProibidas"]:
        if _norm(term) in text:
            issues.append(f"Palavra ou promessa proibida: {term}")
    for rule in MEDICAL_COMPLIANCE_RULES:
        if re.search(rule["pattern"], text):
            issues.append(rule["titulo"])
    return {"ok": not issues, "blocked": bool(issues), "issues": list(dict.fromkeys(issues))}


_NARRATION_PLACEHOLDERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"hook educativo sugerido|revise antes de aprovar", re.I), "Hook ainda parece sugestao automatica"),
    (re.compile(r"\brascunho\b", re.I), "Texto ainda contem marcacao de rascunho"),
    (re.compile(r"angulo:\s*angulo|ângulo:\s*ângulo", re.I), "Angulo duplicado ou com label tecnico"),
    (re.compile(r"explicar o tema sem prescrever|virada educativa reforcando", re.I), "Trecho ainda esta escrito como instrucao interna"),
]


def _narration_quality_issues(
    text: str,
    duration_seconds: int,
    outro: str = MANDATORY_VIDEO_OUTRO,
) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    selected_outro = "" if duration_seconds == 10 else re.sub(r"\s+", " ", outro).strip()
    issues: list[str] = []
    for pattern, issue in _NARRATION_PLACEHOLDERS:
        if pattern.search(normalized):
            issues.append(issue)

    if selected_outro:
        outro_matches = re.findall(re.escape(selected_outro), normalized, flags=re.I)
        if len(outro_matches) != 1:
            issues.append("Encerramento padrao deve aparecer exatamente uma vez")
        elif not normalized.lower().endswith(selected_outro.lower()):
            issues.append("Encerramento escolhido precisa ser a ultima frase")

    assessment = duration_assessment(normalized, duration_seconds)
    if assessment.status == "blocking":
        issues.append(assessment.message)

    return list(dict.fromkeys(issues))


def _has_repeated_narrative_sentence(text: str) -> bool:
    """Detecta frases que repetem substancialmente a mesma informacao."""
    sentences = re.findall(r"[^.!?…]+[.!?…]*", text.lower())
    stop_words = {
        "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e", "em", "esse", "esta",
        "este", "é", "o", "os", "na", "nas", "no", "nos", "ou", "para", "por", "que", "se", "sua", "um",
        "uma", "mais", "menos", "muito", "tambem", "pode", "podem", "ser", "sao", "tem", "têm",
    }
    token_sets: list[set[str]] = []
    for sentence in sentences:
        tokens = {
            token
            for token in re.findall(r"[a-záàâãéêíóôõúç]{4,}", sentence)
            if token not in stop_words
        }
        if len(tokens) >= 4:
            token_sets.append(tokens)
    for index, current in enumerate(token_sets):
        for previous in token_sets[:index]:
            overlap = len(current & previous) / min(len(current), len(previous))
            if overlap >= 0.5:
                return True
    return False


def _video_agent_narration_quality_issues(text: str, duration_seconds: int) -> list[str]:
    """Valida apenas problemas próprios do modo; duração pertence ao gate central."""
    issues: list[str] = []
    if _has_repeated_narrative_sentence(text):
        issues.append("A fala repete a mesma informacao em mais de uma frase")
    return issues


def _validate_final_narration(
    script: dict[str, Any],
    narration_text: str | None,
    duration_seconds: int = 45,
    outro: str = MANDATORY_VIDEO_OUTRO,
    generation_mode: str = "direct",
) -> str:
    """Valida exatamente a fala que sera incorporada ao prompt pago do HeyGen."""
    text = narration_text.strip() if narration_text and narration_text.strip() else _script_text(script)
    if not text:
        raise HTTPException(status_code=422, detail="O texto falado esta vazio.")
    selected_outro = "" if duration_seconds == 10 else re.sub(r"\s+", " ", outro).strip()
    final_text = _strip_video_outros(text, outro) if duration_seconds == 10 else text
    if selected_outro and selected_outro.lower() not in final_text.lower():
        final_text = f"{final_text.rstrip()} {selected_outro}"
    quality_issues = [
        issue
        for issue in _narration_quality_issues(final_text, duration_seconds, selected_outro)
        if not issue.startswith("Texto muito curto")
    ]
    if quality_issues:
        reasons = "; ".join(quality_issues)
        raise HTTPException(
            status_code=422,
            detail=f"Texto falado bloqueado antes do HeyGen: {reasons}.",
        )
    return final_text


def _validate_production_compliance(text: str, *, field: str) -> None:
    """Blocks unsafe wording in every text channel that can reach HeyGen."""
    normalized = performance_display_text(text)
    compliance = _pack_compliance({"text": normalized})
    if compliance["blocked"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field} bloqueado antes do HeyGen: "
                f"{'; '.join(compliance['issues'])}."
            ),
        )


def _finalize_video_texts(payload: VideoCreateIn, script: dict[str, Any]) -> tuple[str, str]:
    source_display = payload.displayText or payload.narrationText
    final_display = performance_display_text(
        _validate_final_narration(
            script,
            source_display,
            payload.durationSeconds,
            payload.outroText,
            payload.generationMode,
        )
    )
    final_spoken = re.sub(
        r"\s+",
        " ",
        payload.spokenText.strip() if payload.spokenText and payload.spokenText.strip() else "",
    ) or prepare_script_for_heygen_voice(final_display, add_sentence_breaks=False)
    _validate_production_compliance(final_display, field="Texto exibido")
    _validate_production_compliance(final_spoken, field="Texto enviado a voz")
    return final_display, final_spoken


def _finalize_preview_texts(payload: VideoPreviewCreateIn) -> tuple[str, str]:
    final_display = performance_display_text(preview_text(payload.displayText))
    final_spoken = preview_text(payload.spokenText) if payload.spokenText else prepare_script_for_heygen_voice(
        final_display,
        add_sentence_breaks=False,
    )
    _validate_production_compliance(final_display, field="Texto exibido da previa")
    _validate_production_compliance(final_spoken, field="Texto enviado a voz da previa")
    return final_display, final_spoken


def _production_configuration_key(payload: VideoCreateIn, display_text: str, spoken_text: str) -> str:
    configuration = {
        "scriptId": payload.scriptId,
        "avatarId": payload.avatarId,
        "voiceId": payload.voiceId,
        "durationSeconds": payload.durationSeconds,
        "generationMode": payload.generationMode,
        "speechMode": payload.speechMode,
        "voiceMood": payload.voiceMood,
        "displayText": display_text,
        "spokenText": spoken_text,
        "cinematicPrompt": (
            _clean_cinematic_prompt(payload.cinematicPrompt)
            if payload.generationMode == "cinematic"
            else ""
        ),
        "ctaMode": payload.ctaMode,
        "outroText": payload.outroText,
        "captions": payload.captions,
        "orientation": payload.orientation,
        "styleId": payload.styleId,
        "brandKitId": payload.brandKitId,
        "videoAgentMode": payload.videoAgentMode,
    }
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"video:{payload.scriptId}:{digest[:32]}"


def _preview_configuration_key(payload: VideoPreviewCreateIn, display_text: str, spoken_text: str) -> str:
    configuration = {
        "scriptId": payload.scriptId,
        "avatarId": payload.avatarId,
        "voiceId": payload.voiceId,
        "orientation": payload.orientation,
        "speechMode": payload.speechMode,
        "voiceMood": payload.voiceMood,
        "displayText": display_text,
        "spokenText": spoken_text,
        "captions": payload.captions,
    }
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"preview:{payload.scriptId}:{digest[:32]}"


def _compose_video_agent_prompt(
    approved_script: str,
    cinematic_prompt: str | None,
    duration_seconds: int,
    voice_mood: str = "confident",
) -> tuple[str, str]:
    clean_script = approved_script.strip()
    if not clean_script:
        return "", "approved_text_plus_voice_direction"
    clean_direction = _clean_cinematic_prompt(cinematic_prompt)
    prompt_parts = [
        "The presenter must speak only the approved Portuguese script below.",
        (
            "VOICE DELIVERY (interpret as performance direction, never read aloud): "
            f"Speak in Brazilian Portuguese with a {voice_mood_direction(_clean_voice_mood(voice_mood))} delivery."
        ),
        (
            f"Keep the video around {duration_seconds} seconds. "
            "Do not add new medical claims, mockery, caricature, or sensational framing."
        ),
        f"APPROVED SCRIPT (Portuguese):\n{clean_script}",
    ]
    if clean_direction:
        prompt_parts.insert(
            2,
            (
                "Do not read, paraphrase, summarize, or mention the cinematic direction. "
                "Use it only for visual staging, camera movement, pacing, background action, and B-roll."
            ),
        )
        prompt_parts.append(
            f"CINEMATIC DIRECTION (interpret visually, do not read aloud):\n{clean_direction}"
        )
    prompt = "\n\n".join(prompt_parts)
    return (
        prompt,
        "approved_text_plus_voice_and_cinematic_direction"
        if clean_direction
        else "approved_text_plus_voice_direction",
    )


_PACK_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
    "required": ["title", "text"],
}

_PACK_FIELDS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **{
            name: {"type": "string"}
            for name in FIELD_NAMES
            if name not in {"item1", "item2", "item3", "photoId"}
        },
        "item1": _PACK_ITEM_SCHEMA,
        "item2": _PACK_ITEM_SCHEMA,
        "item3": _PACK_ITEM_SCHEMA,
        "photoId": {"type": "string", "enum": ["", *PHOTO_LIBRARY.keys()]},
    },
    "required": list(FIELD_NAMES),
}

_PACK_SLIDE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "layoutId": {"type": "string", "enum": list(PACK_LAYOUTS)},
        "variant": {
            "type": "string",
            "enum": ["dark", "deep", "light", "warm", "photo-left", "photo-right", "text-top", "text-bottom"],
        },
        "fields": _PACK_FIELDS_SCHEMA,
    },
    "required": ["layoutId", "variant", "fields"],
}

_PACK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schemaVersion": {"type": "string", "enum": [PACK_SCHEMA_VERSION]},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "slides": {"type": "array", "items": _PACK_SLIDE_SCHEMA},
    },
    "required": ["schemaVersion", "caption", "hashtags", "slides"],
}

_PACK_SYSTEM = """Voce e o editor de carrosseis do Instituto Guilherme Martins.
Sua unica tarefa e transformar um roteiro medico em um carrossel de 7 slides,
em portugues do Brasil, usando o schema estruturado fornecido.

IDENTIDADE:
- Use exclusivamente a identidade e o Avatar Set presentes no CONTEXTO COMPLETO.
- Nunca invente, troque ou escolha outro avatarId; a identidade é anexada pelo backend.
- Se houver Avatar Set, ele representa a mesma pessoa em posições diferentes; mantenha essa continuidade também nas fotos.

OBJETIVO DE COPY: leitura instantanea e entendimento na primeira passada.
- Uma unica ideia por slide.
- Headline curta, concreta e com no maximo 11 palavras.
- Frases ativas; prefira palavras comuns e verbos concretos.
- Explique termos medicos em linguagem cotidiana.
- Corte introducoes, adjetivos vazios, repeticoes e frases de efeito genericas.
- Nao repita a headline no body.
- Nao use emoji, markdown, rotulos como "Slide 1" ou texto sobre o design.
- A pessoa precisa captar a mensagem central de cada tela em ate 3 segundos.

COMPLIANCE:
- Nao prescreva medicamento, dose ou conduta individual.
- Nao prometa resultado e nao use alarmismo.
- Proibido: segredo, milagre, antes/depois, voce esta fazendo errado e julgamento sobre peso.
- Trate obesidade como condicao multifatorial.
- O CTA termina com disclaimer educativo e orienta avaliacao individual.
- Nunca invente numero, estatistica, mito ou comparacao. Sem fonte real, escolha outro layout.

COMPOSICAO:
- Exatamente 7 slides.
- Slide 1: hero_photo ou photo_overlay. Slide 7: cta_photo.
- Slides 2 a 6: escolha livre entre os 12 layouts conforme a funcao narrativa.
- Inclua obrigatoriamente um slide explainer entre os slides 3 e 5. Esse e o slide de contexto: mais explicativo, pode ter body maior e deve traduzir o contexto gerado pela IA para linguagem comum.
- Os layouts sao uma paleta visual, nao uma grade obrigatoria. Voce pode repetir um layout se isso deixar a mensagem mais clara.
- Use pelo menos 4 tipos de layout no total, para manter ritmo.
- Maximo 3 slides com foto; nunca dois full bleed seguidos.
- Maximo 2 fundos escuros consecutivos.
- Sequencia: gancho -> tensao -> contexto explicado -> evidencia/riscos -> ponto central -> aplicacao/autoridade -> CTA.
- photoId deve vir apenas da biblioteca enviada no pedido.
- Layout e texto devem obedecer aos limites descritos no pedido.
- Se a ideia nao couber com leitura confortavel em um layout, reescreva a copy ou escolha outro layout. Nunca deixe frase cortada, incompleta ou dependente de contexto oculto.
- Use do_dont somente para uma comparação prática real: cada item deve ter, à esquerda, algo a evitar e, à direita, a alternativa preferível. Nunca use esse layout para cronologia, mecanismos ou listas de consequências.
- Para mecanismo, sequência ou três consequências, use three_points.
- Em myth_fact, item1 precisa conter um mito especifico, curto e popular do roteiro; item2 precisa conter o fato correspondente, tambem curto. Se nao existir mito real e claro, nao use myth_fact.
- Em efeitos colaterais, riscos e sinais de alerta, prefira lista visual, pergunta, explicador ou grande afirmacao. Nao transforme lista de riscos em mito/fato.
- Voce nao gera HTML, CSS ou imagens."""


def _find_pack_avatar_asset(avatar_id: str) -> dict[str, Any]:
    """Resolve avatar HeyGen para um arquivo local; nunca persiste URL assinada."""
    _, private_looks, _from_cache = _private_avatar_library(allow_cache=False)
    for raw_look in private_looks:
        avatar = normalize_avatar_look(raw_look) if isinstance(raw_look, dict) else None
        if avatar and avatar.get("id") == avatar_id and avatar.get("status") == "completed":
            preview_url = str(avatar.get("previewImageUrl") or "")
            if not preview_url:
                raise HTTPException(
                    status_code=409,
                    detail="O avatar escolhido nao possui imagem de preview no catalogo HeyGen.",
                )
            return _cache_pack_avatar_asset(avatar, preview_url)
    raise HTTPException(status_code=400, detail="Avatar do roteiro nao encontrado no catalogo HeyGen.")


def _cache_pack_avatar_asset(avatar: dict[str, Any], preview_url: str) -> dict[str, Any]:
    parsed = urlparse(preview_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=502, detail="Preview do avatar HeyGen veio com URL invalida.")
    PACK_AVATAR_ASSETS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(preview_url.encode("utf-8")).hexdigest()[:16]
    extension = Path(parsed.path).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".jpg"
    asset_path = PACK_AVATAR_ASSETS / f"{_slug(str(avatar.get('id')))}-{digest}{extension}"
    if not asset_path.exists():
        try:
            response = requests.get(preview_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao baixar preview do avatar: {exc}") from exc
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type == "image/png" and asset_path.suffix != ".png":
            asset_path = asset_path.with_suffix(".png")
        elif content_type == "image/webp" and asset_path.suffix != ".webp":
            asset_path = asset_path.with_suffix(".webp")
        elif content_type in {"image/jpeg", "image/jpg"} and asset_path.suffix not in {".jpg", ".jpeg"}:
            asset_path = asset_path.with_suffix(".jpg")
        asset_path.write_bytes(response.content)
    return {
        "avatarId": avatar["id"],
        "avatarName": avatar.get("name") or "Avatar sem nome",
        "cachedAssetPath": str(asset_path.relative_to(ROOT)),
    }


def _pack_photo_assets() -> list[dict[str, Any]]:
    """Biblioteca aprovada, com IDs estaveis e metadados de enquadramento."""
    assets: list[dict[str, Any]] = []
    for photo_id, meta in PHOTO_LIBRARY.items():
        path = ROOT / str(meta["file"])
        if not path.is_file():
            continue
        assets.append(
            {
                "id": photo_id,
                "name": meta["name"],
                "description": meta["description"],
                "cachedAssetPath": meta["file"],
                "facePointX": meta["facePointX"],
                "facePointY": meta["facePointY"],
                "brightness": meta["brightness"],
                "url": f"/api/packs/photo-assets/{photo_id}",
            }
        )
    return assets


def _pack_photo_asset(asset_id: str) -> dict[str, Any]:
    asset = photo_asset(asset_id)
    if not asset or not (ROOT / str(asset["cachedAssetPath"])).is_file():
        raise HTTPException(status_code=404, detail="Foto do Pack nao encontrada.")
    return {**asset, "url": f"/api/packs/photo-assets/{asset_id}"}


def _pack_design_plan(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": pack.get("schemaVersion") or PACK_SCHEMA_VERSION,
        "carousel": [
            {
                "layoutId": slide.get("layoutId") or slide.get("layout"),
                "variant": slide.get("variant"),
                "photoId": (slide.get("fields") or {}).get("photoId"),
                "headline": slide_headline(slide),
            }
            for slide in pack.get("carousel", [])
            if isinstance(slide, dict)
        ],
    }


def _normalize_pack_design(pack: dict[str, Any]) -> dict[str, Any]:
    normalized = repair_pack_copy(pack)
    raw_carousel = pack_slides(normalized)
    carousel = [normalize_slide(slide, index) for index, slide in enumerate(raw_carousel) if isinstance(slide, dict)]
    normalized["schemaVersion"] = normalized.get("schemaVersion") or PACK_SCHEMA_VERSION
    normalized["designDirection"] = "institute_carousel_v1"
    normalized["carousel"] = carousel
    normalized["slides"] = carousel
    normalized["designPlan"] = _pack_design_plan(normalized)
    normalized.setdefault("hashtags", [])
    normalized.setdefault("stories", [])
    checklist = normalized.get("checklist")
    if isinstance(checklist, list):
        normalized["checklist"] = [
            re.sub(r"\b6\s+slides?\b", "7 slides", str(item), flags=re.IGNORECASE)
            for item in checklist
        ]
        if not any("context" in str(item).casefold() or "explic" in str(item).casefold() for item in normalized["checklist"]):
            normalized["checklist"].insert(1, "1 slide explicativo com contexto da IA")
    if carousel:
        first_fields = carousel[0]["fields"]
        normalized.setdefault(
            "staticPost",
            {
                "headline": first_fields.get("headline", ""),
                "subline": first_fields.get("subheadline", ""),
                "layout": "big_statement",
            },
        )
    else:
        normalized.setdefault("staticPost", {"headline": "", "subline": "", "layout": "big_statement"})
    normalized.setdefault(
        "checklist",
        [
            "7 slides em sequencia narrativa",
            "1 slide explicativo com contexto da IA",
            "12 layouts de marca disponiveis",
            "Copy curta e validada por campo",
            "PNG 1080 x 1350 pronto para Instagram",
        ],
    )
    return normalized


def _validate_pack_content_counts(pack: dict[str, Any]) -> None:
    errors = validate_pack_contract(pack)
    if errors:
        raise HTTPException(status_code=502, detail="; ".join(errors))


def _attach_pack_metadata(
    pack: dict[str, Any],
    *,
    script_id: str,
    avatar_asset: dict[str, Any] | None = None,
    pack_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = _normalize_pack_design(pack)
    enriched["sourceScriptId"] = script_id
    if avatar_asset:
        enriched["sourceAvatarId"] = avatar_asset.get("avatarId")
        enriched["avatarAsset"] = avatar_asset
    if pack_context:
        identity = pack_context.get("identity") if isinstance(pack_context.get("identity"), dict) else {}
        enriched["packContextVersion"] = PACK_CONTEXT_VERSION
        enriched["sourceIdentityKey"] = pack_context.get("identityKey")
        enriched["sourceAvatarSetId"] = identity.get("avatarSetId")
        enriched["sourcePrimaryAvatarId"] = identity.get("primaryAvatarId")
    enriched["designPlan"] = _pack_design_plan(enriched)
    return enriched


def _recent_pack_context(limit: int = 5) -> list[dict[str, Any]]:
    conn = _ai_db()
    try:
        rows = conn.execute(
            "SELECT pack_json FROM visual_packs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    context: list[dict[str, Any]] = []
    for row in rows:
        try:
            pack = json.loads(str(row["pack_json"]))
        except json.JSONDecodeError:
            continue
        carousel = pack_slides(pack) if isinstance(pack, dict) else []
        if not carousel:
            continue
        context.append(
            {
                "layouts": [
                    slide.get("layoutId") or slide.get("layout")
                    for slide in carousel
                    if isinstance(slide, dict) and (slide.get("layoutId") or slide.get("layout"))
                ],
                "headlines": [
                    slide_headline(slide)
                    for slide in carousel[:3]
                    if isinstance(slide, dict)
                ],
            }
        )
    return context


def _pack_generation_context(script_id: str, script: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = _production_profile(script_id)
    if not profile:
        raise HTTPException(status_code=409, detail="Salve o perfil de produção antes de gerar o Pack visual.")
    avatar_set = _get_avatar_set(str(profile.get("avatarSetId") or "")) if profile.get("avatarMode") == "set" else None
    design_system = {
        "version": PACK_SCHEMA_VERSION,
        "canvas": "1080x1350",
        "layouts": list(PACK_LAYOUTS),
        "photoLibrary": list(PHOTO_LIBRARY),
        "rules": [
            "Claude escolhe copy, narrativa, layout e photoId; o renderer controla HTML/CSS.",
            "Exatamente 7 slides; layouts sao sugestoes flexiveis e podem repetir quando fizer sentido.",
            "Um slide explainer no meio traduz o contexto da IA em linguagem simples.",
            "O Pack herda a identidade do Roteiro e não escolhe outro avatar.",
        ],
    }
    context = build_pack_context(
        script=script,
        profile=profile,
        avatar_set=avatar_set,
        design_system=design_system,
        compliance_rules=MEDICAL_COMPLIANCE_RULES,
    )
    identity = context.get("identity") if isinstance(context.get("identity"), dict) else {}
    if not identity.get("primaryAvatarId") or not profile.get("voiceId"):
        raise HTTPException(status_code=409, detail="Defina avatar principal e voz no perfil de produção.")
    return context, profile


@app.get("/api/packs/photo-assets")
def list_pack_photo_assets() -> dict:
    return {"ok": True, "assets": _pack_photo_assets()}


@app.get("/api/packs/photo-assets/{asset_id}")
def get_pack_photo_asset(asset_id: str) -> FileResponse:
    asset = _pack_photo_asset(asset_id)
    path = ROOT / asset["cachedAssetPath"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo da foto do Pack nao encontrado.")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.post("/api/packs/generate")
def generate_pack(payload: PackIn) -> dict:
    """Gera um carrossel de 7 slides com copy curta e layout deterministico."""
    script_id = payload.scriptId
    if not script_id:
        raise HTTPException(status_code=422, detail="Informe scriptId para gerar o Pack visual.")
    script = _find_script(script_id)
    pack_context, _profile = _pack_generation_context(script_id, script)
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Defina ANTHROPIC_API_KEY no arquivo .env para gerar com o Claude.",
        )
    recent_context = _recent_pack_context()
    cache_payload = {
        "request": payload.model_dump(),
        "context": pack_context,
        "identityKey": pack_context["identityKey"],
        "recentPackContext": recent_context,
        "schemaVersion": PACK_SCHEMA_VERSION,
        "slideCount": PACK_SLIDE_COUNT,
    }
    cached = _ai_cache_get("packs.generate", cache_payload)
    if cached:
        pack = cached.get("pack") if isinstance(cached, dict) else None
        if isinstance(pack, dict):
            avatar_asset = pack.get("avatarAsset") if isinstance(pack.get("avatarAsset"), dict) else None
            if not avatar_asset:
                avatar_asset = _find_pack_avatar_asset(str(pack_context["identity"]["primaryAvatarId"]))
            pack = _attach_pack_metadata(
                pack,
                script_id=script_id,
                avatar_asset=avatar_asset,
                pack_context=pack_context,
            )
            validation_errors = validate_pack_contract(pack)
            if validation_errors:
                pack = None
            else:
                _save_visual_pack(script_id, pack)
                cached["pack"] = pack
                return cached
        elif pack is None:
            pass
        else:
            pack = None
    import anthropic

    avatar_asset = _find_pack_avatar_asset(str(pack_context["identity"]["primaryAvatarId"]))
    diversity = json.dumps(recent_context, ensure_ascii=False, indent=2)
    photo_context = json.dumps(
        [
            {"id": photo_id, "description": meta["description"]}
            for photo_id, meta in PHOTO_LIBRARY.items()
        ],
        ensure_ascii=False,
        indent=2,
    )
    layout_context = json.dumps(
        {
            "layouts": list(PACK_LAYOUTS),
            "fallback": list(FALLBACK_LAYOUTS),
            "hardLimits": {
                "eyebrow": 22,
                "headline": "use o limite especifico do layout; nunca mais de 11 palavras",
                "body": "110 a 200 caracteres conforme o layout",
                "itemTitle": 24,
                "itemText": 90,
                "quote": 90,
                "cta": 22,
                "statistic": 6,
                "disclaimer": 90,
            },
            "editorialFreedom": [
                "Escolha o layout que melhor explica a mensagem, mesmo que diferente da sugestao inicial.",
                "Pode repetir layout se isso evitar corte de texto ou melhorar entendimento.",
                "Priorize uma frase forte por slide; detalhes ficam na legenda.",
                "Nao use myth_fact para listas de riscos ou efeitos colaterais.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    base_prompt = (
        "CONTEXTO COMPLETO DO ROTEIRO, PERFORMANCE, IDENTIDADE E COMPLIANCE:\n"
        f"{json.dumps(pack_context, ensure_ascii=False, indent=2)}\n\n"
        f"BIBLIOTECA DE FOTOS (use somente estes IDs):\n{photo_context}\n\n"
        f"VOCABULARIO E LIMITES:\n{layout_context}\n\n"
        f"ULTIMOS CARROSSEIS — evite repetir a mesma sequencia e os mesmos ganchos:\n{diversity}\n\n"
        "Entregue uma narrativa ultra eficiente. Cada tela deve ser entendida isoladamente e levar naturalmente a proxima. "
        "Use fields irrelevantes ao layout como string vazia ou item vazio."
    )

    def request_pack(client: Any, model: str, correction_errors: list[str] | None = None) -> tuple[Any, dict[str, Any]]:
        correction = ""
        if correction_errors:
            correction = (
                "\n\nA PRIMEIRA RESPOSTA FOI REJEITADA. Corrija todos os erros abaixo sem alterar o fato central:\n- "
                + "\n- ".join(correction_errors)
            )
        message = client.messages.create(
            model=model,
            max_tokens=1400,
            system=[
                {
                    "type": "text",
                    "text": _PACK_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _PACK_SCHEMA}},
            messages=[{"role": "user", "content": base_prompt + correction}],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Resposta do Claude nao veio em JSON valido.") from exc
        return message, parsed

    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_PACK_MODEL", "claude-haiku-4-5")
        message, pack = request_pack(client, model)
        _record_anthropic_usage("packs.generate", model, message)
        pack = repair_pack_copy(pack)
        validation_errors = validate_pack_contract(pack)
        if validation_errors:
            message, pack = request_pack(client, model, validation_errors)
            _record_anthropic_usage("packs.generate.repair", model, message)
            pack = repair_pack_copy(pack)
            validation_errors = validate_pack_contract(pack)
        if validation_errors:
            raise HTTPException(
                status_code=502,
                detail="Claude nao respeitou o contrato do carrossel apos uma correcao: "
                + "; ".join(validation_errors),
            )
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Claude respondeu {exc.status_code}: {exc.message}")
    except HTTPException:
        raise
    except Exception as exc:  # rede / credencial
        raise HTTPException(status_code=502, detail=f"Falha ao chamar o Claude: {exc}")

    pack = _attach_pack_metadata(
        pack,
        script_id=script_id,
        avatar_asset=avatar_asset,
        pack_context=pack_context,
    )
    _save_visual_pack(script_id, pack)
    response = {"ok": True, "pack": pack, "compliance": _pack_compliance(pack)}
    _ai_cache_put("packs.generate", cache_payload, response)
    return response


@app.get("/api/packs/{script_id}")
def get_pack(script_id: str) -> dict:
    script = _find_script(script_id)
    pack = _get_visual_pack(script_id)
    # Packs gerados antes das regras semânticas atuais continuam abrindo no
    # editor já corrigidos, sem uma nova chamada ao Claude.
    if pack:
        stored_pack = pack
        pack = _normalize_pack_design(pack)
        # Persiste migrações e reparos sem qualquer chamada ao Claude. O guard
        # mantém compatibilidade com fixtures/DBs antigos sem avatar de origem.
        if pack != stored_pack and pack.get("sourceAvatarId"):
            pack = _save_visual_pack(script_id, pack)
    profile = _production_profile(script_id)
    current_identity_key = None
    if profile:
        try:
            current_context, _ = _pack_generation_context(script_id, script)
            current_identity_key = current_context.get("identityKey")
        except HTTPException:
            current_identity_key = None
    pack_slide_count = 0
    if pack:
        raw_slides = pack_slides(pack)
        pack_slide_count = len(raw_slides)
    outdated_pack_schema = bool(
        pack
        and (
            pack.get("schemaVersion") != PACK_SCHEMA_VERSION
            or pack_slide_count != PACK_SLIDE_COUNT
        )
    )
    outdated = bool(
        pack
        and (
            outdated_pack_schema
            or
            (
                current_identity_key
                and pack.get("sourceIdentityKey")
                and pack.get("sourceIdentityKey") != current_identity_key
            )
        )
    )
    return {
        "ok": True,
        "pack": pack,
        "productionProfile": profile,
        "outdatedAvatar": outdated,
        "outdatedIdentity": outdated,
        "outdatedPackSchema": outdated_pack_schema,
        "requiredSlideCount": PACK_SLIDE_COUNT,
    }


@app.put("/api/packs/{script_id}/carousel/{slide_index}/layout")
def update_pack_carousel_layout(
    script_id: str,
    slide_index: int,
    payload: PackSlideLayoutIn,
) -> dict:
    """Atualiza somente o layout fechado escolhido pelo usuario para um slide."""
    _find_script(script_id)
    if payload.layout not in PACK_LAYOUTS:
        raise HTTPException(status_code=422, detail="Layout de slide invalido.")
    pack = _get_visual_pack(script_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack visual nao encontrado para este roteiro.")
    carousel = pack.get("carousel")
    if not isinstance(carousel, list) or not 0 <= slide_index < len(carousel):
        raise HTTPException(status_code=404, detail="Slide do carrossel nao encontrado.")
    slide = carousel[slide_index]
    if not isinstance(slide, dict):
        raise HTTPException(status_code=422, detail="Slide do carrossel invalido.")

    slide["layoutId"] = payload.layout
    slide["layout"] = payload.layout
    # Mantém o alias legado sincronizado para que uma leitura posterior não
    # recupere o layout anterior.
    pack["slides"] = carousel
    pack["designPlan"] = _pack_design_plan(pack)
    _save_visual_pack(script_id, pack)
    return {"ok": True, "pack": pack, "compliance": _pack_compliance(pack)}


@app.put("/api/packs/{script_id}/carousel/{slide_index}/photo")
def update_pack_carousel_photo(
    script_id: str,
    slide_index: int,
    payload: PackSlidePhotoIn,
) -> dict:
    """Associa uma foto local da biblioteca ao slide, sem alterar seu texto ou layout."""
    _find_script(script_id)
    pack = _get_visual_pack(script_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack visual nao encontrado para este roteiro.")
    carousel = pack.get("carousel")
    if not isinstance(carousel, list) or not 0 <= slide_index < len(carousel):
        raise HTTPException(status_code=404, detail="Slide do carrossel nao encontrado.")
    slide = carousel[slide_index]
    if not isinstance(slide, dict):
        raise HTTPException(status_code=422, detail="Slide do carrossel invalido.")

    if payload.photoAssetId:
        asset = _pack_photo_asset(payload.photoAssetId)
        slide["photoAsset"] = {
            "id": asset["id"],
            "name": asset["name"],
            "cachedAssetPath": asset["cachedAssetPath"],
            "facePointX": asset["facePointX"],
            "facePointY": asset["facePointY"],
            "brightness": asset["brightness"],
        }
        fields = dict(slide.get("fields") or empty_fields())
        fields["photoId"] = asset["id"]
        slide["fields"] = fields
    else:
        slide.pop("photoAsset", None)
        fields = dict(slide.get("fields") or empty_fields())
        fields["photoId"] = ""
        slide["fields"] = fields
    # ``carousel`` é a lista canônica editada pela interface; ``slides`` ainda
    # existe para compatibilidade com Packs antigos e precisa refletir a troca.
    pack["slides"] = carousel
    pack["designPlan"] = _pack_design_plan(pack)
    _save_visual_pack(script_id, pack)
    return {"ok": True, "pack": pack, "compliance": _pack_compliance(pack)}


@app.post("/api/packs/{script_id}/refresh-avatar")
def refresh_pack_avatar(script_id: str) -> dict:
    script = _find_script(script_id)
    pack = _get_visual_pack(script_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack visual nao encontrado para este roteiro.")
    pack_context, _profile = _pack_generation_context(script_id, script)
    current_key = pack_context.get("identityKey")
    if pack.get("sourceIdentityKey") == current_key:
        return {
            "ok": True,
            "pack": pack,
            "compliance": _pack_compliance(pack),
            "productionProfile": _profile,
            "outdatedAvatar": False,
            "outdatedIdentity": False,
        }
    avatar_asset = _find_pack_avatar_asset(str(pack_context["identity"]["primaryAvatarId"]))
    refreshed = _attach_pack_metadata(
        pack,
        script_id=script_id,
        avatar_asset=avatar_asset,
        pack_context=pack_context,
    )
    _save_visual_pack(script_id, refreshed)
    return {
        "ok": True,
        "pack": refreshed,
        "compliance": _pack_compliance(refreshed),
        "productionProfile": _profile,
        "outdatedAvatar": False,
        "outdatedIdentity": False,
    }


# --------------------------------------------------------------------------- #
# Exportacao do Pack para pasta local (carrossel, post, legenda, stories)
# --------------------------------------------------------------------------- #
PACKS_DIR = ROOT / "content" / "packs"


class PackSlide(BaseModel):
    layoutId: str | None = None
    variant: str = "light"
    fields: dict[str, Any] = Field(default_factory=empty_fields)
    # Campos legados mantidos para abrir Packs salvos antes do novo renderer.
    title: str = ""
    body: str = ""
    layout: str = "explainer"
    visualIntent: str = "educational"
    highlight: str = ""
    avatar: dict[str, Any] = {}
    background: str = "clinical_light"
    photoAsset: dict[str, Any] | None = None


class PackStaticPost(BaseModel):
    headline: str = ""
    subline: str = ""
    layout: str = "big_statement"
    visualIntent: str = "educational"
    avatar: dict[str, Any] = {}
    background: str = "clinical_light"
    photoAsset: dict[str, Any] | None = None


class PackBody(BaseModel):
    schemaVersion: str = PACK_SCHEMA_VERSION
    designDirection: str = "institute_carousel_v1"
    carousel: list[PackSlide] = Field(default_factory=list)
    slides: list[PackSlide] = Field(default_factory=list)
    staticPost: PackStaticPost = Field(default_factory=PackStaticPost)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    stories: list[PackSlide] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    sourceScriptId: str | None = None
    sourceAvatarId: str | None = None
    sourceAvatarSetId: str | None = None
    sourcePrimaryAvatarId: str | None = None
    sourceIdentityKey: str | None = None
    packContextVersion: str | None = None
    avatarAsset: dict[str, Any] | None = None
    designPlan: dict[str, Any] | None = None
    updatedAt: str | None = None


class PackExportIn(BaseModel):
    scriptId: str | None = None
    titulo: str
    tema: str = ""
    categoria: str = "educativo"
    risco: str = ""
    formatoSugerido: str = ""
    pack: PackBody


def _slug(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:60] or "pack"


def _limpar_export_antigo(folder: Path) -> None:
    """Remove apenas os artefatos que este export cria (nao mexe no resto)."""
    import shutil

    for nome in ("1-imagens", "2-textos", "carrossel", "stories"):
        alvo = folder / nome
        if alvo.is_dir():
            shutil.rmtree(alvo, ignore_errors=True)
    for nome in ("LEIA-ME.md", "PACK.md", "legenda.txt", "post-fixo.txt"):
        alvo = folder / nome
        if alvo.is_file():
            alvo.unlink()


@app.post("/api/packs/export")
def export_pack(payload: PackExportIn) -> dict:
    """
    Grava o pack em content/packs/<data>_<slug>/ organizado por uso:

        LEIA-ME.md      -> o que postar, em que ordem
        1-imagens/      -> PNGs prontos (carrossel/, stories/, post-fixo.png)
        2-textos/       -> legenda e textos para copiar
    """
    data = datetime.now().strftime("%Y-%m-%d")
    folder = PACKS_DIR / f"{data}_{_slug(payload.titulo)}"
    img_root = folder / "1-imagens"
    txt_root = folder / "2-textos"
    # Reaplica os reparos determinísticos antes de qualquer PNG ou texto ser
    # exportado; assim um Pack antigo não volta a sair com montagem inválida.
    pack = PackBody.model_validate(repair_pack_copy(payload.pack.model_dump()))
    pack_dump = pack.model_dump()
    carousel_rows = [normalize_slide(slide, index) for index, slide in enumerate(pack_dump.get("carousel") or pack_dump.get("slides") or [])]
    is_institute_pack = pack.schemaVersion == PACK_SCHEMA_VERSION
    if is_institute_pack:
        contract_errors = validate_pack_contract(
            {"slides": carousel_rows, "caption": pack.caption, "hashtags": pack.hashtags}
        )
        if contract_errors:
            raise HTTPException(status_code=422, detail="Pack bloqueado antes da exportacao: " + "; ".join(contract_errors))
    compliance = _pack_compliance(pack_dump)

    try:
        folder.mkdir(parents=True, exist_ok=True)
        _limpar_export_antigo(folder)
        img_root.mkdir(parents=True, exist_ok=True)
        txt_root.mkdir(parents=True, exist_ok=True)

        # --- 2-textos: um arquivo por peca, sem repeticao ---
        carrossel_txt = "\n\n".join(
            f"── SLIDE {i:02d} · {slide['layoutId']} ──\n{slide_headline(slide)}\n\n{slide['fields'].get('body') or slide['fields'].get('subheadline') or ''}"
            for i, slide in enumerate(carousel_rows, start=1)
        )
        (txt_root / "carrossel.txt").write_text(carrossel_txt + "\n", encoding="utf-8")
        hashtags = " ".join(tag if tag.startswith("#") else f"#{tag}" for tag in pack.hashtags)
        legenda = pack.caption.strip() + (f"\n\n{hashtags}" if hashtags else "")
        (txt_root / "legenda.txt").write_text(legenda + "\n", encoding="utf-8")
        if not is_institute_pack:
            stories_txt = "\n\n".join(
                f"── STORY {i:02d} · {s.title} ──\n{s.body}"
                for i, s in enumerate(pack.stories, start=1)
            )
            (txt_root / "stories.txt").write_text(stories_txt + "\n", encoding="utf-8")
            (txt_root / "post-fixo.txt").write_text(
                f"{pack.staticPost.headline}\n\n{pack.staticPost.subline}\n", encoding="utf-8"
            )
        (folder / "PACK.md").write_text(
            json.dumps(
                {
                    "sourceScriptId": pack.sourceScriptId or payload.scriptId,
                    "sourceAvatarId": pack.sourceAvatarId,
                    "sourceAvatarSetId": pack.sourceAvatarSetId,
                    "sourcePrimaryAvatarId": pack.sourcePrimaryAvatarId,
                    "sourceIdentityKey": pack.sourceIdentityKey,
                    "packContextVersion": pack.packContextVersion,
                    "avatarAsset": pack.avatarAsset,
                    "schemaVersion": pack.schemaVersion,
                    "designDirection": pack.designDirection,
                    "designPlan": pack.designPlan,
                    "compliance": compliance,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        textos = 3 if is_institute_pack else 5
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao salvar o pack: {exc}")

    # --- 1-imagens: PNGs prontos para postar ---
    imagens = 0
    aviso_imagens = ""
    try:
        from api.slides import render_pack_images

        resultado = render_pack_images(
            img_root,
            carousel_rows,
            [s.model_dump() for s in pack.stories],
            None if is_institute_pack else pack.staticPost.model_dump(),
            design_direction=pack.designDirection,
            avatar_asset=pack.avatarAsset,
            render_extras=not is_institute_pack,
        )
        imagens = int(resultado.get("images", 0))
    except Exception as exc:  # playwright ausente / falha de render
        aviso_imagens = f"Textos salvos, mas nao consegui gerar as imagens: {exc}"

    # --- LEIA-ME: guia de publicacao ---
    leiame = [
        f"# {payload.titulo}",
        "",
        f"Tema: {payload.tema} · Risco: {payload.risco} · Exportado em {data}",
        "",
        "> ⚠️ Conteúdo educativo. **Validar com o Dr. Guilherme antes de publicar.**",
        "",
        "## O que postar",
        "",
        f"**1. Carrossel** — `1-imagens/carrossel/` ({len(carousel_rows)} imagens, 1080×1350)",
        "   Suba na ordem (carrossel-01 → carrossel-%02d) e use a legenda abaixo."
        % len(carousel_rows),
        "",
        "**2. Legenda** — `2-textos/legenda.txt`",
        "   Copie e cole na publicação. As hashtags ficam no final.",
        "",
        f"**3. Vídeo** — gere na aba *Produção de vídeos* do app (formato: {payload.formatoSugerido}).",
        "",
        "## Pastas",
        "",
        "- `1-imagens/` → PNGs prontos para postar",
        "- `2-textos/` → textos para copiar e colar (ou editar no Canva)",
        "",
    ]
    if pack.checklist:
        leiame += ["## Checklist", ""] + [f"- [ ] {item}" for item in pack.checklist] + [""]
    try:
        (folder / "LEIA-ME.md").write_text("\n".join(leiame), encoding="utf-8")
    except OSError:
        pass

    return {
        "ok": True,
        "folder": str(folder),
        "relative": str(folder.relative_to(ROOT)),
        "files": textos + 1 + imagens,
        "images": imagens,
        "warning": aviso_imagens,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=True)
