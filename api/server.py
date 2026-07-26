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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from api.cut_service import process_cut_project
from api.job_store import JobStore
from integrations.portuguese_br import prepare_script_for_heygen_voice

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "sheets_snapshot.json"
VIDEO_JOBS = ROOT / "data" / "video_jobs.json"
AVATAR_JOBS = ROOT / "data" / "avatar_jobs.json"
APP_SETTINGS = ROOT / "data" / "app_settings.json"
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


def _video_prompt(
    script: dict[str, Any],
    *,
    duration_seconds: int = 45,
    speech_mode: str = "natural",
    captions: bool = True,
    optimize_pronunciation: bool = True,
    narration_text: str | None = None,
) -> str:
    texto = narration_text.strip() if narration_text and narration_text.strip() else _script_text(script)
    if optimize_pronunciation:
        texto = prepare_script_for_heygen_voice(texto)
    if MANDATORY_VIDEO_OUTRO.lower() not in texto.lower():
        texto = f"{texto.rstrip()}\n{MANDATORY_VIDEO_OUTRO}"

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
    return "\n\n".join(
        [
            "Create a portrait educational video in Brazilian Portuguese for social media.",
            "The selected presenter explains one health topic with a clear, calm and non-prescriptive tone.",
            "Do not mention medication doses, promise outcomes, or make sensational claims.",
            f"Target duration: approximately {duration_seconds} seconds. Do not pad with silence or pauses.",
            speech_directions.get(speech_mode, speech_directions["natural"]),
            (
                "Add clean, readable Brazilian Portuguese captions synchronized with the narration."
                if captions
                else "Do not add burned-in captions or subtitles."
            ),
            (
                "End the spoken narration exactly once with: "
                f'"{MANDATORY_VIDEO_OUTRO}" This must be the final sentence.'
            ),
            f"VOICE-OPTIMIZED SCRIPT (Portuguese):\n{texto}",
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
}


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


class AppSettingsIn(BaseModel):
    temasPrioritarios: list[str] = Field(default_factory=list, max_length=80)
    palavrasProibidas: list[str] = Field(default_factory=list, max_length=120)
    radar: RadarSettingsIn = Field(default_factory=RadarSettingsIn)
    integracoes: IntegrationsSettingsIn = Field(default_factory=IntegrationsSettingsIn)


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


def _private_avatar_library(command: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lista identidades privadas e todos os visuais de cada identidade."""
    command = command or _heygen_cli()
    response = _run_heygen_json(
        command,
        ["avatar", "list", "--ownership", "private", "--limit", "50"],
        timeout=45,
    )
    groups = _find_value(response, "data")
    if not isinstance(groups, list):
        groups = []

    looks: list[dict[str, Any]] = []
    for group in groups:
        group_id = str(group.get("id") or "")
        if not group_id:
            continue
        look_response = _run_heygen_json(
            command,
            ["avatar", "looks", "list", "--group-id", group_id, "--limit", "50"],
            timeout=45,
        )
        group_looks = _find_value(look_response, "data")
        if not isinstance(group_looks, list):
            continue
        for raw_look in group_looks:
            if not isinstance(raw_look, dict):
                continue
            look = dict(raw_look)
            look["group_id"] = look.get("group_id") or group_id
            look["group_name"] = group.get("name") or "Identidade sem nome"
            looks.append(look)
    return groups, looks


def _heygen_default_avatar_id(avatars: list[dict[str, Any]]) -> str:
    configured = os.getenv("HEYGEN_DEFAULT_AVATAR_ID")
    allowed_ids = {str(avatar.get("id")) for avatar in avatars}
    if configured in allowed_ids:
        return configured
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


@app.get("/api/heygen/catalog")
def heygen_catalog() -> dict:
    """Catalogo de avatares e vozes privados disponiveis para producao."""
    _, looks = _private_avatar_library()
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
        "defaultAvatarId": _heygen_default_avatar_id(avatars),
        "defaultVoiceId": _heygen_default_voice_id(),
    }


@app.get("/api/heygen/avatars")
def heygen_avatars() -> dict:
    """Lista identidades privadas e todos os visuais criados na conta conectada."""
    groups, looks = _private_avatar_library()
    return {"avatars": groups, "looks": looks, "jobs": _load_avatar_jobs()}


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
    return {
        "trends": map_trends(sheets.get("radar", [])),
        "ideas": map_ideas(sheets.get("ideias", [])),
        "scripts": map_scripts(sheets.get("roteiros", [])),
        "videoJobs": _load_video_jobs(),
        "calendarPosts": map_calendar(sheets.get("calendario", [])),
        "performance": map_performance(sheets.get("performance", [])),
        "settings": _load_settings(),
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
    idempotencyKey: str | None = Field(default=None, min_length=8, max_length=128)


class NaturalizeScriptIn(BaseModel):
    text: str = Field(min_length=20, max_length=6000)
    medicalCautions: str = Field(default="", max_length=2000)
    durationSeconds: Literal[10, 15, 30, 45, 60] = 45


_NATURAL_SCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

_NATURAL_SCRIPT_SYSTEM = """Voce e um diretor de fala para videos curtos do Dr. Guilherme.
Transforme o texto em portugues brasileiro falado, espontaneo, humano e facil de entender.

Regras obrigatorias:
- Preserve exatamente o sentido, os fatos e os cuidados medicos do texto original.
- Nao acrescente diagnosticos, tratamentos, exemplos clinicos, doses ou promessas.
- Use frases curtas, contracoes naturais e transicoes discretas.
- Evite linguagem de artigo, listas, titulos, jargao e repeticoes.
- Nao use indicacoes de cena, parenteses, emojis ou marcacoes de pausa.
- Mantenha um tom acolhedor, seguro e profissional.
- Termine exatamente com: "Me siga para mais dicas, e obrigado."
- Responda somente no JSON solicitado."""


@app.post("/api/scripts/naturalize")
def naturalize_script(payload: NaturalizeScriptIn) -> dict:
    """Transforma o roteiro em fala natural somente apos acao explicita do usuario."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Defina ANTHROPIC_API_KEY no arquivo .env para naturalizar com IA.",
        )
    import anthropic

    source = (
        f"DURACAO ALVO: {payload.durationSeconds} segundos\n"
        f"CUIDADOS MEDICOS: {payload.medicalCautions or 'Manter conteudo educativo.'}\n"
        f"TEXTO ORIGINAL:\n{payload.text}"
    )
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_tokens=1200,
            system=_NATURAL_SCRIPT_SYSTEM,
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

    natural_text = re.sub(
        re.escape(MANDATORY_VIDEO_OUTRO),
        "",
        natural_text,
        flags=re.IGNORECASE,
    ).strip()
    natural_text = f"{natural_text.rstrip(' .')}. {MANDATORY_VIDEO_OUTRO}"
    compliance = _pack_compliance({"text": natural_text})
    if compliance["blocked"]:
        raise HTTPException(
            status_code=422,
            detail="O texto naturalizado foi bloqueado pela revisao medica. Revise manualmente.",
        )
    return {"ok": True, "text": natural_text}


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
    _validate_final_narration(script, payload.narrationText, payload.durationSeconds)
    try:
        balance_before, currency_before = _heygen_wallet(command)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, HTTPException):
        balance_before, currency_before = None, None
    _, private_looks = _private_avatar_library(command)
    ready_looks = [look for look in private_looks if look.get("status") == "completed"]
    avatar_id = payload.avatarId or _heygen_default_avatar_id(ready_looks)
    voice_id = payload.voiceId or _heygen_default_voice_id()
    allowed_avatar_ids = {look.get("id") for look in ready_looks}
    if avatar_id not in allowed_avatar_ids:
        raise HTTPException(status_code=400, detail="Selecione um avatar privado pronto.")

    args = [
        command,
        "video-agent",
        "create",
        "--prompt",
        _video_prompt(
            script,
            duration_seconds=payload.durationSeconds,
            speech_mode=payload.speechMode,
            captions=payload.captions,
            optimize_pronunciation=payload.optimizePronunciation,
            narration_text=payload.narrationText,
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
    job["productionSettings"]["avatarId"] = avatar_id
    job["submissionState"] = "submitting"
    job["atualizadoEm"] = _now()
    _job_store().upsert("video", job)
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

    job["status"] = "fila"
    job["submissionState"] = "submitted"
    job["atualizadoEm"] = _now()
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
    clipCount: int = Field(default=3, ge=1, le=8)
    minDuration: int = Field(default=15, ge=8, le=90)
    maxDuration: int = Field(default=45, ge=10, le=120)
    durationMode: Literal["preset", "auto"] = "preset"
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
    if project.get("status") != "erro":
        raise HTTPException(status_code=409, detail="Somente projetos com erro podem ser repetidos.")

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
    return {
        "ok": True,
        "added": max(depois - antes, 0),
        "queries": query_terms,
        "log": "\n\n".join(log)[-1500:],
    }


# --------------------------------------------------------------------------- #
# Escrita de status de volta no Google Sheets
# --------------------------------------------------------------------------- #
TAB_RANGE = {
    "radar": "'Radar Tendencias'!A:L",
    "ideias": "'Ideias'!A:K",
    "roteiros": "'Roteiros'!A:P",
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
    criadoEm: str | None = None
    link: str | None = None
    status: str = "aguardando_validacao"


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


_NARRATION_PLACEHOLDERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"hook educativo sugerido|revise antes de aprovar", re.I), "Hook ainda parece sugestao automatica"),
    (re.compile(r"\brascunho\b", re.I), "Texto ainda contem marcacao de rascunho"),
    (re.compile(r"angulo:\s*angulo|ângulo:\s*ângulo", re.I), "Angulo duplicado ou com label tecnico"),
    (re.compile(r"explicar o tema sem prescrever|virada educativa reforcando", re.I), "Trecho ainda esta escrito como instrucao interna"),
]


def _narration_quality_issues(text: str, duration_seconds: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    issues: list[str] = []
    for pattern, issue in _NARRATION_PLACEHOLDERS:
        if pattern.search(normalized):
            issues.append(issue)

    outro_matches = re.findall(re.escape(MANDATORY_VIDEO_OUTRO), normalized, flags=re.I)
    if len(outro_matches) != 1:
        issues.append("Encerramento padrao deve aparecer exatamente uma vez")
    elif not normalized.lower().endswith(MANDATORY_VIDEO_OUTRO.lower()):
        issues.append("Encerramento padrao precisa ser a ultima frase")

    word_count = len([word for word in re.split(r"\s+", normalized) if word])
    minimum_words = 18 if duration_seconds <= 15 else 35 if duration_seconds <= 30 else 50 if duration_seconds <= 45 else 65
    if word_count < minimum_words:
        issues.append(f"Texto muito curto para {duration_seconds}s")

    return list(dict.fromkeys(issues))


def _validate_final_narration(script: dict[str, Any], narration_text: str | None, duration_seconds: int = 45) -> str:
    """Valida exatamente a fala que sera incorporada ao prompt pago do HeyGen."""
    text = narration_text.strip() if narration_text and narration_text.strip() else _script_text(script)
    if not text:
        raise HTTPException(status_code=422, detail="O texto falado esta vazio.")
    final_text = text
    if MANDATORY_VIDEO_OUTRO.lower() not in final_text.lower():
        final_text = f"{final_text.rstrip()} {MANDATORY_VIDEO_OUTRO}"
    compliance = _pack_compliance({"narration": final_text})
    if compliance["blocked"]:
        reasons = "; ".join(compliance["issues"])
        raise HTTPException(
            status_code=422,
            detail=f"Texto falado bloqueado pelo compliance final: {reasons}.",
        )
    quality_issues = _narration_quality_issues(final_text, duration_seconds)
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
