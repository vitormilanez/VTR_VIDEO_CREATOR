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

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "sheets_snapshot.json"
VIDEO_JOBS = ROOT / "data" / "video_jobs.json"

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


def _load_video_jobs() -> list[dict[str, Any]]:
    if not VIDEO_JOBS.exists():
        return []
    try:
        data = json.loads(VIDEO_JOBS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save_video_jobs(jobs: list[dict[str, Any]]) -> None:
    VIDEO_JOBS.parent.mkdir(parents=True, exist_ok=True)
    temporary = VIDEO_JOBS.with_suffix(".tmp")
    temporary.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(VIDEO_JOBS)


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


def _video_prompt(script: dict[str, Any]) -> str:
    texto = _script_text(script)
    return "\n\n".join(
        [
            "Create a portrait educational video in Brazilian Portuguese for social media.",
            "The selected presenter explains one health topic with a clear, calm and non-prescriptive tone.",
            "Do not mention medication doses, promise outcomes, or make sensational claims.",
            "This script is a concept and theme to convey - not a verbatim transcript. You have full creative freedom to expand, elaborate, add examples, and fill the duration naturally. Do not pad with silence or pauses.",
            f"SCRIPT (Portuguese):\n{texto}",
            "Use minimal, clean styled visuals. Blue, black, and white as main colors. Leverage motion graphics as B-rolls and A-roll overlays. Include an intro sequence and an outro with a gentle call to action.",
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
                "criadoEm": _iso(None),
            }
        )
    return out


def map_scripts(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "id": _row_id(r, "s", i),
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
                "criadoEm": _iso(None),
                "validadoEm": _iso(r.get("Data aprovação")) if r.get("Data aprovação") else None,
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


DEFAULT_SETTINGS = {
    "temasPrioritarios": [
        "obesidade", "GLP-1", "Mounjaro", "Ozempic", "Wegovy",
        "dieta", "metabolismo", "comportamento alimentar",
    ],
    "palavrasProibidas": [
        "cura", "milagre", "garantido", "sem esforco",
        "resultado certo", "emagrece rapido", "prometo",
    ],
    # Integracoes reais existem no backend, mas so ligar quando testadas.
    "integracoes": {"heygen": False, "meta": False, "googleSheets": True},
}


HEYGEN_CATALOG = {
    "avatars": [
        {"id": "883356edef07402ab7be3c39920868ab", "name": "Dr Guilherme - Formal sorrindo", "orientation": "portrait"},
        {"id": "3836fbbca6994dae91f02b3e9926a62a", "name": "Dr Guilherme - Camisa branca close", "orientation": "portrait"},
        {"id": "68773738aa9b45ce9d619d743d1d77af", "name": "Dr Guilherme - Casual serio", "orientation": "portrait"},
        {"id": "2835cbcbdd65484c809bd0f6f80313e2", "name": "Confident gentleman in a smart outfit", "orientation": "portrait"},
        {"id": "a88d9b04f9964218b6889a7e10507edb", "name": "drguilhermeia smiling in the gym", "orientation": "landscape"},
        {"id": "1c00c73aad1d4decaa24407758fc5c35", "name": "drguilhermeia smiling in the gym (2)", "orientation": "landscape"},
        {"id": "587ea824d7764ef3b6acd618db89bc78", "name": "Photo Avatar", "orientation": "portrait"},
        {"id": "8d0f249218b648cbb8a5f2bc0c0fb1d3", "name": "Podcaster in a grey hoodie", "orientation": "landscape"},
        {"id": "69db99c0495f4dba9d08a267db636664", "name": "Grey Quarter-Zip Studio Host", "orientation": "landscape"},
        {"id": "5cf53de5717943669098c6b27199ec98", "name": "Man in black zip hoodie", "orientation": "landscape"},
        {"id": "2038b644953f4937afea78e3a7ccd8f8", "name": "Podcaster in blue hoodie", "orientation": "landscape"},
        {"id": "0e2646b2584640e4a56c01c72c85cec7", "name": "Man in olive green shirt", "orientation": "landscape"},
        {"id": "61e130873d2345a79a7d538147064154", "name": "drguilhermeia (digital twin)", "orientation": "landscape"},
    ],
    "voices": [
        {"id": "33a98f732fe144d9a40f5cf33a7e95ec", "name": "drguilhermeia", "gender": "male"},
        {"id": "2f31eb4f4d644a9b9f22cbdb63430cc0", "name": "Doutor Guilherme Intel Artificia", "gender": "unknown"},
        {"id": "47788d6e0a224eb9b2ee74fcc30fd1f8", "name": "Voice Clone", "gender": "male"},
        {"id": "a21ea127df6649ee9e333697761e0b29", "name": "voice-name-here", "gender": "male"},
        {"id": "a5dc4150b5a14c5393ee8c166f5028c8", "name": "voice-name-here (2)", "gender": "male"},
        {"id": "a816446b92424300a325f8940606aea2", "name": "4 - Bioplastia Glutea", "gender": "male"},
    ],
}


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "snapshot_exists": SNAPSHOT.exists()}


@app.get("/api/heygen/catalog")
def heygen_catalog() -> dict:
    """Catalogo de avatares e vozes privados disponiveis para producao."""
    return {
        **HEYGEN_CATALOG,
        "defaultAvatarId": os.getenv("HEYGEN_DEFAULT_AVATAR_ID"),
        "defaultVoiceId": os.getenv("HEYGEN_DEFAULT_VOICE_ID"),
    }


@app.get("/api/state")
def state() -> dict:
    """Payload unico que hidrata o store do frontend."""
    snap = _load_snapshot()
    sheets = snap.get("sheets", {})
    return {
        "trends": map_trends(sheets.get("radar", [])),
        "ideas": map_ideas(sheets.get("ideias", [])),
        "scripts": map_scripts(sheets.get("roteiros", [])),
        "videoJobs": _load_video_jobs(),
        "calendarPosts": map_calendar(sheets.get("calendario", [])),
        "performance": map_performance(sheets.get("performance", [])),
        "settings": DEFAULT_SETTINGS,
        "updatedAt": snap.get("updated_at"),
    }


# --------------------------------------------------------------------------- #
# HeyGen: envio e consulta somente por acao explicita do usuario
# --------------------------------------------------------------------------- #
class VideoCreateIn(BaseModel):
    scriptId: str
    avatarId: str | None = None
    voiceId: str | None = None


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

    return {
        "updatedAt": _now(),
        "providers": [heygen],
    }


@app.post("/api/videos")
def create_video(payload: VideoCreateIn) -> dict:
    """Cria um job real no HeyGen somente apos o clique de enviar para producao."""
    command = _heygen_cli()
    try:
        balance_before, currency_before = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_before, currency_before = None, None
    script = _find_script(payload.scriptId)
    avatar_id = payload.avatarId or os.getenv("HEYGEN_DEFAULT_AVATAR_ID")
    voice_id = payload.voiceId or os.getenv("HEYGEN_DEFAULT_VOICE_ID")
    if not avatar_id or not voice_id:
        raise HTTPException(
            status_code=503,
            detail="Configure HEYGEN_DEFAULT_AVATAR_ID e HEYGEN_DEFAULT_VOICE_ID no .env.",
        )

    args = [
        command,
        "video-agent",
        "create",
        "--prompt",
        _video_prompt(script),
        "--avatar-id",
        avatar_id,
        "--voice-id",
        voice_id,
        "--orientation",
        "portrait",
    ]
    try:
        proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="HeyGen demorou demais para aceitar o job.") from exc
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=(proc.stderr or proc.stdout or "Falha ao criar video no HeyGen.")[-500:])

    response = _read_json_output(proc)
    session_id = _find_value(response, "session_id", "sessionId")
    video_id = _find_value(response, "video_id", "videoId", "id")
    if not session_id:
        raise HTTPException(status_code=502, detail="HeyGen nao retornou o identificador da sessao.")

    now = _now()
    job = {
        "id": f"v-{uuid.uuid4().hex[:12]}",
        "scriptId": payload.scriptId,
        "status": "fila",
        "provider": "heygen",
        "progresso": 0,
        "criadoEm": now,
        "atualizadoEm": now,
        "remoteSessionId": session_id,
        "remoteVideoId": video_id or None,
    }
    try:
        balance_after, currency_after = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_after, currency_after = None, None
    if balance_before is not None and balance_after is not None and balance_after <= balance_before:
        job["costUsd"] = round(balance_before - balance_after, 2)
        job["currency"] = (currency_after or currency_before or "USD").upper()
    jobs = _load_video_jobs()
    jobs.insert(0, job)
    _save_video_jobs(jobs)
    return {"ok": True, "job": job}


@app.post("/api/videos/{job_id}/refresh")
def refresh_video(job_id: str) -> dict:
    """Consulta o HeyGen e atualiza um job local ja criado."""
    command = _heygen_cli()
    jobs = _load_video_jobs()
    job = next((item for item in jobs if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job de video nao encontrado.")
    session_id = job.get("remoteSessionId")
    if not session_id:
        raise HTTPException(status_code=500, detail="Job sem sessao HeyGen.")
    try:
        proc = subprocess.run(
            [command, "video-agent", "get", str(session_id)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="HeyGen demorou demais para responder.") from exc
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=(proc.stderr or proc.stdout or "Falha ao consultar video no HeyGen.")[-500:])

    response = _read_json_output(proc)
    status, progress = _job_status(response)
    job["status"] = status
    job["progresso"] = progress
    job["atualizadoEm"] = _now()
    job["remoteVideoId"] = _find_value(response, "video_id", "videoId") or job.get("remoteVideoId")
    job["videoUrl"] = _find_value(response, "video_url", "videoUrl", "video_page_url", "videoPageUrl") or job.get("videoUrl")
    job["thumbnailUrl"] = _find_value(response, "thumbnail_url", "thumbnailUrl") or job.get("thumbnailUrl")
    if job.get("remoteVideoId") and not job.get("videoUrl"):
        video_proc = subprocess.run(
            [command, "video", "get", str(job["remoteVideoId"])],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=45,
        )
        if video_proc.returncode == 0:
            video_details = _read_json_output(video_proc)
            job["videoUrl"] = _find_value(video_details, "video_url", "videoUrl") or job.get("videoUrl")
            job["thumbnailUrl"] = _find_value(video_details, "thumbnail_url", "thumbnailUrl") or job.get("thumbnailUrl")
    if status == "erro":
        job["erro"] = str(_find_value(response, "error", "message", "detail") or "HeyGen nao concluiu o video.")
    _save_video_jobs(jobs)
    return {"ok": True, "job": job}


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

    steps = [
        ("trend_hunter", [str(ROOT / "trend_hunter" / "trend_hunter.py")], 180),
        ("sync_sheets", [str(ROOT / "sync_trends_to_sheets.py"), "--limit", "20"], 120),
        ("refresh_snapshot", [str(ROOT / "sync_sheets_snapshot.py")], 120),
    ]
    log: list[str] = []
    for nome, args, timeout in steps:
        if not Path(args[0]).exists():
            raise HTTPException(status_code=404, detail=f"{nome}: script nao encontrado")
        try:
            proc = _run(args, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail=f"{nome}: tempo esgotado")
        log.append(f"[{nome}] rc={proc.returncode}\n{(proc.stdout or proc.stderr)[-400:]}")
        if proc.returncode != 0:
            # Passos 2/3 falham sem credenciais (.env / token OAuth do Sheets).
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Falha no passo '{nome}'. Verifique .env e .google_sheets_token.json "
                    f"na raiz do projeto.\n{(proc.stderr or proc.stdout)[-400:]}"
                ),
            )

    depois = len(map_trends(_load_snapshot().get("sheets", {}).get("radar", [])))
    return {"ok": True, "added": max(depois - antes, 0), "log": "\n\n".join(log)[-1500:]}


# --------------------------------------------------------------------------- #
# Escrita de status de volta no Google Sheets
# --------------------------------------------------------------------------- #
TAB_RANGE = {
    "radar": "'Radar Tendencias'!A:L",
    "ideias": "'Ideias'!A:K",
    "roteiros": "'Roteiros'!A:P",
    "calendario": "'Calendario'!A:K",
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


class IdeaIn(BaseModel):
    id: str | None = None
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


class ScriptIn(BaseModel):
    id: str | None = None
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
    link: str | None = None
    status: str = "aguardando_validacao"


def _append(tab: str, row: list) -> None:
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    try:
        client = GoogleSheetsRestClient()
        _ensure_tab_ids(client, tab)
        client.append_rows(TAB_RANGE[tab], [row])
    except Exception as exc:  # credenciais / rede
        raise HTTPException(status_code=503, detail=f"falha ao gravar no Sheets: {exc}")


@app.post("/api/sheets/ideias")
def append_idea(payload: IdeaIn) -> dict:
    """Grava uma nova ideia na aba 'Ideias' (colunas reais)."""
    item_id = payload.id or f"i-{uuid.uuid4().hex[:12]}"
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
    ]
    _append("ideias", row)
    raw = dict(zip(["Tema", "Hook", "Ângulo", "Tipo", "Público/Dor", "CTA", "Prioridade", "Status", "Link origem", "Observações", "ID"], row))
    _append_snapshot_row("ideias", raw)
    return {"ok": True, "idea": map_ideas([raw])[0]}


@app.post("/api/sheets/roteiros")
def append_script(payload: ScriptIn) -> dict:
    """Grava um novo roteiro na aba 'Roteiros' (colunas reais)."""
    item_id = payload.id or f"s-{uuid.uuid4().hex[:12]}"
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
    ]
    _append("roteiros", row)
    headers = ["Categoria", "Tema", "Título", "Hook", "Dor/Conflito", "Explicação simples", "Virada/Provocação", "CTA", "Cuidados médicos", "Risco", "Formato sugerido", "Status", "Aprovador", "Data aprovação", "Link doc/video", "ID"]
    raw = dict(zip(headers, row))
    _append_snapshot_row("roteiros", raw)
    return {"ok": True, "script": map_scripts([raw])[0]}


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
    ]
    try:
        client = GoogleSheetsRestClient()
        _ensure_tab_ids(client, "roteiros")
        values = client.get_values(TAB_RANGE["roteiros"])
        rownum = _sheet_row_number(values, item_id, "s")
        client.update_values(f"'Roteiros'!A{rownum}:P{rownum}", [row])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"falha ao atualizar roteiro: {exc}")
    headers = ["Categoria", "Tema", "Título", "Hook", "Dor/Conflito", "Explicação simples", "Virada/Provocação", "CTA", "Cuidados médicos", "Risco", "Formato sugerido", "Status", "Aprovador", "Data aprovação", "Link doc/video", "ID"]
    raw = dict(zip(headers, row))
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
    if re.search(r"\b\d+\s?(mg|mcg|ml|g)\b|\bdose\b|\bcomprimid|\bampola", text):
        issues.append("Possivel mencao de dose ou forma de administracao")
    if re.search(r"\b(prescreva|tome|use|aumente|reduza|pare|comece)\b", text):
        issues.append("Possivel linguagem prescritiva")
    return {"ok": not issues, "blocked": bool(issues), "issues": list(dict.fromkeys(issues))}


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
        message = client.messages.create(
            # Sonnet 5: bom custo/qualidade e suporta structured outputs.
            # Troque para claude-opus-4-8 via ANTHROPIC_MODEL se quiser o topo de linha.
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
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
    return {"ok": True, "pack": pack, "compliance": _pack_compliance(pack)}


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
