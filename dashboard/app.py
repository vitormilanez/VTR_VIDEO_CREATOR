#!/usr/bin/env python3
"""Dashboard local sem dependencias de UI externas."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import csv
import re
from collections import Counter
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")

SHEETS = {
    "radar": "'Radar Tendencias'!A:L",
    "ideias": "'Ideias'!A:M",
    "roteiros": "'Roteiros'!A:P",
    "calendario": "'Calendario'!A:N",
    "performance": "'Performance'!A:N",
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 120
SNAPSHOT_PATH = ROOT / "data" / "sheets_snapshot.json"
PRODUCTION_DIR = ROOT / "production_videos"
DEFAULT_AVATAR_ID = "2835cbcbdd65484c809bd0f6f80313e2"
DEFAULT_VOICE_ID = "33a98f732fe144d9a40f5cf33a7e95ec"


def rows_to_dicts(values: list[list[str]]) -> list[dict[str, str]]:
    if not values:
        return []
    headers = [str(value).strip() for value in values[0]]
    rows = []
    for row in values[1:]:
        record = {
            header: str(row[index]).strip() if index < len(row) else ""
            for index, header in enumerate(headers)
            if header
        }
        if any(record.values()):
            rows.append(record)
    return rows


def counter_by(rows: list[dict[str, str]], column: str) -> dict[str, int]:
    counter = Counter((row.get(column) or "Sem status").strip() for row in rows)
    return dict(counter)


def numeric_sum(rows: list[dict[str, str]], column: str) -> int:
    total = 0.0
    for row in rows:
        raw = (row.get(column) or "0").replace(".", "").replace(",", ".")
        try:
            total += float(raw)
        except ValueError:
            continue
    return int(total)


def load_sheets() -> dict[str, list[dict[str, str]]]:
    from integrations.google_sheets_rest_client import GoogleSheetsRestClient

    client = GoogleSheetsRestClient()
    return {name: rows_to_dicts(client.get_values(range_name)) for name, range_name in SHEETS.items()}


def latest_trends_csv() -> Path | None:
    output_dir = ROOT / "trend_hunter" / "output"
    files = sorted(output_dir.glob("trends_*.csv"), reverse=True)
    return files[0] if files else None


def load_local_data() -> dict[str, list[dict[str, str]]]:
    if SNAPSHOT_PATH.exists():
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        sheets = snapshot.get("sheets", {})
        return {
            "radar": sheets.get("radar", []),
            "ideias": sheets.get("ideias", []),
            "roteiros": sheets.get("roteiros", []),
            "calendario": sheets.get("calendario", []),
            "performance": sheets.get("performance", []),
        }

    radar: list[dict[str, str]] = []
    trends_path = latest_trends_csv()
    if trends_path:
        with trends_path.open("r", encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                score = row.get("score", "")
                try:
                    score_number = int(float(score or 0))
                except ValueError:
                    score_number = 0
                radar.append(
                    {
                        "Data": row.get("publicado_em") or "",
                        "Tema": (row.get("termos_encontrados") or row.get("trend") or "").split(",")[0].strip(),
                        "Subtema": row.get("trend", ""),
                        "Fonte": row.get("fonte", ""),
                        "Link referência": row.get("link_da_fonte", ""),
                        "Sinal de tendência": row.get("trend", ""),
                        "Dor do público": row.get("angulo_de_conteudo", ""),
                        "Potencial Viral": str(min(10, max(1, round(score_number / 7)))),
                        "Prioridade": "Alta" if score_number >= 55 else "Media" if score_number >= 40 else "Baixa",
                        "Status": "Coletado localmente",
                        "Observações": row.get("cuidado_medico_compliance", ""),
                    }
                )
    return {
        "radar": radar,
        "ideias": [],
        "roteiros": [],
        "calendario": [],
        "performance": [],
    }


def dashboard_data() -> dict[str, list[dict[str, str]]]:
    if os.getenv("DASHBOARD_LIVE_SHEETS") == "1":
        return load_sheets()
    return load_local_data()


def summary_payload() -> dict[str, Any]:
    data = dashboard_data()
    roteiros_status = counter_by(data["roteiros"], "Status")
    calendario_status = counter_by(data["calendario"], "Status")
    performance = data["performance"]
    jobs = production_jobs()
    completed_row_ids = {
        str(job.get("row_id"))
        for job in jobs
        if job.get("status") == "completed" and job.get("row_id") is not None
    }
    return {
        "counts": {
            "tendencias": len(data["radar"]),
            "ideias": len(data["ideias"]),
            "roteiros": len(data["roteiros"]),
            "validacao_medica": roteiros_status.get("Aguardando validação médica", 0),
            "aprovados_video": roteiros_status.get("Aprovado para video", 0),
            "agendados": calendario_status.get("Agendado", 0),
        },
        "status": {
            "radar": counter_by(data["radar"], "Status"),
            "roteiros": roteiros_status,
            "calendario": calendario_status,
        },
        "performance": {
            "views": numeric_sum(performance, "Views"),
            "comentarios": numeric_sum(performance, "Comentários"),
            "salvamentos": numeric_sum(performance, "Salvamentos"),
            "compartilhamentos": numeric_sum(performance, "Compartilhamentos"),
            "leads": numeric_sum(performance, "Leads"),
        },
        "tables": {
            "roteiros": with_production_status(with_row_ids(data["roteiros"][:80]), completed_row_ids),
            "performance": performance[:80],
        },
        "mode": "live" if os.getenv("DASHBOARD_LIVE_SHEETS") == "1" else "snapshot" if SNAPSHOT_PATH.exists() else "local",
    }


def with_row_ids(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"_row_id": str(index), **row} for index, row in enumerate(rows)]


def with_production_status(rows: list[dict[str, str]], completed_row_ids: set[str]) -> list[dict[str, str]]:
    enriched = []
    for row in rows:
        produced = row.get("_row_id") in completed_row_ids
        enriched.append({**row, "Produção": "Vídeo feito" if produced else "Pendente"})
    return enriched


def slugify(value: str, fallback: str = "video") -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized[:80] or fallback


def pick_first(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return value.strip()
    return ""


def build_script_from_roteiro(row: dict[str, str]) -> str:
    from integrations.portuguese_br import apply_portuguese_br_accents

    title = pick_first(row, ["Título", "Titulo", "Tema"]) or "Roteiro"
    hook = pick_first(row, ["Hook"])
    conflict = pick_first(row, ["Dor/Conflito", "Dor do público", "Dor do publico"])
    explanation = pick_first(row, ["Explicação simples", "Explicacao simples", "Roteiro", "Texto"])
    turn = pick_first(row, ["Virada/Provocação", "Virada/Provocacao"])
    cta = pick_first(row, ["CTA"])
    care = pick_first(row, ["Cuidados médicos", "Cuidado médico", "Cuidados medicos", "Cuidado medico"])

    pieces = [
        hook or title,
        conflict,
        explanation,
        turn,
        cta,
        care,
    ]
    script = " ".join(piece.strip() for piece in pieces if piece and piece.strip())
    return apply_portuguese_br_accents(script)


def improve_script_for_video(script: str) -> str:
    from integrations.portuguese_br import apply_portuguese_br_accents

    cleaned = apply_portuguese_br_accents(re.sub(r"\s+", " ", script).strip())
    if not cleaned:
        return ""

    if not re.search(r"(procure|converse|consulte|avaliação|médico)", cleaned, re.IGNORECASE):
        cleaned += " Converse com seu médico antes de iniciar qualquer tratamento."

    opening = "Antes de culpar sua força de vontade, olha isso: "
    if not cleaned.lower().startswith(("antes de", "você", "voce", "muita gente", "se")):
        cleaned = opening + cleaned[0].lower() + cleaned[1:]

    return apply_portuguese_br_accents(cleaned)


def production_jobs() -> list[dict[str, Any]]:
    jobs_path = PRODUCTION_DIR / "jobs.json"
    if not jobs_path.exists():
        return []
    return json.loads(jobs_path.read_text(encoding="utf-8"))


def available_avatar_looks() -> list[dict[str, str]]:
    avatars = [
        {
            "name": "Avatar padrão",
            "id": os.getenv("HEYGEN_DEFAULT_AVATAR_ID", "2835cbcbdd65484c809bd0f6f80313e2"),
            "gender": "Man",
            "status": "completed",
            "avatar_type": "photo_avatar",
            "preferred_orientation": "portrait",
            "default_voice_id": os.getenv("HEYGEN_DEFAULT_VOICE_ID", ""),
        }
    ]
    avatar_looks_path = ROOT / "data" / "heygen_avatar_looks.json"
    if avatar_looks_path.exists():
        avatar_looks = json.loads(avatar_looks_path.read_text(encoding="utf-8"))
        for look in avatar_looks.get("selected_photos", []):
            avatars.append(
                {
                    "name": look.get("name", ""),
                    "id": look.get("avatar_id", ""),
                    "gender": "Man",
                    "status": look.get("status", ""),
                    "avatar_type": "photo_avatar",
                    "preferred_orientation": "portrait",
                    "default_voice_id": os.getenv("HEYGEN_DEFAULT_VOICE_ID", ""),
                }
            )
    return avatars


def save_production_job(job: dict[str, Any]) -> None:
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    jobs = production_jobs()
    jobs = [existing for existing in jobs if existing.get("video_id") != job.get("video_id")]
    jobs.insert(0, job)
    (PRODUCTION_DIR / "jobs.json").write_text(json.dumps(jobs[:100], ensure_ascii=False, indent=2), encoding="utf-8")


def get_roteiro(row_id: int) -> dict[str, str]:
    roteiros = dashboard_data()["roteiros"]
    if row_id < 0 or row_id >= len(roteiros):
        raise RuntimeError("Roteiro não encontrado.")
    return roteiros[row_id]


def production_preview(row_id: int) -> dict[str, Any]:
    from integrations.portuguese_br import prepare_script_for_heygen_voice

    row = get_roteiro(row_id)
    script = build_script_from_roteiro(row)
    improved_script = improve_script_for_video(script)
    return {
        "row_id": row_id,
        "roteiro": row,
        "script": improved_script,
        "voice_script": prepare_script_for_heygen_voice(improved_script),
    }


def create_production_video(
    row_id: int,
    script_override: str | None = None,
    avatar_id: str | None = None,
    caption: bool = True,
    pronunciation_mode: bool = True,
) -> dict[str, Any]:
    from integrations.heygen_client import HeyGenClient
    from integrations.portuguese_br import apply_portuguese_br_accents, prepare_script_for_heygen_voice

    preview = production_preview(row_id)
    row = preview["roteiro"]
    title = pick_first(row, ["Título", "Titulo", "Tema"]) or "Video Dr Guilherme"
    display_script = improve_script_for_video(script_override) if script_override else preview["script"]
    display_script = apply_portuguese_br_accents(display_script)
    voice_script = prepare_script_for_heygen_voice(display_script) if pronunciation_mode else display_script
    if not display_script:
        raise RuntimeError("O roteiro está vazio.")
    avatar_id = avatar_id or os.getenv("HEYGEN_DEFAULT_AVATAR_ID", DEFAULT_AVATAR_ID)
    voice_id = os.getenv("HEYGEN_DEFAULT_VOICE_ID", DEFAULT_VOICE_ID)
    client = HeyGenClient()
    result = client.create_avatar_video(
        avatar_id=avatar_id,
        voice_id=voice_id,
        title=title,
        script=voice_script,
        aspect_ratio="9:16",
        resolution="720p",
        caption=caption,
    )
    data = result.get("data", result)
    video_id = data.get("video_id") or data.get("id")
    if not video_id:
        raise RuntimeError(f"A HeyGen não retornou video_id: {result}")

    job = {
        "video_id": video_id,
        "row_id": row_id,
        "title": title,
        "status": data.get("status", "waiting"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script": display_script,
        "voice_script": voice_script,
        "pronunciation_mode": pronunciation_mode,
        "avatar_id": avatar_id,
        "voice_id": voice_id,
        "caption": caption,
        "local_video_path": "",
        "local_subtitle_path": "",
        "video_page_url": "",
    }
    save_production_job(job)
    return job


def refresh_production_video(video_id: str) -> dict[str, Any]:
    from integrations.heygen_client import HeyGenClient

    client = HeyGenClient()
    result = client.get_video(video_id)
    data = result.get("data", result)
    jobs = production_jobs()
    job = next((existing for existing in jobs if existing.get("video_id") == video_id), {"video_id": video_id})
    job.update(
        {
            "status": data.get("status", job.get("status", "")),
            "duration": data.get("duration"),
            "video_url": data.get("video_url"),
            "captioned_video_url": data.get("captioned_video_url"),
            "subtitle_url": data.get("subtitle_url"),
            "thumbnail_url": data.get("thumbnail_url"),
            "video_page_url": data.get("video_page_url") or job.get("video_page_url", ""),
            "failure_code": data.get("failure_code"),
            "failure_message": data.get("failure_message"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    if job["status"] == "completed":
        title_slug = slugify(job.get("title", "video"))
        base = PRODUCTION_DIR / f"{datetime.now().date().isoformat()}_{title_slug}_{video_id[:8]}"
        source_url = job.get("captioned_video_url") or job.get("video_url")
        if source_url and not job.get("local_video_path"):
            video_path = client.download_file(source_url, base.with_suffix(".mp4"))
            job["local_video_path"] = str(video_path)
        if job.get("subtitle_url") and not job.get("local_subtitle_path"):
            subtitle_path = client.download_file(job["subtitle_url"], base.with_suffix(".srt"))
            job["local_subtitle_path"] = str(subtitle_path)

    save_production_job(job)
    return job


def heygen_payload() -> dict[str, Any]:
    jobs = production_jobs()
    completed_jobs = [job for job in jobs if job.get("status") == "completed"]
    estimated_seconds = sum(float(job.get("duration") or 0) for job in completed_jobs)
    estimated_minutes = round(estimated_seconds / 60, 2)
    local_usage = {
        "videos_total": len(jobs),
        "videos_completed": len(completed_jobs),
        "estimated_seconds": round(estimated_seconds, 2),
        "estimated_minutes": estimated_minutes,
    }

    should_use_live = os.getenv("DASHBOARD_LIVE_HEYGEN") == "1" or bool(os.getenv("HEYGEN_API_KEY"))
    if not should_use_live:
        return {
            "mode": "local",
            "local_usage": local_usage,
            "user": {
                "email": "drguilhermeia@gmail.com",
                "billing_type": "wallet",
                "wallet": {"remaining_balance": "30.00"},
            },
            "avatars": [
                {
                    "name": "drguilhermeia",
                    "id": os.getenv("HEYGEN_DEFAULT_AVATAR_ID", "6cfd960b8d8d45bcae1ce3bbe4bd74dd"),
                    "gender": "Man",
                    "looks_count": "7",
                    "default_voice_id": os.getenv("HEYGEN_DEFAULT_VOICE_ID", ""),
                }
            ],
        }

    from integrations.heygen_client import HeyGenClient

    try:
        client = HeyGenClient()
        user = client.get_current_user().get("data", {})
        mode = "live"
        live_error = ""
    except Exception as exc:
        user = {
            "email": "drguilhermeia@gmail.com",
            "billing_type": "wallet",
            "wallet": {"remaining_balance": "30.00"},
        }
        mode = "local"
        live_error = str(exc)
    avatars = available_avatar_looks()
    return {"mode": mode, "live_error": live_error, "user": user, "avatars": avatars, "local_usage": local_usage}


def instagram_payload() -> dict[str, Any]:
    from integrations.instagram_client import InstagramClient

    client = InstagramClient()
    if not client.is_configured:
        return {"configured": False}
    return {
        "configured": True,
        "profile": client.profile(),
        "media": client.recent_media(limit=10),
    }


def cached_payload(key: str, loader) -> dict[str, Any]:
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    payload = loader()
    _CACHE[key] = (now, payload)
    return payload


def run_command(args: list[str], timeout: int = 180) -> dict[str, Any]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": " ".join(args),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def run_trend_pipeline(limit: int = 20) -> dict[str, Any]:
    python = sys.executable
    steps = [
        run_command([python, "trend_hunter/trend_hunter.py"], timeout=240),
    ]
    if steps[-1]["returncode"] == 0:
        steps.append(run_command([python, "sync_trends_to_sheets.py", "--limit", str(limit)], timeout=120))
    if steps[-1]["returncode"] == 0:
        steps.append(run_command([python, "sync_sheets_snapshot.py"], timeout=120))

    _CACHE.clear()
    ok = all(step["returncode"] == 0 for step in steps)
    return {"ok": ok, "steps": steps}


HTML = r"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Video Creator</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #657282;
      --line: #d9e0e8;
      --blue: #2563eb;
      --green: #0f8a5f;
      --orange: #b45309;
      --red: #b42318;
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      letter-spacing: 0;
    }
    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 { font-size: 19px; margin: 0; font-weight: 700; }
    h2 { font-size: 15px; margin: 0 0 14px; }
    main { padding: 22px 28px 32px; max-width: 1480px; margin: 0 auto; }
    button, a.button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 9px 12px;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
    }
    button.primary { background: var(--blue); color: white; border-color: var(--blue); }
    button:disabled { opacity: .58; cursor: not-allowed; }
    select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      font-size: 13px;
      background: #fff;
      color: var(--ink);
    }
    textarea { min-height: 180px; resize: vertical; line-height: 1.45; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .control-row { display: grid; grid-template-columns: 1fr 180px; gap: 10px; margin-top: 10px; align-items: end; }
    .checkbox-line { display: flex; align-items: center; gap: 8px; min-height: 38px; font-size: 13px; }
    .checkbox-line input { width: 16px; height: 16px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 18px; }
    .tab.active { background: var(--ink); color: white; border-color: var(--ink); }
    .grid { display: grid; gap: 14px; }
    .metrics { grid-template-columns: repeat(6, minmax(140px, 1fr)); }
    .three { grid-template-columns: repeat(3, 1fr); }
    .two { grid-template-columns: 1fr 1fr; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      margin-bottom: 16px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 14px 16px;
      min-height: 82px;
    }
    .metric .label { color: var(--muted); font-size: 12px; }
    .metric .value { font-size: 28px; font-weight: 750; margin-top: 8px; white-space: nowrap; }
    .status-list { display: grid; gap: 8px; }
    .status-item {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #eef2f6;
      padding: 7px 0;
      font-size: 13px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid #e7edf4; padding: 8px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; background: #f9fbfc; position: sticky; top: 0; }
    .table-wrap { max-height: 420px; overflow: auto; border: 1px solid var(--line); border-radius: var(--radius); }
    .muted { color: var(--muted); }
    .ok { color: var(--green); font-weight: 650; }
    .warn { color: var(--orange); font-weight: 650; }
    .error { color: var(--red); }
    .hidden { display: none; }
    @media (max-width: 1000px) {
      .metrics, .three, .two { grid-template-columns: 1fr 1fr; }
      header { padding: 0 16px; }
      main { padding: 18px 16px; }
    }
    @media (max-width: 640px) {
      .metrics, .three, .two { grid-template-columns: 1fr; }
      .tabs { overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>AI Video Creator</h1>
    <div>
      <a class="button" href="https://docs.google.com/spreadsheets/d/1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ/edit" target="_blank">Planilha</a>
      <button class="primary" onclick="refresh()">Atualizar</button>
    </div>
  </header>
  <main>
    <div class="tabs">
      <button class="tab active" data-tab="pipeline">Pipeline</button>
      <button class="tab" data-tab="tendencias">Tendências</button>
      <button class="tab" data-tab="producao">Produção</button>
      <button class="tab" data-tab="gastos">Gastos</button>
      <button class="tab" data-tab="instagram">Instagram</button>
    </div>

    <div id="message" class="muted">Carregando dados...</div>

    <div id="pipeline" class="page">
      <div class="grid metrics" id="metrics"></div>
      <div class="grid three">
        <section><h2>Radar por Status</h2><div class="status-list" id="radarStatus"></div></section>
        <section><h2>Roteiros por Status</h2><div class="status-list" id="roteirosStatus"></div></section>
        <section><h2>Calendário por Status</h2><div class="status-list" id="calendarioStatus"></div></section>
      </div>
    </div>

    <div id="tendencias" class="page hidden">
      <section>
        <h2>Buscar novas tendências</h2>
        <p class="muted">Roda o Trend Hunter, adiciona apenas tendências novas na aba Radar Tendencias e atualiza o snapshot do dashboard.</p>
        <button class="primary" id="runTrendsButton" onclick="runTrends()">Buscar e adicionar à planilha</button>
        <div id="trendRunResult" class="muted" style="margin-top:14px"></div>
      </section>
      <section>
        <h2>Regras</h2>
        <div class="status-list">
          <div class="status-item"><span>Modo de escrita</span><strong>Append</strong></div>
          <div class="status-item"><span>Deduplicação</span><strong>Link + sinal de tendência</strong></div>
          <div class="status-item"><span>Status inicial</span><strong>Pendente</strong></div>
          <div class="status-item"><span>Destino</span><strong>Radar Tendencias</strong></div>
        </div>
      </section>
    </div>

    <div id="producao" class="page hidden">
      <section>
        <h2>Gerar vídeo a partir de roteiro</h2>
        <div class="grid two">
          <div>
            <label class="muted" for="roteiroSelect">Roteiro</label>
            <select id="roteiroSelect" onchange="previewRoteiro()"></select>
            <div class="control-row">
              <div>
                <label class="muted" for="avatarSelect">Avatar HeyGen</label>
                <select id="avatarSelect"></select>
              </div>
              <label class="checkbox-line">
                <input id="captionToggle" type="checkbox" checked>
                Incluir legenda
              </label>
              <label class="checkbox-line">
                <input id="pronunciationToggle" type="checkbox" checked onchange="updateVoicePreview()">
                Melhorar pronúncia PT-BR
              </label>
            </div>
            <div class="actions" style="margin-top:12px">
              <button onclick="previewRoteiro()">Pré-visualizar roteiro</button>
              <button class="primary" id="createVideoButton" onclick="createVideo()">Gerar vídeo</button>
            </div>
            <p class="muted">Você pode editar livremente antes de gerar. Ao enviar, o sistema ainda corrige acentos e reforça o formato de fala para Reels.</p>
          </div>
          <div>
            <label class="muted" for="scriptPreview">Roteiro editável que será enviado</label>
            <textarea id="scriptPreview" oninput="updateVoicePreview()" placeholder="Escolha um roteiro ou escreva aqui o texto final do vídeo."></textarea>
            <label class="muted" for="voicePreview">Prévia para voz HeyGen</label>
            <textarea id="voicePreview" readonly placeholder="A prévia de pronúncia aparece aqui."></textarea>
          </div>
        </div>
        <div id="productionResult" class="muted" style="margin-top:14px"></div>
      </section>
      <section>
        <div class="actions" style="justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">Vídeos gerados localmente</h2>
          <button onclick="refreshProductionJobs()">Atualizar vídeos</button>
        </div>
        <div class="table-wrap" id="productionJobsTable"></div>
      </section>
      <section><h2>Roteiros</h2><div class="table-wrap" id="roteirosTable"></div></section>
    </div>

    <div id="gastos" class="page hidden">
      <div class="grid metrics" id="heygenMetrics"></div>
      <section><h2>Avatares</h2><div class="table-wrap" id="avatarsTable"></div></section>
    </div>

    <div id="instagram" class="page hidden">
      <div class="grid metrics" id="performanceMetrics"></div>
      <section><h2>Instagram</h2><div id="instagramPanel"></div></section>
      <section><h2>Performance da Planilha</h2><div class="table-wrap" id="performanceTable"></div></section>
    </div>
  </main>
  <script>
    const state = { summary: null, heygen: null, instagram: null, jobs: [], avatars: [] };
    const columns = {
      roteiros: ["Produção", "Categoria", "Tema", "Título", "Hook", "CTA", "Cuidados médicos", "Risco", "Formato sugerido", "Status", "Aprovador", "Link doc/video"],
      performance: ["Data", "Canal", "Tema", "Views", "Retenção %", "Comentários", "Salvamentos", "Compartilhamentos", "Leads", "Nota", "Link post"],
      avatars: ["name", "id", "status", "avatar_type", "preferred_orientation", "default_voice_id"],
      jobs: ["created_at", "title", "status", "duration", "local_video_path", "video_page_url", "failure_message"]
    };

    document.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
        btn.classList.add("active");
        document.querySelectorAll(".page").forEach(page => page.classList.add("hidden"));
        document.getElementById(btn.dataset.tab).classList.remove("hidden");
      });
    });

    function setMessage(text, type = "muted") {
      const el = document.getElementById("message");
      el.className = type;
      el.textContent = text;
    }

    async function api(path) {
      const res = await fetch(path);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || "Erro");
      return payload;
    }

    async function apiPost(path, body = {}) {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || "Erro");
      return payload;
    }

    function metric(label, value) {
      return `<div class="metric"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(String(value ?? "n/d"))}</div></div>`;
    }

    function statusList(obj) {
      const entries = Object.entries(obj || {});
      if (!entries.length) return `<div class="muted">Sem dados</div>`;
      return entries.map(([k, v]) => `<div class="status-item"><span>${escapeHtml(k)}</span><strong>${v}</strong></div>`).join("");
    }

    function table(rows, cols) {
      rows = rows || [];
      if (!rows.length) return `<div class="muted" style="padding:14px">Sem dados</div>`;
      const head = cols.map(c => `<th>${escapeHtml(c)}</th>`).join("");
      const body = rows.map(row => `<tr>${cols.map(c => `<td>${linkify(row[c] || "")}</td>`).join("")}</tr>`).join("");
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function linkify(value) {
      const text = escapeHtml(String(value));
      if (String(value).startsWith("http")) return `<a href="${text}" target="_blank">${text}</a>`;
      return text;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]));
    }

    function money(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/d";
      return `US$ ${n.toFixed(2)}`;
    }

    function renderSummary() {
      const s = state.summary;
      const c = s.counts;
      document.getElementById("metrics").innerHTML = [
        metric("Tendências", c.tendencias),
        metric("Ideias", c.ideias),
        metric("Roteiros", c.roteiros),
        metric("Validação médica", c.validacao_medica),
        metric("Aprovados p/ vídeo", c.aprovados_video),
        metric("Agendados", c.agendados)
      ].join("");
      document.getElementById("radarStatus").innerHTML = statusList(s.status.radar);
      document.getElementById("roteirosStatus").innerHTML = statusList(s.status.roteiros);
      document.getElementById("calendarioStatus").innerHTML = statusList(s.status.calendario);
      document.getElementById("roteirosTable").innerHTML = table(s.tables.roteiros, columns.roteiros);
      renderRoteiroSelect(s.tables.roteiros);
      document.getElementById("performanceTable").innerHTML = table(s.tables.performance, columns.performance);
      document.getElementById("performanceMetrics").innerHTML = [
        metric("Views", s.performance.views),
        metric("Comentários", s.performance.comentarios),
        metric("Salvamentos", s.performance.salvamentos),
        metric("Compartilhamentos", s.performance.compartilhamentos),
        metric("Leads", s.performance.leads)
      ].join("");
    }

    function renderRoteiroSelect(rows) {
      const select = document.getElementById("roteiroSelect");
      const current = select.value;
      const options = (rows || []).map(row => {
        const title = row["Título"] || row["Titulo"] || row["Tema"] || `Roteiro ${row._row_id}`;
        const status = row["Status"] ? ` · ${row["Status"]}` : "";
        const production = row["Produção"] === "Vídeo feito" ? " · Vídeo feito" : "";
        return `<option value="${escapeHtml(row._row_id)}">${escapeHtml(title + status + production)}</option>`;
      });
      select.innerHTML = options.length ? options.join("") : `<option value="">Sem roteiros</option>`;
      if ([...select.options].some(option => option.value === current)) select.value = current;
      if (select.value) previewRoteiro();
    }

    function renderProductionJobs() {
      document.getElementById("productionJobsTable").innerHTML = table(state.jobs || [], columns.jobs);
    }

    function renderAvatarSelect() {
      const select = document.getElementById("avatarSelect");
      const current = select.value;
      const options = (state.avatars || [])
        .filter(avatar => avatar.id && (!avatar.status || avatar.status === "completed"))
        .map(avatar => `<option value="${escapeHtml(avatar.id)}">${escapeHtml(avatar.name || avatar.id)}</option>`);
      select.innerHTML = options.length ? options.join("") : `<option value="">Avatar padrão</option>`;
      if ([...select.options].some(option => option.value === current)) select.value = current;
    }

    function renderHeygen() {
      const h = state.heygen;
      const user = h.user || {};
      const wallet = user.wallet || {};
      const usage = user.usage_based || {};
      const localUsage = h.local_usage || {};
      document.querySelectorAll(".heygen-live-warning").forEach(el => el.remove());
      document.getElementById("heygenMetrics").innerHTML = [
        metric("Modo HeyGen", h.mode === "live" ? "ao vivo" : "local"),
        metric("Conta", user.email || "n/d"),
        metric("Saldo wallet", money(wallet.remaining_balance)),
        metric("Gasto atual", money(usage.spending_current_usd)),
        metric("Vídeos gerados", localUsage.videos_total ?? 0),
        metric("Minutos estimados", localUsage.estimated_minutes ?? 0),
        metric("Billing", user.billing_type || "n/d")
      ].join("");
      document.getElementById("avatarsTable").innerHTML = table(h.avatars || [], columns.avatars);
      if (h.live_error) {
        document.getElementById("avatarsTable").insertAdjacentHTML(
          "beforebegin",
          `<p class="warn heygen-live-warning">A HeyGen não respondeu a tempo. Mostrando saldo local e consumo estimado pelos vídeos gerados.</p>`
        );
      }
    }

    function renderInstagram() {
      const i = state.instagram;
      const panel = document.getElementById("instagramPanel");
      if (!i.configured) {
        panel.innerHTML = `
          <p class="warn">Instagram ainda não conectado via Meta API.</p>
          <p class="muted">As métricas acima vêm da aba Performance. Para puxar dados reais, configure META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID no .env.</p>
        `;
        return;
      }
      const p = i.profile || {};
      const media = (i.media || {}).data || [];
      panel.innerHTML = `
        <p class="ok">Conectado: @${escapeHtml(p.username || "perfil")}</p>
        <div class="grid metrics">
          ${metric("Seguidores", p.followers_count)}
          ${metric("Seguindo", p.follows_count)}
          ${metric("Mídias", p.media_count)}
        </div>
        <div class="table-wrap">${table(media, ["timestamp", "media_type", "like_count", "comments_count", "permalink"])}</div>
      `;
    }

    function renderRunResult(payload) {
      const result = document.getElementById("trendRunResult");
      const steps = payload.steps || [];
      result.className = payload.ok ? "ok" : "error";
      result.innerHTML = `
        <p>${payload.ok ? "Tendências atualizadas com sucesso." : "A atualização falhou."}</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Etapa</th><th>Status</th><th>Saída</th></tr></thead>
            <tbody>
              ${steps.map(step => `
                <tr>
                  <td>${escapeHtml(step.command)}</td>
                  <td>${step.returncode === 0 ? "OK" : "Erro " + step.returncode}</td>
                  <td><pre style="white-space:pre-wrap;margin:0">${escapeHtml(step.stdout || step.stderr || "")}</pre></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    }

    async function runTrends() {
      const button = document.getElementById("runTrendsButton");
      button.disabled = true;
      document.getElementById("trendRunResult").className = "muted";
      document.getElementById("trendRunResult").textContent = "Buscando tendências, adicionando à planilha e atualizando snapshot...";
      try {
        const payload = await apiPost("/api/run-trends", { limit: 20 });
        renderRunResult(payload);
        await refresh();
      } catch (err) {
        document.getElementById("trendRunResult").className = "error";
        document.getElementById("trendRunResult").textContent = err.message;
      } finally {
        button.disabled = false;
      }
    }

    async function previewRoteiro() {
      const rowId = document.getElementById("roteiroSelect").value;
      const preview = document.getElementById("scriptPreview");
      const voicePreview = document.getElementById("voicePreview");
      if (!rowId) {
        preview.value = "";
        voicePreview.value = "";
        return;
      }
      try {
        const payload = await apiPost("/api/production/preview", { row_id: Number(rowId) });
        preview.value = payload.script || "";
        voicePreview.value = payload.voice_script || prepareVoiceScript(preview.value);
      } catch (err) {
        preview.value = err.message;
        voicePreview.value = "";
      }
    }

    function prepareVoiceScript(text) {
      if (!text) return "";
      const replacements = [
        [/\bGLP-1\b/gi, "G L P um"],
        [/\bMounjaro\b/gi, "Maundjáro"],
        [/\bOzempic\b/gi, "Ozêmpic"],
        [/\bWegovy\b/gi, "Uegóvi"],
        [/\bRybelsus\b/gi, "Ribélsus"],
        [/\b30s\b/gi, "trinta segundos"],
        [/(\d+)\s*%/g, "$1 por cento"]
      ];
      let output = text.trim().replace(/\s+/g, " ");
      for (const [pattern, value] of replacements) {
        output = output.replace(pattern, value);
      }
      return output.replace(/([.!?])\s+/g, "$1\n");
    }

    function updateVoicePreview() {
      const script = document.getElementById("scriptPreview").value.trim();
      const pronunciation = document.getElementById("pronunciationToggle").checked;
      document.getElementById("voicePreview").value = pronunciation ? prepareVoiceScript(script) : script;
    }

    async function createVideo() {
      const rowId = document.getElementById("roteiroSelect").value;
      const script = document.getElementById("scriptPreview").value.trim();
      const avatarId = document.getElementById("avatarSelect").value;
      const caption = document.getElementById("captionToggle").checked;
      const pronunciation = document.getElementById("pronunciationToggle").checked;
      const button = document.getElementById("createVideoButton");
      const result = document.getElementById("productionResult");
      if (!rowId) {
        result.className = "error";
        result.textContent = "Selecione um roteiro primeiro.";
        return;
      }
      if (!script) {
        result.className = "error";
        result.textContent = "Escreva ou pré-visualize um roteiro antes de gerar.";
        return;
      }
      button.disabled = true;
      result.className = "muted";
      result.textContent = "Enviando vídeo para a HeyGen...";
      try {
        const job = await apiPost("/api/production/create-video", {
          row_id: Number(rowId),
          script,
          avatar_id: avatarId,
          caption,
          pronunciation_mode: pronunciation
        });
        result.className = "ok";
        result.textContent = `Vídeo enviado. Status: ${job.status}. ID: ${job.video_id}`;
        await refreshProductionJob(job.video_id);
      } catch (err) {
        result.className = "error";
        result.textContent = err.message;
      } finally {
        button.disabled = false;
      }
    }

    async function refreshProductionJob(videoId) {
      const result = document.getElementById("productionResult");
      try {
        const job = await apiPost("/api/production/refresh-video", { video_id: videoId });
        await loadProductionJobs();
        if (job.status === "completed") {
          result.className = "ok";
          result.innerHTML = `Vídeo pronto e salvo em: <strong>${escapeHtml(job.local_video_path || "")}</strong>`;
        } else if (job.status === "failed") {
          result.className = "error";
          result.textContent = job.failure_message || "A geração falhou.";
        } else {
          result.className = "muted";
          result.textContent = `Status atual: ${job.status}. Clique em Atualizar vídeos em alguns instantes.`;
        }
      } catch (err) {
        result.className = "error";
        result.textContent = err.message;
      }
    }

    async function loadProductionJobs() {
      const payload = await api("/api/production/jobs");
      state.jobs = payload.jobs || [];
      renderProductionJobs();
    }

    async function loadAvatars() {
      const payload = await api("/api/production/avatars");
      state.avatars = payload.avatars || [];
      renderAvatarSelect();
    }

    async function refreshProductionJobs() {
      const jobs = state.jobs || [];
      const pending = jobs.filter(job => job.video_id && !["completed", "failed"].includes(job.status));
      for (const job of pending) {
        await apiPost("/api/production/refresh-video", { video_id: job.video_id });
      }
      await loadProductionJobs();
    }

    async function refresh() {
      setMessage("Atualizando...");
      try {
        state.summary = await api("/api/summary");
        renderSummary();
        await loadProductionJobs();
        await loadAvatars();
        setMessage("Dados atualizados.", "ok");
      } catch (err) {
        setMessage(err.message, "error");
      }
      try {
        state.heygen = await api("/api/heygen");
        renderHeygen();
      } catch (err) {
        document.getElementById("heygenMetrics").innerHTML = `<section class="error">${escapeHtml(err.message)}</section>`;
      }
      try {
        state.instagram = await api("/api/instagram");
        renderInstagram();
      } catch (err) {
        document.getElementById("instagramPanel").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      }
    }

    refresh();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:
        if urlparse(self.path).path == "/":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/summary":
                self.send_json(cached_payload("summary", summary_payload))
            elif path == "/api/heygen":
                self.send_json(cached_payload("heygen", heygen_payload))
            elif path == "/api/instagram":
                self.send_json(cached_payload("instagram", instagram_payload))
            elif path == "/api/production/jobs":
                self.send_json({"jobs": production_jobs()})
            elif path == "/api/production/avatars":
                self.send_json({"avatars": available_avatar_looks()})
            elif path == "/api/refresh":
                _CACHE.clear()
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "Não encontrado"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            body = json.loads(raw_body or "{}")
            if path == "/api/run-trends":
                limit = int(body.get("limit", 20))
                self.send_json(run_trend_pipeline(limit=limit))
            elif path == "/api/production/preview":
                self.send_json(production_preview(int(body.get("row_id", 0))))
            elif path == "/api/production/create-video":
                script = str(body.get("script", "")).strip() or None
                avatar_id = str(body.get("avatar_id", "")).strip() or None
                caption = bool(body.get("caption", True))
                pronunciation_mode = bool(body.get("pronunciation_mode", True))
                self.send_json(
                    create_production_video(
                        int(body.get("row_id", 0)),
                        script_override=script,
                        avatar_id=avatar_id,
                        caption=caption,
                        pronunciation_mode=pronunciation_mode,
                    )
                )
            elif path == "/api/production/refresh-video":
                video_id = str(body.get("video_id", "")).strip()
                if not video_id:
                    raise RuntimeError("Informe o video_id.")
                self.send_json(refresh_production_video(video_id))
            else:
                self.send_json({"error": "Não encontrado"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> int:
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8501"))
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard local: http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
