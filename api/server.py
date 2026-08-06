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
MANDATORY_VIDEO_OUTRO = "Me siga para mais dicas, e obrigado."

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
        """
    )
    return conn


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
    body = text
    for candidate in {
        selected_outro.strip(),
        MANDATORY_VIDEO_OUTRO,
        "Veja o contexto no perfil.",
    }:
        if candidate:
            body = re.sub(rf"\s*{re.escape(candidate)}\s*", " ", body, flags=re.I)
    return re.sub(r"[ \t]+", " ", body).strip()


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
    avatars = [
        {
            "id": look.get("id"),
            "name": look.get("name") or "Avatar sem nome",
            "orientation": (
                "landscape" if look.get("preferred_orientation") == "landscape" else "portrait"
            ),
            "groupId": look.get("group_id"),
            "groupName": look.get("group_name"),
            "previewImageUrl": look.get("preview_image_url"),
        }
        for look in looks
        if look.get("id") and look.get("status") == "completed"
    ]
    return {
        "avatars": avatars,
        "voices": HEYGEN_CATALOG["voices"],
        "defaultAvatarId": _heygen_default_avatar_id(avatars) if avatars else None,
        "defaultVoiceId": _heygen_default_voice_id(),
    }


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
    avatarId: str | None = None
    voiceId: str | None = None
    orientation: Literal["portrait", "landscape"] = "portrait"
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    speechMode: Literal["natural", "fiel", "direto"] = "natural"
    captions: bool = True
    optimizePronunciation: bool = True
    styleId: str | None = None
    forceNewVersion: bool = False
    narrationText: str | None = Field(default=None, max_length=6000)
    outroText: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)


SHORT_DIRECT_VIDEO_DURATIONS = frozenset({10, 15})
SHORT_VIDEO_VOICE_SPEEDS = {
    "fiel": 1.0,
    "natural": 1.03,
    "direto": 1.08,
}


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
) -> dict[str, Any]:
    """Monta um video curto deterministico, sem impor duracao artificial."""
    spoken_text = re.sub(r"\s+", " ", narration_text).strip()
    if optimize_pronunciation:
        spoken_text = prepare_script_for_heygen_voice(
            spoken_text,
            add_sentence_breaks=False,
        )
    speed = SHORT_VIDEO_VOICE_SPEEDS.get(speech_mode, SHORT_VIDEO_VOICE_SPEEDS["natural"])
    payload: dict[str, Any] = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "title": str(script.get("titulo") or "AI Video Creator - video curto"),
        "aspect_ratio": "9:16" if orientation == "portrait" else "16:9",
        "resolution": "720p",
        "output_format": "mp4",
        "script": spoken_text,
        "voice_id": voice_id,
        "voice_settings": {
            "speed": speed,
            "pitch": 0,
            "volume": 1,
            "locale": "pt-BR",
        },
    }
    if captions:
        payload["caption"] = {"file_format": "srt", "style": "default"}
    return payload


class NaturalizeScriptIn(BaseModel):
    text: str = Field(min_length=20, max_length=6000)
    medicalCautions: str = Field(default="", max_length=2000)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45
    outro: str = Field(default=MANDATORY_VIDEO_OUTRO, max_length=200)


_NATURAL_SCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

def _natural_script_system(duration_seconds: int, outro: str = MANDATORY_VIDEO_OUTRO) -> str:
    minimum_words, maximum_words = _duration_word_limits(duration_seconds)
    selected_outro = re.sub(r"\s+", " ", outro).strip() or MANDATORY_VIDEO_OUTRO
    ending_rule = (
        "- Para 10 segundos, entregue entre 18 e 24 palavras e termine no impacto, sem frase final ou CTA falado."
        if duration_seconds == 10
        else f'- Termine exatamente com: "{selected_outro}"'
    )
    return f"""Voce e um diretor de fala para videos curtos do Dr. Guilherme.
Transforme o texto em portugues brasileiro falado, espontaneo, humano e facil de entender.

Regras obrigatorias:
- Preserve exatamente o sentido, os fatos e os cuidados medicos do texto original.
- Nao acrescente diagnosticos, tratamentos, exemplos clinicos, doses ou promessas.
- Use frases curtas, contracoes naturais e transicoes discretas.
- Evite linguagem de artigo, listas, titulos, jargao e repeticoes.
- Nao use indicacoes de cena, parenteses, emojis ou marcacoes de pausa.
- Mantenha um tom acolhedor, seguro e profissional.
- O texto final completo deve ter entre {minimum_words} e {maximum_words} palavras. Conte todas as palavras, incluindo o encerramento.
- Respeite rigorosamente a duracao solicitada; corte explicacoes secundarias antes de responder.
{ending_rule}
- Responda somente no JSON solicitado."""


def _fit_ten_second_text(text: str) -> str:
    """Reduz uma fala a um hook coerente de 18–24 palavras, sem encerramento."""
    clean = _strip_video_outros(text)
    sentences = re.findall(r"[^.!?…]+[.!?…]*", clean)
    selected: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.strip().split()
        if not words:
            continue
        remaining = 24 - count
        if len(words) <= remaining:
            selected.append(sentence.strip())
            count += len(words)
            if count >= 18:
                break
        elif remaining > 0:
            selected.append(" ".join(words[:remaining]).rstrip(" ,:;") + "…")
            break
    result = " ".join(selected).strip()
    return result or " ".join(clean.split()[:24]).strip()


def _duration_word_limits(duration_seconds: int) -> tuple[int, int]:
    return {
        10: (18, 24),
        15: (25, 36),
        30: (55, 72),
        45: (85, 108),
        60: (115, 144),
    }.get(duration_seconds, (85, 108))


def _fit_text_to_duration(text: str, duration_seconds: int, outro: str) -> str:
    if duration_seconds == 10:
        return _fit_ten_second_text(text)
    selected_outro = re.sub(r"\s+", " ", outro).strip() or MANDATORY_VIDEO_OUTRO
    _minimum_words, maximum_words = _duration_word_limits(duration_seconds)
    outro_words = len(selected_outro.split())
    body_limit = max(1, maximum_words - outro_words)
    clean = _strip_video_outros(text, selected_outro)
    sentences = re.findall(r"[^.!?…]+[.!?…]*", clean)
    selected: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.strip().split()
        if not words:
            continue
        remaining = body_limit - count
        if remaining <= 0:
            break
        if len(words) <= remaining:
            selected.append(sentence.strip())
            count += len(words)
        else:
            selected.append(" ".join(words[:remaining]).rstrip(" ,:;") + "…")
            break
    body = " ".join(selected).strip() or " ".join(clean.split()[:body_limit]).strip()
    return f"{body.rstrip()} {selected_outro}".strip()


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
    cache_payload = {"promptVersion": "2026-08-03-v2-duration", **payload.model_dump()}
    cached = _ai_cache_get("scripts.naturalize", cache_payload)
    if cached:
        return cached
    import anthropic

    source = (
        f"DURACAO ALVO: {payload.durationSeconds} segundos\n"
        f"CUIDADOS MEDICOS: {payload.medicalCautions or 'Manter conteudo educativo.'}\n"
        f"TEXTO ORIGINAL:\n{payload.text}"
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=1200,
            system=_natural_script_system(payload.durationSeconds, payload.outro),
            output_config={"format": {"type": "json_schema", "schema": _NATURAL_SCRIPT_SCHEMA}},
            messages=[{"role": "user", "content": source}],
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
        natural_text = str(json.loads(raw_text)["text"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=502, detail="A IA nao retornou um texto valido.")

    natural_text = _fit_text_to_duration(
        natural_text,
        payload.durationSeconds,
        payload.outro,
    )
    response = {"ok": True, "text": natural_text}
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
    idempotency_key = payload.idempotencyKey or (
        f"video:{payload.scriptId}:initial"
        if not payload.forceNewVersion
        else f"video:{payload.scriptId}:version:{uuid.uuid4().hex}"
    )
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
            "orientation": payload.orientation,
            "durationSeconds": payload.durationSeconds,
            "speechMode": payload.speechMode,
            "captions": payload.captions,
            "optimizePronunciation": payload.optimizePronunciation,
            "styleId": payload.styleId,
            "narrationText": payload.narrationText,
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
        return _create_video_job(payload, reserved_job)
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


def _create_video_job(payload: VideoCreateIn, job: dict[str, Any]) -> dict:
    command = _heygen_cli()
    script = _find_script(payload.scriptId)
    if script.get("status") != "aprovado_clinicamente":
        raise HTTPException(
            status_code=409,
            detail="O roteiro precisa concluir a revisão de fala e estar marcado como Pronto antes do HeyGen.",
        )
    final_narration = _validate_final_narration(
        script,
        payload.narrationText,
        payload.durationSeconds,
        payload.outroText,
    )
    try:
        balance_before, currency_before = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_before, currency_before = None, None
    # allow_cache=False: este e o momento de gastar producao real na HeyGen, entao
    # o avatar escolhido precisa ser validado contra a lista ao vivo, nunca contra
    # um cache que pode estar desatualizado (avatar removido ou criado recentemente).
    _, private_looks, _from_cache = _private_avatar_library(command, allow_cache=False)
    ready_looks = [look for look in private_looks if look.get("status") == "completed"]
    avatar_id = payload.avatarId or _heygen_default_avatar_id(ready_looks)
    voice_id = payload.voiceId or _heygen_default_voice_id()
    allowed_avatar_ids = {look.get("id") for look in ready_looks}
    if avatar_id not in allowed_avatar_ids:
        raise HTTPException(status_code=400, detail="Selecione um avatar privado pronto.")

    job["productionSettings"]["avatarId"] = avatar_id
    job["productionSettings"]["voiceId"] = voice_id
    job["submissionState"] = "submitting"
    job["atualizadoEm"] = _now()
    _job_store().upsert("video", job)

    if payload.durationSeconds in SHORT_DIRECT_VIDEO_DURATIONS:
        generation_mode = "direct"
        voice_speed = SHORT_VIDEO_VOICE_SPEEDS.get(
            payload.speechMode,
            SHORT_VIDEO_VOICE_SPEEDS["natural"],
        )
        job["productionSettings"]["generationMode"] = generation_mode
        job["productionSettings"]["voiceSpeed"] = voice_speed
        _job_store().upsert("video", job)
        direct_payload = _direct_video_payload(
            script=script,
            narration_text=final_narration,
            avatar_id=avatar_id,
            voice_id=voice_id,
            orientation=payload.orientation,
            speech_mode=payload.speechMode,
            captions=payload.captions,
            optimize_pronunciation=payload.optimizePronunciation,
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
                narration_text=final_narration,
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
    selected_outro = "" if duration_seconds == 10 else re.sub(r"\s+", " ", outro).strip() or MANDATORY_VIDEO_OUTRO
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
    selected_outro = "" if duration_seconds == 10 else re.sub(r"\s+", " ", outro).strip() or MANDATORY_VIDEO_OUTRO
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


_PACK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "carousel": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
            },
        },
        "staticPost": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"headline": {"type": "string"}, "subline": {"type": "string"}},
            "required": ["headline", "subline"],
        },
        "caption": {"type": "string"},
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
            },
        },
        "checklist": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["carousel", "staticPost", "caption", "stories", "checklist"],
}

_PACK_SYSTEM = """Voce e um editor de conteudo medico do Dr. Guilherme, focado em \
obesidade, GLP-1, Mounjaro, Ozempic, metabolismo e comportamento alimentar, em \
portugues-BR.

Regras de compliance OBRIGATORIAS em TODAS as pecas:
- Nao prescrever medicamentos nem citar doses (mg, ml, comprimidos).
- Nao prometer resultado ("cura", "milagre", "garantido", "emagrece rapido").
- Nao fazer sensacionalismo medico.
- Reforcar avaliacao individual com profissional.
- Tratar obesidade como condicao multifatorial, com linguagem acolhedora.
- Conteudo educativo, nao prescritivo.

A partir do roteiro fornecido, gere um pacote de conteudo para redes sociais:
- carousel: 5 a 7 slides educativos (title curto + body 1-2 frases).
- staticPost: headline forte + subline (1 frase).
- caption: legenda pronta para Instagram/LinkedIn, com quebras de linha.
- stories: 3 a 5 telas curtas (title + body), incluindo uma com pergunta/enquete.
- checklist: 4 a 6 itens do que o pacote entrega.
Responda apenas no formato JSON pedido."""


@app.post("/api/packs/generate")
def generate_pack(payload: PackIn) -> dict:
    """Gera o pack de conteudo real via Claude a partir de um roteiro."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Defina ANTHROPIC_API_KEY no arquivo .env para gerar com o Claude.",
        )
    cache_payload = payload.model_dump()
    cached = _ai_cache_get("packs.generate", cache_payload)
    if cached:
        return cached
    import anthropic

    roteiro = (
        f"Titulo: {payload.titulo}\n"
        f"Tema: {payload.tema}\n"
        f"Categoria: {payload.categoria}\n"
        f"Hook: {payload.hook}\n"
        f"Dor/Conflito: {payload.dorConflito}\n"
        f"Explicacao simples: {payload.explicacaoSimples}\n"
        f"Virada/Provocacao: {payload.virada}\n"
        f"CTA: {payload.cta}\n"
        f"Cuidados medicos: {payload.cuidadosMedicos}\n"
        f"Formato do video: {payload.formatoSugerido}"
    )
    try:
        client = anthropic.Anthropic()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            system=_PACK_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _PACK_SCHEMA}},
            messages=[{"role": "user", "content": f"ROTEIRO:\n{roteiro}"}],
        )
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Claude respondeu {exc.status_code}: {exc.message}")
    except Exception as exc:  # rede / credencial
        raise HTTPException(status_code=502, detail=f"Falha ao chamar o Claude: {exc}")

    texto = "".join(getattr(b, "text", "") for b in message.content)
    try:
        pack = json.loads(texto)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Resposta do Claude nao veio em JSON valido.")
    response = {"ok": True, "pack": pack, "compliance": _pack_compliance(pack)}
    _record_anthropic_usage("packs.generate", model, message)
    _ai_cache_put("packs.generate", cache_payload, response)
    return response


# --------------------------------------------------------------------------- #
# Exportacao do Pack para pasta local (carrossel, post, legenda, stories)
# --------------------------------------------------------------------------- #
PACKS_DIR = ROOT / "content" / "packs"


class PackSlide(BaseModel):
    title: str = ""
    body: str = ""


class PackStaticPost(BaseModel):
    headline: str = ""
    subline: str = ""


class PackBody(BaseModel):
    carousel: list[PackSlide] = []
    staticPost: PackStaticPost = PackStaticPost()
    caption: str = ""
    stories: list[PackSlide] = []
    checklist: list[str] = []


class PackExportIn(BaseModel):
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

    try:
        folder.mkdir(parents=True, exist_ok=True)
        _limpar_export_antigo(folder)
        img_root.mkdir(parents=True, exist_ok=True)
        txt_root.mkdir(parents=True, exist_ok=True)

        # --- 2-textos: um arquivo por peca, sem repeticao ---
        carrossel_txt = "\n\n".join(
            f"── SLIDE {i:02d} ──\n{s.title}\n\n{s.body}"
            for i, s in enumerate(pack.carousel, start=1)
        )
        (txt_root / "carrossel.txt").write_text(carrossel_txt + "\n", encoding="utf-8")

        stories_txt = "\n\n".join(
            f"── STORY {i:02d} · {s.title} ──\n{s.body}"
            for i, s in enumerate(pack.stories, start=1)
        )
        (txt_root / "stories.txt").write_text(stories_txt + "\n", encoding="utf-8")

        (txt_root / "legenda.txt").write_text(pack.caption + "\n", encoding="utf-8")
        (txt_root / "post-fixo.txt").write_text(
            f"{pack.staticPost.headline}\n\n{pack.staticPost.subline}\n", encoding="utf-8"
        )
        textos = 4
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao salvar o pack: {exc}")

    # --- 1-imagens: PNGs prontos para postar ---
    imagens = 0
    aviso_imagens = ""
    try:
        from api.slides import render_pack_images

        carrossel = [s.model_dump() for s in pack.carousel]
        if carrossel:
            carrossel[0]["tema"] = payload.tema or payload.categoria
        resultado = render_pack_images(
            img_root,
            carrossel,
            [s.model_dump() for s in pack.stories],
            pack.staticPost.model_dump(),
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
        f"**1. Carrossel** — `1-imagens/carrossel/` ({len(pack.carousel)} imagens, 1080×1350)",
        "   Suba na ordem (carrossel-01 → carrossel-%02d) e use a legenda abaixo."
        % len(pack.carousel),
        "",
        "**2. Legenda** — `2-textos/legenda.txt`",
        "   Copie e cole na publicação. Já vem com hashtags.",
        "",
        f"**3. Stories** — `1-imagens/stories/` ({len(pack.stories)} imagens, 1080×1920)",
        "   Publique no dia seguinte apontando para o post.",
        "   Na tela de enquete, adicione o sticker de enquete do Instagram.",
        "",
        "**4. Post fixo (opcional)** — `1-imagens/post-fixo.png` (1080×1080)",
        "   Peça única, para reforçar a mensagem principal.",
        "",
        f"**5. Vídeo** — gere na aba *Produção de vídeos* do app (formato: {payload.formatoSugerido}).",
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
