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
import hashlib
import ipaddress
import json
import os
import re
import socket
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlparse

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
    photo_asset,
    slide_headline,
    validate_pack_contract,
)
from api.services.heygen_catalog import build_catalog, default_voice_id, normalize_avatar_look
from api.services.script_performance import (
    LEGACY_OUTRO,
    PERFORMANCE_SCHEMA,
    SPEECH_PRESETS,
    build_performance_prompt,
    display_text as performance_display_text,
    duration_word_limits,
    fit_ten_second_text,
    fit_text_to_duration,
    normalize_performance_response,
    preview_text,
    speech_speed,
    strip_known_outros,
)
from api.services.video_generation import (
    DIRECT_VIDEO_DURATIONS,
    direct_video_payload,
    normalize_caption_srt,
)
from api.services.scene_generation import build_scene_generation_result
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
CUT_OUTPUTS = ROOT / "data" / "cuts"
PACK_AVATAR_ASSETS = ROOT / "data" / "pack_assets" / "avatars"
PACK_PHOTO_ASSETS = ROOT / "data" / "pack_assets" / "photos"
VIDEO_SLIDE_OUTPUTS = ROOT / "data" / "video_slides"
MANDATORY_VIDEO_OUTRO = LEGACY_OUTRO

app = FastAPI(title="AI Video Creator API", version="0.1.0")

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


def _ai_db() -> sqlite3.Connection:
    """Abre o banco operacional usado para cache e medicao de chamadas de IA."""
    conn = sqlite3.connect(OPERATIONAL_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
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
        """
    )
    # Existing local databases predate Avatar Sets. Keep them usable without
    # requiring a destructive migration or touching the Google Sheets schema.
    for column, definition in (
        ("avatar_mode", "TEXT NOT NULL DEFAULT 'single'"),
        ("avatar_set_id", "TEXT"),
        ("primary_avatar_id", "TEXT"),
        ("position_count", "INTEGER NOT NULL DEFAULT 1"),
    ):
        try:
            conn.execute(f"ALTER TABLE production_profiles ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.commit()
    return conn


def _production_profile(script_id: str) -> dict[str, Any] | None:
    conn = _ai_db()
    try:
        row = conn.execute(
            """
            SELECT script_id, avatar_id, voice_id, speech_mode, generation_mode,
                   avatar_mode, avatar_set_id, primary_avatar_id, position_count, updated_at
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
        "updatedAt": _now(),
    }
    conn = _ai_db()
    try:
        conn.execute(
            """
            INSERT INTO production_profiles(
                script_id, avatar_id, voice_id, speech_mode, generation_mode,
                avatar_mode, avatar_set_id, primary_avatar_id, position_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                avatar_id = excluded.avatar_id,
                voice_id = excluded.voice_id,
                speech_mode = excluded.speech_mode,
                generation_mode = excluded.generation_mode,
                avatar_mode = excluded.avatar_mode,
                avatar_set_id = excluded.avatar_set_id,
                primary_avatar_id = excluded.primary_avatar_id,
                position_count = excluded.position_count,
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


VIDEO_VISUAL_DESIGN_SYSTEM_VERSION = "video-vertical-v1"
VIDEO_VISUAL_TYPES = frozenset({"none", "full_slide", "overlay", "statistic", "comparison", "quote"})
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


def _heygen_cli() -> str:
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
    if not os.getenv("HEYGEN_API_KEY"):
        raise HTTPException(status_code=503, detail="Defina HEYGEN_API_KEY no arquivo .env.")
    return command


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
    catalog["generationModes"] = ["direct", "video_agent"]
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
    group_id = _find_value(avatar_response, "group_id")
    avatar_id = _find_value(avatar_response, "id")
    if not group_id:
        raise HTTPException(status_code=502, detail="HeyGen nao retornou a identidade do avatar.")

    voice_id = _find_value(avatar_response, "default_voice_id")
    if payload.cloneVoice and payload.voiceSource == "video" and not voice_id:
        avatar_details = _run_heygen_json(
            command,
            ["avatar", "get", str(group_id)],
            timeout=45,
        )
        voice_id = _find_value(avatar_details, "default_voice_id")

    if voice_audio:
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

    consent_response = _run_heygen_json(
        command,
        ["avatar", "consent", "create", str(group_id)],
        payload={},
        timeout=45,
    )
    consent_url = _find_value(consent_response, "url", "consent_url", "consentUrl")
    now = _now()
    job = {
        "id": f"a-{uuid.uuid4().hex[:12]}",
        "name": name,
        "creationType": payload.creationType,
        "status": "pending_consent",
        "groupId": group_id,
        "avatarId": avatar_id,
        "voiceId": voice_id,
        "consentUrl": consent_url,
        "createdAt": now,
        "updatedAt": now,
    }
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
    generationMode: Literal["direct", "video_agent"] = "direct"
    ctaMode: Literal["auto", "manual", "none", "visual"] = "manual"
    captions: bool = True
    optimizePronunciation: bool = True
    styleId: str | None = None
    forceNewVersion: bool = False
    narrationText: str | None = Field(default=None, max_length=6000)
    displayText: str | None = Field(default=None, max_length=6000)
    spokenText: str | None = Field(default=None, max_length=6000)
    outroText: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)


class VideoPreviewCreateIn(BaseModel):
    scriptId: str
    avatarId: str = Field(min_length=1, max_length=160)
    voiceId: str = Field(min_length=1, max_length=160)
    orientation: Literal["portrait", "landscape"] = "portrait"
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    generationMode: Literal["direct", "video_agent"] = "direct"
    captions: bool = True
    optimizePronunciation: bool = True
    displayText: str = Field(min_length=10, max_length=6000)
    spokenText: str | None = Field(default=None, max_length=6000)
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)


class ProductionProfileIn(BaseModel):
    avatarId: str = Field(min_length=1, max_length=160)
    voiceId: str = Field(min_length=1, max_length=160)
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural"
    generationMode: Literal["direct", "video_agent"] = "direct"
    avatarMode: Literal["single", "set"] = "single"
    avatarSetId: str | None = Field(default=None, max_length=160)
    primaryAvatarId: str | None = Field(default=None, max_length=160)


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


class VisualPlanSceneIn(BaseModel):
    sceneId: str = Field(min_length=1, max_length=80)
    visual: VisualPlanVisualIn


class VisualPlanIn(BaseModel):
    scenes: list[VisualPlanSceneIn] = Field(min_length=1, max_length=30)


SCENE_DIRECTOR_PROMPT_VERSION = "2026-08-07-v1-scene-director"
VISUAL_DIRECTOR_PROMPT_VERSION = "2026-08-07-v1-visual-director"
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
                        },
                        "required": ["type", "layout", "headline", "body", "purpose"],
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
        captions=captions,
        optimize_pronunciation=optimize_pronunciation,
        caption_source_matches_spoken=caption_source_matches_spoken,
    )


@app.get("/api/scripts/{script_id}/production-profile")
def get_script_production_profile(script_id: str) -> dict:
    """Intencao de producao escolhida na tela do roteiro, antes do job pago."""
    _find_script(script_id)
    return {"ok": True, "profile": _production_profile(script_id)}


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
            "generationMode": payload.generationMode,
            "avatarMode": payload.avatarMode,
            "avatarSetId": payload.avatarSetId,
            "primaryAvatarId": payload.primaryAvatarId,
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
    return {"ok": True, "scenePlan": _scene_plan(script_id)}


@app.put("/api/scripts/{script_id}/scene-plan")
def save_script_scene_plan(script_id: str, payload: ScenePlanIn) -> dict:
    _find_script(script_id)
    plan = _save_scene_plan(script_id, [scene.model_dump() for scene in payload.scenes])
    return {"ok": True, "scenePlan": plan}


@app.get("/api/scripts/{script_id}/scene-generation/plan")
def get_scene_generation_plan(
    script_id: str,
    speechMode: Literal["natural", "fiel", "direto", "enfatico"] = "natural",
    orientation: Literal["portrait", "landscape"] = "portrait",
) -> dict:
    """Expõe o contrato futuro por cena sem criar job ou chamar a HeyGen."""
    _find_script(script_id)
    scene_plan = _scene_plan(script_id)
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
            orientation=orientation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "generation": result.to_dict()}


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
    for index, scene in enumerate(scene_plan["scenes"]):
        visual = submitted.get(str(scene["id"]), {})
        visual_type = str(visual.get("type") or "none")
        if visual_type not in VIDEO_VISUAL_TYPES:
            raise HTTPException(status_code=422, detail=f"Tipo visual inválido na cena {index + 1}.")
        layout = str(visual.get("layout") or "")
        if visual_type != "none" and layout not in VIDEO_VISUAL_LAYOUTS:
            raise HTTPException(status_code=422, detail=f"Layout visual inválido na cena {index + 1}.")
        headline = re.sub(r"\s+", " ", str(visual.get("headline") or "")).strip()[:180]
        body = re.sub(r"\s+", " ", str(visual.get("body") or "")).strip()[:500]
        purpose = re.sub(r"\s+", " ", str(visual.get("purpose") or "")).strip()[:300]
        if visual_type == "none":
            layout = ""
            headline = ""
            body = ""
        else:
            _validate_production_compliance(headline, field=f"Headline visual da cena {index + 1}")
            _validate_production_compliance(body, field=f"Body visual da cena {index + 1}")
        visual_scenes.append(
            {
                "sceneId": scene["id"],
                "visual": {
                    "type": visual_type,
                    "layout": layout,
                    "headline": headline,
                    "body": body,
                    "purpose": purpose,
                },
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
        rendered = render_video_slides(_video_slide_output_dir(script_id), visual_plan)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível renderizar os previews locais: {exc}") from exc
    saved = _save_video_slide_render(script_id, rendered)
    return {"ok": True, "render": _video_slide_public_render(script_id, saved)}


@app.get("/api/scripts/{script_id}/video-slides/{filename}")
def get_video_slide_file(script_id: str, filename: str) -> FileResponse:
    _find_script(script_id)
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise HTTPException(status_code=404, detail="Preview não encontrado.")
    path = (_video_slide_output_dir(script_id) / filename).resolve()
    root = _video_slide_output_dir(script_id).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Preview não encontrado.")
    return FileResponse(path, media_type="image/png")


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
    design_system = {
        "version": VIDEO_VISUAL_DESIGN_SYSTEM_VERSION,
        "canvas": "1080x1920",
        "allowedTypes": sorted(VIDEO_VISUAL_TYPES),
        "allowedLayouts": sorted(VIDEO_VISUAL_LAYOUTS),
        "rules": [
            "headline de 3 a 8 palavras quando houver headline",
            "linguagem simples e complementar à fala",
            "não transcrever o roteiro",
            "não gerar HTML, CSS ou JavaScript",
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
- Use visual.type none quando o médico sozinho for mais forte.
- Quando usar visual, escolha somente tipos e layouts permitidos no DESIGN_SYSTEM.
- O visual deve complementar, não repetir ou transcrever, a fala.
- Headline ideal: 3–8 palavras. Evite parágrafos.
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
        visual_type = str(raw_visual.get("type") or "none")
        if visual_type not in VIDEO_VISUAL_TYPES:
            visual_type = "none"
        layout = str(raw_visual.get("layout") or "")
        if layout not in VIDEO_VISUAL_LAYOUTS:
            layout = ""
        headline = re.sub(r"\s+", " ", str(raw_visual.get("headline") or "")).strip()[:180]
        body = re.sub(r"\s+", " ", str(raw_visual.get("body") or "")).strip()[:500]
        purpose = re.sub(r"\s+", " ", str(raw_visual.get("purpose") or "")).strip()[:300]
        if visual_type == "none":
            layout = ""
            headline = ""
            body = ""
        else:
            _validate_production_compliance(headline, field=f"Headline visual da cena {index + 1}")
            _validate_production_compliance(body, field=f"Body visual da cena {index + 1}")
        visual_scenes.append(
            {
                "sceneId": scene["id"],
                "visual": {
                    "type": visual_type,
                    "layout": layout,
                    "headline": headline,
                    "body": body,
                    "purpose": purpose,
                },
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


class NaturalizeScriptIn(BaseModel):
    text: str = Field(min_length=20, max_length=6000)
    medicalCautions: str = Field(default="", max_length=2000)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    outro: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    ctaMode: Literal["auto", "manual", "none", "visual"] = "auto"
    manualCta: str = Field(default="", max_length=240)
    recentCtas: list[str] = Field(default_factory=list)


_NATURAL_SCRIPT_SCHEMA = PERFORMANCE_SCHEMA

def _natural_script_system(duration_seconds: int, outro: str = MANDATORY_VIDEO_OUTRO) -> str:
    prompt = build_performance_prompt(
        text="",
        medical_cautions="",
        duration_seconds=duration_seconds,
        cta_mode="manual",
        manual_cta=outro,
        recent_ctas=[],
    )
    return prompt.system


def _fit_ten_second_text(text: str) -> str:
    """Reduz uma fala a um hook coerente de 18–24 palavras, sem encerramento."""
    return fit_ten_second_text(text)


def _duration_word_limits(duration_seconds: int) -> tuple[int, int]:
    return duration_word_limits(duration_seconds)


def _fit_text_to_duration(text: str, duration_seconds: int, outro: str) -> str:
    return fit_text_to_duration(text, duration_seconds, outro)


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


SCRIPT_GENERATION_PROMPT_VERSION = "2026-08-05-v4-claude-flow-validated"


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

    raw_spoken_text = str(script.get("textoFalado") or "")
    script["textoFalado"] = _fit_text_to_duration(
        raw_spoken_text,
        payload.durationSeconds,
        payload.outro,
    )
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

    response = {"ok": True, "provider": "claude", "script": script}
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


@app.post("/api/videos")
def create_video(payload: VideoCreateIn) -> dict:
    """Cria um job real no HeyGen somente apos o clique de enviar para producao."""
    now = _now()
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
    script = _find_script(payload.scriptId)
    final_display_text, final_spoken_text = _finalize_video_texts(payload, script)
    idempotency_key = payload.idempotencyKey or _production_configuration_key(
        payload, final_display_text, final_spoken_text
    )
    if payload.forceNewVersion and not payload.idempotencyKey:
        idempotency_key = f"{idempotency_key}:version:{uuid.uuid4().hex}"
    reserved_job = {
        "id": f"v-{uuid.uuid4().hex[:12]}",
        "scriptId": payload.scriptId,
        "status": "fila",
        "provider": "heygen",
        "progresso": 0,
        "criadoEm": now,
        "atualizadoEm": now,
        "submissionState": "reserved",
        "productionSettings": {
            "avatarId": payload.avatarId,
            "voiceId": payload.voiceId,
            "orientation": payload.orientation,
            "durationSeconds": payload.durationSeconds,
            "speechMode": payload.speechMode,
            "generationMode": payload.generationMode,
            "ctaMode": payload.ctaMode,
            "captions": payload.captions,
            "optimizePronunciation": payload.optimizePronunciation,
            "styleId": payload.styleId,
            "narrationText": final_display_text,
            "displayText": final_display_text,
            "spokenText": final_spoken_text,
            "outroText": payload.outroText,
        },
    }
    job, reservation = _job_store().reserve_video(
        reserved_job,
        idempotency_key=idempotency_key,
        force_new_version=payload.forceNewVersion,
    )
    if reservation == "duplicate":
        if job.get("submissionState") in {"reserved", "submitting"}:
            raise HTTPException(
                status_code=409,
                detail="Este roteiro ja esta sendo enviado. Aguarde a criacao aparecer na producao.",
            )
        return {"ok": True, "job": job, "deduplicated": True}
    if reservation == "conflict":
        if job.get("submissionState") in {"reserved", "submitting", "submission_uncertain"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Ja existe um envio deste roteiro em andamento ou aguardando reconciliacao. "
                    "Nenhuma nova chamada foi feita ao HeyGen."
                ),
            )
        raise HTTPException(
            status_code=409,
            detail=(
                "Este roteiro ja possui um video. Abra a producao existente ou use "
                "'Criar nova versao' para gerar outro video."
            ),
        )
    try:
        return _create_video_job(payload, reserved_job, script=script, final_texts=(final_display_text, final_spoken_text))
    except HTTPException as exc:
        current = _job_store().get("video", reserved_job["id"]) or reserved_job
        current["status"] = "erro"
        current["progresso"] = 0
        current["erro"] = str(exc.detail)
        current["retrySafe"] = current.get("submissionState") != "submitting"
        current["submissionState"] = (
            "failed_safe" if current["retrySafe"] else "submission_uncertain"
        )
        current["atualizadoEm"] = _now()
        _job_store().upsert("video", current)
        raise


def _create_video_job(
    payload: VideoCreateIn,
    job: dict[str, Any],
    *,
    script: dict[str, Any] | None = None,
    final_texts: tuple[str, str] | None = None,
) -> dict:
    command = _heygen_cli()
    script = script or _find_script(payload.scriptId)
    if script.get("status") != "aprovado_clinicamente":
        raise HTTPException(
            status_code=409,
            detail="O roteiro precisa concluir a revisão de fala e estar marcado como Pronto antes do HeyGen.",
        )
    final_display_text, final_spoken_text = final_texts or _finalize_video_texts(payload, script)
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

    _save_production_profile(
        {
            "scriptId": payload.scriptId,
            "avatarId": avatar_id,
            "voiceId": voice_id,
            "speechMode": payload.speechMode,
            "generationMode": payload.generationMode,
        }
    )
    job["productionSettings"]["avatarId"] = avatar_id
    job["productionSettings"]["voiceId"] = voice_id
    job["productionSettings"]["displayText"] = final_display_text
    job["productionSettings"]["spokenText"] = final_spoken_text
    captions_need_normalization = payload.captions and final_display_text != final_spoken_text
    job["productionSettings"]["captionStrategy"] = (
        "sidecar_srt_normalized" if captions_need_normalization else "sidecar_srt"
    ) if payload.captions else "disabled"
    job["submissionState"] = "submitting"
    job["atualizadoEm"] = _now()
    _job_store().upsert("video", job)

    if payload.generationMode == "direct":
        generation_mode = "direct"
        voice_speed = speech_speed(payload.speechMode)
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
        generation_mode = "video_agent"
        job["productionSettings"]["generationMode"] = generation_mode
        job["productionSettings"]["voiceSpeed"] = speech_speed(payload.speechMode)
        _job_store().upsert("video", job)
        args = [
            "video-agent",
            "create",
            "--prompt",
            _video_prompt(
                script,
                duration_seconds=payload.durationSeconds,
                speech_mode=payload.speechMode,
                captions=payload.captions,
                optimize_pronunciation=payload.optimizePronunciation,
                narration_text=final_display_text,
                outro_text=payload.outroText,
            ),
            "--avatar-id",
            avatar_id,
            "--voice-id",
            voice_id,
            "--orientation",
            payload.orientation,
        ]
        if payload.styleId:
            args.extend(["--style-id", payload.styleId])
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
    preview_display_text, preview_spoken_text = _finalize_preview_texts(payload)
    idempotency_key = payload.idempotencyKey or _preview_configuration_key(
        payload, preview_display_text, preview_spoken_text
    )
    reserved_job = {
        "id": f"vp-{uuid.uuid4().hex[:12]}",
        "scriptId": payload.scriptId,
        "status": "fila",
        "provider": "heygen",
        "progresso": 0,
        "criadoEm": now,
        "atualizadoEm": now,
        "submissionState": "reserved",
        "isPreview": True,
        "productionSettings": {
            "avatarId": payload.avatarId,
            "voiceId": payload.voiceId,
            "orientation": payload.orientation,
            "durationSeconds": 10,
            "speechMode": payload.speechMode,
            "generationMode": "direct",
            "captions": payload.captions,
            "optimizePronunciation": payload.optimizePronunciation,
            "displayText": preview_display_text,
            "spokenText": preview_spoken_text,
        },
    }
    job, reservation = _job_store().reserve(
        "video",
        reserved_job,
        idempotency_key=idempotency_key,
    )
    if reservation == "duplicate":
        return {"ok": True, "job": job, "deduplicated": True}

    try:
        command = _heygen_cli()
        script = _find_script(payload.scriptId)
        if script.get("status") != "aprovado_clinicamente":
            raise HTTPException(
                status_code=409,
                detail="O roteiro precisa estar marcado como Pronto antes da prévia paga.",
            )
        _, private_looks, _from_cache = _private_avatar_library(command, allow_cache=False)
        ready_looks = [look for look in private_looks if look.get("status") == "completed"]
        allowed_avatar_ids = {look.get("id") for look in ready_looks}
        if payload.avatarId not in allowed_avatar_ids:
            raise HTTPException(status_code=400, detail="Selecione um avatar privado pronto.")
        _save_production_profile(
            {
                "scriptId": payload.scriptId,
                "avatarId": payload.avatarId,
                "voiceId": payload.voiceId,
                "speechMode": payload.speechMode,
                "generationMode": "direct",
            }
        )
        job["submissionState"] = "submitting"
        job["productionSettings"]["generationMode"] = "direct"
        job["productionSettings"]["voiceSpeed"] = speech_speed(payload.speechMode)
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
    except HTTPException as exc:
        current = _job_store().get("video", reserved_job["id"]) or reserved_job
        current["status"] = "erro"
        current["erro"] = str(exc.detail)
        current["retrySafe"] = current.get("submissionState") != "submitting"
        current["submissionState"] = "failed_safe" if current["retrySafe"] else "submission_uncertain"
        current["atualizadoEm"] = _now()
        _job_store().upsert("video", current)
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
    job["status"] = status
    job["progresso"] = progress
    job["atualizadoEm"] = _now()
    job["remoteVideoId"] = _find_value(response, "video_id", "videoId") or job.get("remoteVideoId")
    job["videoUrl"] = _find_value(response, "video_url", "videoUrl", "video_page_url", "videoPageUrl") or job.get("videoUrl")
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
    _job_store().upsert("video", job)
    return {"ok": True, "job": job}


@app.get("/api/videos/{job_id}/download")
def download_video(job_id: str) -> StreamingResponse:
    """Transmite o MP4 pronto do HeyGen como download com nome amigavel."""
    job = _job_store().get("video", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video nao encontrado.")
    video_url = str(job.get("videoUrl") or "")
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
        source_url = str((video_job or {}).get("videoUrl") or "")
        if not source_url:
            raise RuntimeError("O video produzido nao esta mais disponivel.")
    elif not youtube_url:
        raise RuntimeError("A origem deste projeto nao esta disponivel.")
    return source_url, youtube_url, source_path


@app.on_event("startup")
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
        source_url = str(video_job.get("videoUrl") or "")
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
    article: str = Field(min_length=120, max_length=50000)
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


def _manual_article_analysis(payload: ArticleIdeasIn) -> dict[str, Any]:
    text = _article_source_text(payload.article)
    lowered = text.lower()
    glp = bool(re.search(r"glp|semaglutide|semaglutida|tirzepatide|tirzepatida|mounjaro|ozempic", lowered))
    cancer = bool(re.search(r"cancer|câncer|tumou?r|oncolog|malignan|neoplasm", lowered))
    skin = bool(re.search(r"pele|flacidez|col[aá]geno|rosto|dermatolog|cut[aâ]ne|cicatriz|hidradenite|psor[ií]ase|queda de cabelo", lowered))
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


def _fetch_article_context(source_url: str | None) -> str:
    """Baixa somente texto útil da matéria, com limites de rede e de tokens."""
    if not source_url:
        return ""
    try:
        url = _validate_public_article_url(resolve_google_news_url(source_url))
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
    clean_payload = payload.model_copy(update={"article": source_article or payload.article})
    if not os.getenv("ANTHROPIC_API_KEY"):
        result = _manual_article_analysis(clean_payload)
        return {"ok": True, "provider": "fallback", **result}

    cache_payload = clean_payload.model_dump()
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
    return {"ok": True, "script": map_scripts([raw])[0]}


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
    return {"ok": True, "script": map_scripts([raw])[0]}


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

    word_count = len([word for word in re.split(r"\s+", normalized) if word])
    minimum_words, maximum_words = _duration_word_limits(duration_seconds)
    if word_count < minimum_words:
        issues.append(f"Texto muito curto para {duration_seconds}s")
    if word_count > maximum_words:
        issues.append(f"Texto muito longo para {duration_seconds}s ({word_count} palavras; maximo {maximum_words})")

    return list(dict.fromkeys(issues))


def _validate_final_narration(
    script: dict[str, Any],
    narration_text: str | None,
    duration_seconds: int = 45,
    outro: str = MANDATORY_VIDEO_OUTRO,
) -> str:
    """Valida exatamente a fala que sera incorporada ao prompt pago do HeyGen."""
    text = narration_text.strip() if narration_text and narration_text.strip() else _script_text(script)
    if not text:
        raise HTTPException(status_code=422, detail="O texto falado esta vazio.")
    selected_outro = "" if duration_seconds == 10 else re.sub(r"\s+", " ", outro).strip()
    final_text = _strip_video_outros(text, outro) if duration_seconds == 10 else text
    if selected_outro and selected_outro.lower() not in final_text.lower():
        final_text = f"{final_text.rstrip()} {selected_outro}"
    quality_issues = _narration_quality_issues(final_text, duration_seconds, selected_outro)
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
        "displayText": display_text,
        "spokenText": spoken_text,
        "ctaMode": payload.ctaMode,
        "outroText": payload.outroText,
        "captions": payload.captions,
        "orientation": payload.orientation,
        "styleId": payload.styleId,
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
        "displayText": display_text,
        "spokenText": spoken_text,
        "captions": payload.captions,
    }
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"preview:{payload.scriptId}:{digest[:32]}"


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
Sua unica tarefa e transformar um roteiro medico em um carrossel de 6 slides,
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
- Exatamente 6 slides, todos com layoutId diferente.
- Slide 1: hero_photo ou photo_overlay. Slide 6: cta_photo.
- Slides 2 a 5: escolha livre entre os 12 layouts conforme a funcao narrativa.
- Maximo 3 slides com foto; nunca dois full bleed seguidos.
- Maximo 2 fundos escuros consecutivos.
- Sequencia: gancho -> tensao -> explicacao/evidencia -> ponto central -> aplicacao/autoridade -> CTA.
- photoId deve vir apenas da biblioteca enviada no pedido.
- Layout e texto devem obedecer aos limites descritos no pedido.
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
    normalized = dict(pack)
    raw_carousel = normalized.get("carousel")
    if not isinstance(raw_carousel, list):
        raw_carousel = normalized.get("slides") if isinstance(normalized.get("slides"), list) else []
    carousel = [normalize_slide(slide, index) for index, slide in enumerate(raw_carousel) if isinstance(slide, dict)]
    normalized["schemaVersion"] = normalized.get("schemaVersion") or PACK_SCHEMA_VERSION
    normalized["designDirection"] = "institute_carousel_v1"
    normalized["carousel"] = carousel
    normalized["slides"] = carousel
    normalized.setdefault("hashtags", [])
    normalized.setdefault("stories", [])
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
            "6 slides em sequencia narrativa",
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
        carousel = pack.get("carousel") if isinstance(pack, dict) else None
        if not isinstance(carousel, list):
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
            "Exatamente 6 slides, sem layouts repetidos.",
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
    return FileResponse(path)


@app.post("/api/packs/generate")
def generate_pack(payload: PackIn) -> dict:
    """Gera um carrossel de 6 slides com copy curta e layout deterministico."""
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
            _save_visual_pack(script_id, pack)
            cached["pack"] = pack
        return cached
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
        validation_errors = validate_pack_contract(pack)
        if validation_errors:
            message, pack = request_pack(client, model, validation_errors)
            _record_anthropic_usage("packs.generate.repair", model, message)
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
    profile = _production_profile(script_id)
    current_identity_key = None
    if profile:
        try:
            current_context, _ = _pack_generation_context(script_id, script)
            current_identity_key = current_context.get("identityKey")
        except HTTPException:
            current_identity_key = None
    outdated = bool(
        pack
        and (
            (
                current_identity_key
                and pack.get("sourceIdentityKey")
                and pack.get("sourceIdentityKey") != current_identity_key
            )
            or (
                pack.get("schemaVersion") != PACK_SCHEMA_VERSION
                and profile
                and pack.get("sourceAvatarId")
                and profile.get("avatarId")
                and pack.get("sourceAvatarId") != profile.get("avatarId")
            )
        )
    )
    return {
        "ok": True,
        "pack": pack,
        "productionProfile": profile,
        "outdatedAvatar": outdated,
        "outdatedIdentity": outdated,
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
    pack = payload.pack
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
        "files": textos + 1,
        "images": imagens,
        "warning": aviso_imagens,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=True)
