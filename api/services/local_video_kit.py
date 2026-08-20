"""Renderiza e aplica o kit gráfico vertical sem APIs ou créditos externos."""
from __future__ import annotations

import base64
import html
import json
import math
import re
import selectors
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from api.services.local_video_captions import render_caption_assets, write_caption_timeline
from api.services.medical_identity import (
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_MINIMUM_END_CARD_SECONDS,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
)
from api.services.post_production_overlays import render_overlay
from api.services.transcript_service import transcribe_video_to_file


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
ACCENT_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
FIVE_STACK_DEFAULT_LINES = (
    "GLP-1 — sinal de saciedade",
    "Amilina — controle da fome",
    "Esvaziamento gástrico mais lento",
    "Oral: ~13% em 12 semanas",
    "Injetável: 24,3% em 36 semanas",
)
CLAUDE_MIDNIGHT_MODELS: dict[str, dict[str, Any]] = {
    "numberGlass": {
        "duration": 3.8,
        "startRatio": 0.16,
        "fields": (
            "DADO CLÍNICO",
            "24,3%",
            "de redução de peso em 36 semanas",
            "formulação injetável · fase inicial",
        ),
    },
    "editorialClip": {
        "duration": 4.2,
        "startRatio": 0.22,
        "fields": (
            "BOLETIM CLÍNICO",
            "N.º 04",
            "Uma molécula, dois receptores",
            "A Amycretin foi desenvolvida para agir no GLP-1 e na amilina ao mesmo tempo.",
            "Ensaios iniciais · em desenvolvimento",
        ),
    },
    "mechanismBars": {
        "duration": 3.6,
        "startRatio": 0.34,
        "fields": (
            "UM ALVO VS. DOIS",
            "Terapias atuais · 1 receptor",
            "Amycretin · GLP-1 + amilina",
            "Esquema de mecanismos — não é comparação de eficácia",
        ),
    },
    "evidenceStamp": {
        "duration": 4.4,
        "startRatio": 0.48,
        "fields": (
            "STATUS REGULATÓRIO",
            "AMYCRETIN",
            "Em desenvolvimento clínico",
            "PRÉ-CLÍN.",
            "FASE 1",
            "FASE 2",
            "FASE 3",
            "APROV.",
            "Ainda não disponível comercialmente.",
        ),
    },
    "glossarySource": {
        "duration": 4.2,
        "startRatio": 0.12,
        "fields": (
            "O TERMO",
            "Amilina",
            "Hormônio liberado junto com a insulina. Sinaliza saciedade ao cérebro e desacelera o esvaziamento do estômago.",
            "FONTE",
            "Ensaios clínicos iniciais · fase 1/2",
            "Resultados preliminares, grupos específicos",
        ),
    },
}


def _run(args: list[str], *, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "Falha no processamento local.")[-1800:])
    return process


def _run_ffmpeg_with_progress(
    args: list[str],
    *,
    expected_duration: float,
    output_path: Path,
    on_progress: Callable[[int, str], None],
    timeout: int = 1800,
    stall_timeout: int = 180,
) -> None:
    """Executa FFmpeg com heartbeat real e encerra somente um processo sem avanço."""
    command = [
        args[0],
        "-hide_banner",
        "-nostats",
        "-progress",
        "pipe:1",
        *args[1:],
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    if process.stdout is None:
        process.terminate()
        raise RuntimeError("Não foi possível acompanhar o processo do FFmpeg.")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    log_lines: deque[str] = deque(maxlen=180)
    started = time.monotonic()
    last_activity = started
    last_size = output_path.stat().st_size if output_path.is_file() else 0
    last_reported = -1
    stall_reason: str | None = None

    def stop_process() -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    try:
        while process.poll() is None:
            events = selector.select(timeout=1)
            for key, _mask in events:
                line = key.fileobj.readline()
                if not line:
                    continue
                clean = line.strip()
                if clean:
                    log_lines.append(clean)
                    last_activity = time.monotonic()
                name, separator, raw_value = clean.partition("=")
                if not separator or name not in {"out_time_us", "out_time_ms"}:
                    continue
                try:
                    rendered_seconds = max(0.0, float(raw_value) / 1_000_000)
                except ValueError:
                    continue
                fraction = min(1.0, rendered_seconds / max(expected_duration, 0.001))
                overall = min(94, 55 + int(fraction * 39))
                if overall > last_reported:
                    on_progress(overall, f"Renderizando MP4 · {round(fraction * 100)}% do vídeo")
                    last_reported = overall

            current_size = output_path.stat().st_size if output_path.is_file() else 0
            if current_size != last_size:
                last_size = current_size
                last_activity = time.monotonic()
            now = time.monotonic()
            if now - started > timeout:
                stall_reason = f"O render excedeu o limite de {timeout // 60} minutos."
                stop_process()
                break
            if now - last_activity > stall_timeout:
                stall_reason = (
                    f"O FFmpeg ficou {stall_timeout} segundos sem produzir novos quadros ou bytes."
                )
                stop_process()
                break
    finally:
        selector.close()

    return_code = process.wait()
    if stall_reason:
        raise RuntimeError(f"Render interrompido automaticamente. {stall_reason}")
    if return_code != 0:
        detail = "\n".join(log_lines) or "Falha no processamento local."
        raise RuntimeError(detail[-1800:])


def probe_duration(source: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe não está instalado.")
    process = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        timeout=30,
    )
    try:
        duration = float(process.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("O vídeo não possui duração válida.") from exc
    if duration <= 0:
        raise RuntimeError("O vídeo está vazio.")
    return duration


def _font_face(name: str, path: Path, *, style: str = "normal", weight: str = "400") -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f"@font-face{{font-family:'{name}';src:url(data:font/woff2;base64,{encoded}) "
        f"format('woff2');font-style:{style};font-weight:{weight};font-display:block}}"
    )


def _safe_text(value: Any, fallback: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or fallback)).strip()
    return html.escape(cleaned[:limit])


def _config_text(config: dict[str, Any], key: str, fallback: str, limit: int) -> str:
    """Keep legacy defaults while respecting an explicitly cleared optional field."""
    value = config[key] if key in config else fallback
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    return html.escape(cleaned[:limit])


def _five_stack_data(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize the reusable Claude stack without requiring it in old jobs."""
    raw = config.get("fiveStack")
    if not isinstance(raw, dict):
        raw = {}
    raw_lines = raw.get("lines") if isinstance(raw.get("lines"), list) else []
    lines = [
        re.sub(r"\s+", " ", str(raw_lines[index] if index < len(raw_lines) else fallback)).strip()[:118]
        or fallback
        for index, fallback in enumerate(FIVE_STACK_DEFAULT_LINES)
    ]
    start = raw.get("startSeconds")
    duration = raw.get("durationSeconds")
    return {
        "enabled": bool(config.get("manualVisualsEnabled")) and bool(raw.get("enabled")),
        "startSeconds": float(start) if isinstance(start, (int, float)) else None,
        "durationSeconds": min(
            8.0,
            max(1.0, float(duration) if isinstance(duration, (int, float)) else 4.5),
        ),
        "lines": lines,
    }


def _five_stack_enabled(config: dict[str, Any]) -> bool:
    return bool(_five_stack_data(config)["enabled"])


def _five_stack_timing(config: dict[str, Any], duration: float) -> tuple[float, float]:
    stack = _five_stack_data(config)
    requested_start = stack["startSeconds"]
    start = requested_start if requested_start is not None else round(duration * 0.28, 2)
    start = min(max(0.5, start), max(0.5, duration - 0.5))
    requested_duration = stack["durationSeconds"]
    visible_for = min(max(1.0, requested_duration), max(0.5, duration - start))
    return start, visible_for


def _claude_midnight_data(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize all v2 Claude models while preserving backward compatibility."""
    raw_models = config.get("claudeInserts")
    raw_models = raw_models if isinstance(raw_models, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, defaults in CLAUDE_MIDNIGHT_MODELS.items():
        raw = raw_models.get(key)
        raw = raw if isinstance(raw, dict) else {}
        raw_fields = raw.get("fields") if isinstance(raw.get("fields"), list) else []
        fields = [
            re.sub(r"\s+", " ", str(raw_fields[index] if index < len(raw_fields) else fallback)).strip()[:190]
            or fallback
            for index, fallback in enumerate(defaults["fields"])
        ]
        raw_start = raw.get("startSeconds")
        raw_duration = raw.get("durationSeconds")
        normalized[key] = {
            "enabled": bool(config.get("manualVisualsEnabled")) and bool(raw.get("enabled")),
            "startSeconds": float(raw_start) if isinstance(raw_start, (int, float)) else None,
            "durationSeconds": min(
                8.0,
                max(1.0, float(raw_duration if isinstance(raw_duration, (int, float)) else defaults["duration"])),
            ),
            "fields": fields,
        }
    return normalized


def _claude_midnight_timing(
    key: str,
    model: dict[str, Any],
    duration: float,
) -> tuple[float, float]:
    defaults = CLAUDE_MIDNIGHT_MODELS[key]
    requested_start = model.get("startSeconds")
    start = (
        float(requested_start)
        if isinstance(requested_start, (int, float))
        else round(duration * float(defaults["startRatio"]), 2)
    )
    start = min(max(0.5, start), max(0.5, duration - 0.5))
    visible_for = min(
        max(1.0, float(model.get("durationSeconds") or defaults["duration"])),
        max(0.5, duration - start),
    )
    return start, visible_for


def _claude_midnight_model_document(key: str, fields: list[str], base: str) -> str:
    """Build each transparent Midnight Glass overlay from the Claude reference."""
    safe = [html.escape(value) for value in fields]
    if key == "numberGlass":
        label, value, support, detail = safe
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
          body{{position:relative;background:transparent}}.stack{{position:absolute;left:90px;right:90px;bottom:250px;display:flex;flex-direction:column;align-items:flex-start;gap:20px}}
          .tag{{display:flex;align-items:center;gap:14px;padding:12px 20px;background:rgba(8,24,28,.55);border:1px solid rgba(111,227,210,.35);color:#6fe3d2;font-size:26px;font-weight:800;letter-spacing:.23em}}
          .dot{{width:12px;height:12px;background:#6fe3d2}}.number{{color:#ffb84d;font-size:220px;font-weight:800;letter-spacing:-.07em;line-height:.82;text-shadow:0 20px 60px rgba(0,0,0,.55)}}
          .line{{width:100%;height:4px;background:linear-gradient(90deg,#6fe3d2,rgba(111,227,210,0))}}.copy{{max-width:840px;border-left:3px solid rgba(111,227,210,.7);padding:18px 24px;background:rgba(8,24,28,.50)}}
          .support{{font-size:42px;line-height:1.2;font-weight:600;color:#eef4f5}}.detail{{padding-top:8px;color:rgba(238,244,245,.6);font-size:26px;letter-spacing:.06em}}
        </style></head><body><div class='stack'><div class='tag'><span class='dot'></span>{label}</div><div class='number'>{value}</div><div class='line'></div><div class='copy'><div class='support'>{support}</div><div class='detail'>{detail}</div></div></div></body></html>"""
    if key == "editorialClip":
        masthead, issue, headline, body, footnote = safe
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
          body{{position:relative;background:transparent}}.card{{position:absolute;left:90px;bottom:180px;width:620px;background:rgba(8,24,28,.62);border:1px solid rgba(238,244,245,.16);box-shadow:0 32px 80px rgba(0,0,0,.5)}}
          .rule{{height:4px;background:linear-gradient(90deg,#6fe3d2,rgba(111,227,210,0))}}.inner{{padding:30px 32px 34px;display:flex;flex-direction:column;gap:18px}}
          .meta{{display:flex;justify-content:space-between;gap:20px;color:rgba(238,244,245,.55);font-size:22px;font-weight:800;letter-spacing:.20em}}.issue{{color:#6fe3d2}}h1{{margin:0;font-size:64px;line-height:1;font-weight:800;letter-spacing:-.04em}}p{{margin:0;color:rgba(238,244,245,.72);font-size:30px;line-height:1.34}}.foot{{border-top:1px solid rgba(238,244,245,.18);padding-top:18px;color:rgba(238,244,245,.5);font-size:22px;letter-spacing:.08em}}
        </style></head><body><article class='card'><div class='rule'></div><div class='inner'><div class='meta'><span>{masthead}</span><span class='issue'>{issue}</span></div><h1>{headline}</h1><p>{body}</p><div class='foot'>{footnote}</div></div></article></body></html>"""
    if key == "mechanismBars":
        label, first, second, footnote = safe
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
          body{{position:relative;background:transparent}}.stack{{position:absolute;left:90px;right:90px;bottom:260px;display:flex;flex-direction:column;gap:28px}}
          .label{{color:#6fe3d2;font-size:30px;font-weight:800;letter-spacing:.23em}}.group{{display:flex;flex-direction:column;gap:14px}}.caption{{font-size:30px;font-weight:600;color:rgba(238,244,245,.7)}}.caption.strong{{color:#eef4f5;font-weight:800}}.bar{{height:60px;border:1px solid rgba(238,244,245,.28);background:rgba(238,244,245,.18)}}.bar.short{{width:46%}}.bar.long{{width:100%;border:0;background:linear-gradient(90deg,#0e6b63,#6fe3d2);box-shadow:0 12px 40px rgba(111,227,210,.28)}}.foot{{color:rgba(238,244,245,.5);font-size:24px}}
        </style></head><body><div class='stack'><div class='label'>{label}</div><div class='group'><div class='caption'>{first}</div><div class='bar short'></div></div><div class='group'><div class='caption strong'>{second}</div><div class='bar long'></div></div><div class='foot'>{footnote}</div></div></body></html>"""
    if key == "evidenceStamp":
        kicker, badge, headline, preclinical, phase1, phase2, phase3, approved, support = safe
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
          body{{position:relative;background:transparent}}.card{{position:absolute;left:90px;right:90px;bottom:160px;background:rgba(8,24,28,.62);border:1px solid rgba(238,244,245,.16);box-shadow:0 32px 80px rgba(0,0,0,.5)}}.header{{display:flex;justify-content:space-between;gap:20px;padding:18px 26px;border-bottom:1px solid rgba(238,244,245,.16);color:rgba(238,244,245,.6);font-size:24px;font-weight:800;letter-spacing:.18em}}.badge{{color:#6fe3d2}}.inner{{padding:28px 26px 32px;display:flex;flex-direction:column;gap:22px}}h1{{margin:0;color:#eef4f5;font-size:52px;line-height:1.04;font-weight:800;letter-spacing:-.03em}}.phases{{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}}.phase{{padding:14px 8px;background:#6fe3d2;color:#07100f;font-size:18px;font-weight:900;letter-spacing:.05em}}.phase.pending{{padding:13px 8px;background:rgba(238,244,245,.08);border:1px solid rgba(238,244,245,.2);color:rgba(238,244,245,.45)}}.support{{color:rgba(238,244,245,.72);font-size:28px;line-height:1.34}}
        </style></head><body><article class='card'><div class='header'><span>{kicker}</span><span class='badge'>{badge}</span></div><div class='inner'><h1>{headline}</h1><div class='phases'><div class='phase'>{preclinical}</div><div class='phase'>{phase1}</div><div class='phase'>{phase2}</div><div class='phase pending'>{phase3}</div><div class='phase pending'>{approved}</div></div><div class='support'>{support}</div></div></article></body></html>"""
    if key == "glossarySource":
        eyebrow, term, definition, source_label, source, source_note = safe
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
          body{{position:relative;background:transparent}}.glossary{{position:absolute;left:90px;top:150px;width:600px;padding:26px 28px 30px;background:rgba(8,24,28,.60);border:1px solid rgba(238,244,245,.16);box-shadow:0 24px 64px rgba(0,0,0,.32)}}.eyebrow{{color:#6fe3d2;font-size:22px;font-weight:800;letter-spacing:.24em}}h1{{margin:12px 0 0;color:#eef4f5;font-size:64px;line-height:1;font-weight:800;letter-spacing:-.04em}}p{{margin:12px 0 0;color:rgba(238,244,245,.72);font-size:28px;line-height:1.34}}.source{{position:absolute;left:90px;bottom:90px;display:flex;align-items:stretch;box-shadow:0 18px 46px rgba(0,0,0,.25)}}.source-label{{padding:14px 16px;background:#6fe3d2;color:#07100f;font-size:22px;font-weight:900;letter-spacing:.16em}}.source-copy{{padding:12px 20px;background:rgba(8,24,28,.62);border:1px solid rgba(238,244,245,.16);border-left:0}}.source-copy strong{{display:block;color:#eef4f5;font-size:24px}}.source-copy span{{display:block;margin-top:2px;color:rgba(238,244,245,.55);font-size:20px}}
        </style></head><body><article class='glossary'><div class='eyebrow'>{eyebrow}</div><h1>{term}</h1><p>{definition}</p></article><div class='source'><div class='source-label'>{source_label}</div><div class='source-copy'><strong>{source}</strong><span>{source_note}</span></div></div></body></html>"""
    raise ValueError(f"Modelo Claude desconhecido: {key}")


def _kit_documents(config: dict[str, Any], project_root: Path) -> dict[str, tuple[str, bool]]:
    archivo = project_root / "assets" / "fonts" / "archivo" / "archivo-latin-wght-normal.woff2"
    instrument = (
        project_root
        / "assets"
        / "fonts"
        / "instrument-serif"
        / "instrument-serif-latin-400-italic.woff2"
    )
    if not archivo.is_file() or not instrument.is_file():
        raise RuntimeError("As fontes locais do kit gráfico não foram encontradas.")
    fonts = _font_face("ArchivoLocal", archivo, weight="100 900") + _font_face(
        "InstrumentLocal", instrument, style="italic"
    )
    accent = str(config.get("accent") or "#c8e05a")
    if not ACCENT_PATTERN.fullmatch(accent):
        accent = "#c8e05a"
    name = _config_text(config, "name", "Dr. Guilherme Martins", 80)
    role = _config_text(config, "role", "Médico", 90)
    title = _config_text(config, "title", "Saúde e desempenho", 120)
    subtitle = _config_text(
        config,
        "subtitle",
        "Informação clara, direto ao ponto.",
        150,
    )
    section_title = _safe_text(config.get("sectionTitle"), "", 100)
    medical_disclaimer = html.escape(MEDICAL_EDUCATIONAL_DISCLAIMER)
    medical_identification = html.escape(MEDICAL_PROFESSIONAL_IDENTIFICATION)
    base = f"""
      {fonts}
      *{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden}}
      body{{font-family:'ArchivoLocal',Arial,sans-serif;color:#f5f3ee}}
      .serif{{font-family:'InstrumentLocal',Georgia,serif;font-style:italic}}
    """
    opening_name = (
        f"<div class='name'><span class='dot'></span>{name}</div>" if name else ""
    )
    opening_title = f"<h1 class='serif'>{title}</h1>" if title else ""
    opening_subtitle = f"<p>{subtitle}</p>" if subtitle else ""
    lower_name = f"<h2>{name}</h2>" if name else ""
    lower_role = f"<p>{role}</p>" if role else ""
    cover_title = f"<h2 class='serif'>{title}</h2>" if title else ""
    cover_name = f"<div class='name'>{name}</div>" if name else ""
    opening = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;padding:180px 90px 520px;display:flex;flex-direction:column;justify-content:center}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(80% 50% at 50% 26%,rgba(255,255,255,.09),transparent 66%)}}
      .name{{position:absolute;top:180px;left:90px;display:flex;align-items:center;gap:18px;color:#a3a098;font-size:26px;font-weight:650;letter-spacing:.18em;text-transform:uppercase}}
      .dot{{width:14px;height:14px;border-radius:50%;background:{accent}}}.content{{position:relative}}
      .line{{width:220px;height:4px;background:{accent};margin-bottom:44px}}h1{{margin:0;font-size:132px;line-height:.94;font-weight:400;letter-spacing:-.025em;max-width:900px}}
      p{{margin:{"38px 0 0" if title else "0"};color:#aaa79f;font-size:42px;line-height:1.32;max-width:830px}}
    </style></head><body>{opening_name}<div class='content'><div class='line'></div>{opening_title}{opening_subtitle}</div></body></html>"""
    lower = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{background:transparent;position:relative}}.lower{{position:absolute;left:70px;bottom:570px;display:flex;filter:drop-shadow(0 20px 34px rgba(0,0,0,.34))}}
      .bar{{width:10px;background:{accent}}}.card{{min-width:690px;max-width:900px;background:rgba(15,15,16,.94);padding:32px 52px 34px 40px}}
      h2{{margin:0;font-size:58px;line-height:1.04;letter-spacing:-.02em}}p{{margin:{"12px 0 0" if name else "0"};color:{accent};font-size:29px;line-height:1.25;letter-spacing:.045em}}
    </style></head><body><div class='lower'><div class='bar'></div><div class='card'>{lower_name}{lower_role}</div></div></body></html>"""
    section = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{background:{accent};color:#0f0f10;display:flex;align-items:center;justify-content:center;padding:120px 90px 520px;text-align:center}}
      h2{{margin:0;font-size:118px;line-height:.98;font-weight:400;letter-spacing:-.02em;max-width:920px}}
    </style></head><body><main><h2 class='serif'>{section_title}</h2></main></body></html>"""
    outro = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;display:flex;align-items:center;justify-content:center;padding:150px 90px 500px;text-align:left}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(70% 42% at 50% 34%,rgba(255,255,255,.08),transparent 67%)}}
      main{{position:relative;width:100%;max-width:900px;display:flex;flex-direction:column;align-items:flex-start;gap:34px}}
      .eyebrow{{color:{accent};font-size:25px;font-weight:800;letter-spacing:.22em;text-transform:uppercase}}
      .rule{{width:180px;height:5px;background:{accent}}}
      .notice{{max-width:900px;color:#f5f3ee;font-size:43px;line-height:1.42;font-weight:560;letter-spacing:-.018em}}
      .medical-id{{max-width:900px;padding-top:30px;border-top:1px solid rgba(245,243,238,.24);color:#d7d4cd;font-size:31px;line-height:1.48;font-weight:700;letter-spacing:-.012em}}
    </style></head><body><main><div class='eyebrow'>Informação médica</div><div class='rule'></div><div class='notice'>{medical_disclaimer}</div><div class='medical-id'>{medical_identification}</div></main></body></html>"""
    cover = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;padding:170px 90px 520px;display:flex;flex-direction:column;justify-content:flex-end}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 72% 20%,rgba(200,224,90,.2),transparent 36%),repeating-linear-gradient(135deg,#19191b 0 14px,#121214 14px 28px)}}
      main{{position:relative}}.line{{height:4px;width:170px;background:{accent};margin-bottom:34px}}h2{{margin:0;font-size:108px;line-height:.95;font-weight:400;letter-spacing:-.025em}}
      .name{{margin-top:30px;color:{accent};font-size:28px;letter-spacing:.15em;text-transform:uppercase;font-weight:700}}
    </style></head><body><main><div class='line'></div>{cover_title}{cover_name}</main></body></html>"""
    documents: dict[str, tuple[str, bool]] = {
        "opening": (opening, False),
        "lowerThird": (lower, True),
        "section": (section, False),
        "outro": (outro, False),
        "cover": (cover, False),
    }
    stack = _five_stack_data(config)
    if stack["enabled"]:
        for index, line in enumerate(stack["lines"], start=1):
            top = 430 + (index - 1) * 154
            is_amber = index == 5
            is_muted = index == 4
            accent_color = "#ffb84d" if is_amber else "#6fe3d2"
            border = "rgba(255,184,77,.50)" if is_amber else "rgba(238,244,245,.14)"
            body_color = "#eef4f5" if not is_muted else "rgba(238,244,245,.72)"
            number_color = accent_color if not is_muted else "rgba(238,244,245,.5)"
            row = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
              body{{position:relative;background:transparent}}
              .row{{position:absolute;right:90px;top:{top}px;width:660px;min-height:130px;display:flex;align-items:center;gap:20px;
                padding:22px 26px;background:rgba(8,24,28,.55);border:1px solid {border};border-left:3px solid {accent_color};
                box-shadow:0 18px 44px rgba(0,0,0,.24)}}
              .number{{min-width:46px;color:{number_color};font-size:26px;font-weight:800;letter-spacing:.1em}}
              .copy{{color:{body_color};font-size:34px;line-height:1.2;font-weight:{700 if is_amber else 600};letter-spacing:-.015em}}
            </style></head><body><div class='row'><span class='number'>{index:02d}</span><span class='copy'>{html.escape(line)}</span></div></body></html>"""
            documents[f"fiveStackRow{index}"] = (row, True)
    for key, model in _claude_midnight_data(config).items():
        if model["enabled"]:
            documents[f"claude{key}"] = (
                _claude_midnight_model_document(key, model["fields"], base),
                True,
            )
    return documents


def render_kit_assets(
    config: dict[str, Any],
    destination: Path,
    *,
    project_root: Path,
) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    destination.mkdir(parents=True, exist_ok=True)
    documents = _kit_documents(config, project_root)
    rendered: dict[str, Path] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            for name, (document, transparent) in documents.items():
                path = destination / f"{name}.png"
                page.set_content(document, wait_until="load")
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(path), omit_background=transparent)
                rendered[name] = path
        finally:
            context.close()
            browser.close()
    return rendered


def render_medical_end_card(destination: Path, *, project_root: Path) -> Path:
    """Renderiza somente a cartela médica canônica usada pelos editores de vídeo."""
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    document, _transparent = _kit_documents({}, project_root)["outro"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            page.set_content(document, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(destination))
        finally:
            context.close()
            browser.close()
    return destination


def _detect_flat_horizontal_bars(source: Path, duration: float, ffmpeg: str) -> tuple[int, int] | None:
    """Detecta letterbox claro/escuro; retorna topo e altura do conteúdo real."""
    width, height = 270, 480
    process = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.1, duration * 0.48):.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:{height}",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    expected = width * height * 3
    if process.returncode != 0 or len(process.stdout) != expected:
        return None

    rows: list[tuple[float, float]] = []
    raw = process.stdout
    for y in range(height):
        values: list[int] = []
        offset = y * width * 3
        for x in range(0, width, 4):
            pixel = offset + x * 3
            values.extend(raw[pixel : pixel + 3])
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        rows.append((mean, math.sqrt(variance)))

    top_mean = sum(row[0] for row in rows[:12]) / 12
    bottom_mean = sum(row[0] for row in rows[-12:]) / 12
    top_flat = sum(row[1] for row in rows[:12]) / 12 < 8
    bottom_flat = sum(row[1] for row in rows[-12:]) / 12 < 8
    if not top_flat or not bottom_flat or abs(top_mean - bottom_mean) > 18:
        return None

    reference = (top_mean + bottom_mean) / 2
    active = [abs(mean - reference) > 10 or deviation > 12 for mean, deviation in rows]
    first = next((index for index in range(height - 3) if all(active[index : index + 3])), None)
    last = next(
        (index + 2 for index in range(height - 3, -1, -1) if all(active[index : index + 3])),
        None,
    )
    if first is None or last is None or last <= first:
        return None
    content_ratio = (last - first + 1) / height
    if not 0.25 <= content_ratio <= 0.9:
        return None
    scale = VIDEO_HEIGHT / height
    # Mantém apenas a área ativa. Expandir o recorte reintroduz uma linha da
    # letterbox original nas bordas superior e inferior do vídeo reenquadrado.
    top = max(0, round(first * scale))
    bottom = min(VIDEO_HEIGHT, round((last + 1) * scale))
    detected_height = bottom - top
    detected_height -= detected_height % 2
    return top, detected_height


def _section_timing(config: dict[str, Any], duration: float) -> tuple[float, float]:
    """Resolve o início e a duração da cartela dentro do vídeo disponível."""
    requested_start = config.get("sectionStartSeconds")
    topic_start = float(requested_start) if requested_start is not None else round(duration * 0.52, 2)
    topic_start = min(max(3.0, topic_start), max(3.0, duration - 0.5))

    requested_duration = config.get("sectionDurationSeconds")
    section_duration = float(requested_duration) if requested_duration is not None else 3.0
    section_duration = min(max(0.5, section_duration), max(0.5, duration - topic_start))
    return topic_start, section_duration


def _section_enabled(config: dict[str, Any]) -> bool:
    """Uma cartela sem conteúdo nunca deve existir no vídeo final."""
    return bool(
        config.get("includeSection", True)
        and re.sub(r"\s+", "", str(config.get("sectionTitle") or ""))
    )


def _section_transition(
    config: dict[str, Any],
    section_start: float,
    section_end: float,
) -> tuple[str, str]:
    """Monta a camada e a posição da cartela para a transição escolhida."""
    transition = str(config.get("sectionTransition") or "fade")
    if transition not in {"none", "fade", "slide_up"}:
        transition = "fade"
    section_duration = max(0.5, section_end - section_start)
    transition_duration = min(0.4, section_duration / 2)
    section_stream = "[3:v]format=rgba"
    if transition == "fade":
        section_stream += (
            f",fade=t=in:st={section_start:.3f}:d={transition_duration:.3f}:alpha=1"
            f",fade=t=out:st={max(section_start, section_end - transition_duration):.3f}:d={transition_duration:.3f}:alpha=1"
        )
    section_stream += "[section];"
    if transition == "slide_up":
        start_end = section_start + transition_duration
        end_start = max(start_end, section_end - transition_duration)
        overlay_position = (
            f"0:'if(lt(t,{start_end:.3f}),H*(1-(t-{section_start:.3f})/{transition_duration:.3f}),"
            f"if(gt(t,{end_start:.3f}),-H*(t-{end_start:.3f})/{transition_duration:.3f},0))'"
        )
    else:
        overlay_position = "0:0"
    return section_stream, overlay_position


def _outro_tail_seconds(config: dict[str, Any]) -> float:
    requested = config.get("outroTailSeconds")
    tail = float(requested) if requested is not None else 10.0
    return min(max(MEDICAL_MINIMUM_END_CARD_SECONDS, tail), 120.0)


def _motion_profile(
    config: dict[str, Any],
    duration: float,
    *,
    blocked_intervals: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Planeja punch-ins curtos sem competir com as cartelas de tópico."""
    preset = str(config.get("motionPreset") or "subtle")
    if preset not in {"none", "subtle", "social"}:
        preset = "subtle"
    settings = {
        "none": (1.0, 0.0, 0.0, 0.0, 0.0),
        "subtle": (1.14, 6.5, 9.8, 2.6, 0.7),
        "social": (1.22, 5.0, 6.5, 3.0, 0.55),
    }
    zoom, first_start, cadence, hold, ramp = settings[preset]
    intervals: list[tuple[float, float]] = []
    blocked = blocked_intervals or []
    cursor = first_start
    while cadence and cursor + hold <= max(0.0, duration - 0.8):
        end = cursor + hold
        overlaps = any(cursor < blocked_end and end > blocked_start for blocked_start, blocked_end in blocked)
        if not overlaps:
            intervals.append((round(cursor, 3), round(end, 3)))
        cursor += cadence
    return {
        "preset": preset,
        "zoom": zoom,
        "rampSeconds": ramp,
        "focusY": 0.43,
        "intervals": intervals,
    }


def _eased_zoom_expression(start: float, end: float, zoom: float, ramp: float) -> str:
    """Cria uma aproximação com easing cossenoidal, sem saltos de escala."""
    safe_ramp = min(max(0.1, ramp), max(0.1, (end - start) / 2))
    rise_end = start + safe_ramp
    fall_start = end - safe_ramp
    delta = zoom - 1.0
    return (
        f"if(between(it,{start:.3f},{rise_end:.3f}),"
        f"1+{delta:.6f}*(0.5-0.5*cos(PI*(it-{start:.3f})/{safe_ramp:.3f})),"
        f"if(between(it,{rise_end:.3f},{fall_start:.3f}),{zoom:.6f},"
        f"if(between(it,{fall_start:.3f},{end:.3f}),"
        f"1+{delta:.6f}*(0.5+0.5*cos(PI*(it-{fall_start:.3f})/{safe_ramp:.3f})),1)))"
    )


def _motion_filter(profile: dict[str, Any]) -> str:
    intervals = list(profile.get("intervals") or [])
    zoom = float(profile.get("zoom") or 1.0)
    if not intervals or zoom <= 1.0:
        return "[base_raw]null[base];"
    ramp = float(profile.get("rampSeconds") or 0.6)
    focus_y = min(0.55, max(0.35, float(profile.get("focusY") or 0.43)))
    zoom_expressions = [
        _eased_zoom_expression(float(start), float(end), zoom, ramp)
        for start, end in intervals
    ]
    zoom_expression = zoom_expressions[0]
    for expression in zoom_expressions[1:]:
        zoom_expression = f"max({zoom_expression},{expression})"
    return (
        f"[base_raw]zoompan=z='{zoom_expression}':"
        "x='iw/2-(iw/zoom/2)':"
        f"y='max(0,min(ih-ih/zoom,ih*{focus_y:.3f}-ih/(2*zoom)))':"
        f"d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}[base];"
    )


def _voice_filters(config: dict[str, Any]) -> str:
    if not config.get("enhanceVoice", True):
        return ""
    return (
        "highpass=f=75,lowpass=f=12000,"
        "acompressor=threshold=0.08:ratio=2.5:attack=20:release=220:makeup=1.15,"
        "alimiter=limit=0.95,"
    )


def _probe_has_audio(source: Path, ffmpeg: str) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe não está instalado.")
    process = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(source),
        ],
        timeout=30,
    )
    return bool(process.stdout.strip())


def _insert_visual_filter(
    inserts: list[dict[str, Any]],
    *,
    input_start: int,
    base_label: str = "base",
) -> tuple[str, str]:
    """Monta uma trilha de B-roll sem substituir o áudio do vídeo principal."""
    if not inserts:
        return "", base_label

    filters: list[str] = []
    previous = base_label
    for index, insert in enumerate(inserts):
        source_start = float(insert["sourceStartSeconds"])
        source_end = float(insert["sourceEndSeconds"])
        timeline_start = float(insert["timelineStartSeconds"])
        timeline_end = float(insert["timelineEndSeconds"])
        input_index = input_start + index
        prefix = f"insert_{index}"
        next_label = f"base_insert_{index}"
        filters.extend(
            [
                f"[{input_index}:v]trim=start={source_start:.3f}:end={source_end:.3f},"
                f"setpts=PTS-STARTPTS,split=2[{prefix}_bg0][{prefix}_fg0]",
                f"[{prefix}_bg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},gblur=sigma=34,"
                f"eq=brightness=-0.18:saturation=0.72[{prefix}_bg]",
                f"[{prefix}_fg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                f"force_original_aspect_ratio=decrease,setsar=1[{prefix}_fg]",
                f"[{prefix}_bg][{prefix}_fg]overlay=(W-w)/2:(H-h)/2:shortest=1,"
                f"setpts=PTS+{timeline_start:.3f}/TB[{prefix}_timed]",
                f"[{previous}][{prefix}_timed]overlay=0:0:eof_action=pass:repeatlast=0:"
                f"enable='between(t,{timeline_start:.3f},{timeline_end:.3f})'[{next_label}]",
            ]
        )
        previous = next_label
    return ";".join(filters) + ";", previous


def _five_stack_visual_filter(
    *,
    input_start: int,
    row_count: int,
    base_label: str,
    start: float,
    end: float,
) -> tuple[str, str]:
    """Overlay five transparent rows with the 0.1 s stagger from the reference."""
    if row_count <= 0 or end <= start:
        return "", base_label

    filters: list[str] = []
    previous = base_label
    for index in range(row_count):
        row_start = min(end - 0.05, start + index * 0.10)
        fade_out = max(row_start + 0.12, end - 0.22)
        stream = f"five_stack_{index}"
        output = f"base_five_stack_{index}"
        filters.extend(
            (
                f"[{input_start + index}:v]format=rgba,"
                f"fps={VIDEO_FPS},"
                f"fade=t=in:st={row_start:.3f}:d=0.28:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.22:alpha=1[{stream}]",
                f"[{previous}][{stream}]overlay=0:0:eof_action=pass:repeatlast=0:"
                f"enable='between(t,{row_start:.3f},{end:.3f})'[{output}]",
            )
        )
        previous = output
    return ";".join(filters) + ";", previous


def _claude_midnight_visual_filter(
    models: list[tuple[str, float, float]],
    *,
    input_start: int,
    base_label: str,
) -> tuple[str, str]:
    """Apply the remaining Midnight assets with a compact rise/fade entrance."""
    if not models:
        return "", base_label

    filters: list[str] = []
    previous = base_label
    for index, (key, start, end) in enumerate(models):
        fade_out = max(start + 0.25, end - 0.22)
        stream = f"claude_{key}"
        output = f"base_claude_{key}"
        filters.extend(
            (
                f"[{input_start + index}:v]format=rgba,"
                f"fps={VIDEO_FPS},"
                f"fade=t=in:st={start:.3f}:d=0.34:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.22:alpha=1[{stream}]",
                f"[{previous}][{stream}]overlay=x=0:y="
                f"'if(between(t,{start:.3f},{start + 0.34:.3f}),"
                f"18*(1-(t-{start:.3f})/0.34),0)':eof_action=pass:repeatlast=0:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{output}]",
            )
        )
        previous = output
    return ";".join(filters) + ";", previous


_GENERIC_VISUAL_TYPES = {
    "caption_emphasis",
    "kinetic_text",
    "progressive_list",
    "supporting_visual",
    "definition_card",
    "number_card",
    "comparison_card",
    "quote_card",
    "evidence_card",
    "cta_card",
}

_GENERIC_VISUAL_POSITIONS = {
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


def _generic_visual_events(config: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    """Valida eventos decididos pelo Claude antes de criar qualquer filtro."""
    normalized: list[dict[str, Any]] = []
    for raw in config.get("visualEvents") or []:
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        kind = str(raw.get("interactionType") or "none")
        if kind not in _GENERIC_VISUAL_TYPES:
            continue
        start = float(raw.get("startMs") or 0) / 1000
        end = float(raw.get("endMs") or 0) / 1000
        visible_for = end - start
        if start < 0 or end > duration + 0.25 or visible_for < 1.5 or visible_for > 5.5:
            raise RuntimeError(
                f"Visual '{raw.get('visualText') or kind}' precisa durar entre 1,5 e 5,5 segundos."
            )
        screen_position = str(raw.get("screenPosition") or "top_right")
        if screen_position not in _GENERIC_VISUAL_POSITIONS:
            screen_position = "top_right"
        background_color = str(raw.get("backgroundColor") or "#073e4b").strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", background_color):
            background_color = "#073e4b"
        try:
            background_opacity = float(raw.get("backgroundOpacity", 0.9))
        except (TypeError, ValueError):
            background_opacity = 0.9
        normalized.append(
            {
                **raw,
                "id": re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw.get("id") or kind))[:80],
                "interactionType": kind,
                "visualText": re.sub(r"\s+", " ", str(raw.get("visualText") or "")).strip()[:100],
                "screenPosition": screen_position,
                "backgroundColor": background_color,
                "backgroundOpacity": min(1.0, max(0.15, background_opacity)),
                "start": start,
                "end": end,
            }
        )
    normalized.sort(key=lambda event: (event["start"], event["end"]))
    return normalized[:6]


def _validate_visual_intervals(intervals: list[tuple[str, float, float]]) -> None:
    previous: tuple[str, float, float] | None = None
    for current in sorted(intervals, key=lambda item: (item[1], item[2])):
        if previous and current[1] < previous[2] - 0.12:
            raise RuntimeError(
                f"Os visuais '{previous[0]}' e '{current[0]}' se sobrepõem. "
                "Mantenha uma intervenção por vez."
            )
        previous = current


def _generic_visual_filter(
    events: list[dict[str, Any]],
    *,
    input_start: int,
    base_label: str,
) -> tuple[str, str]:
    if not events:
        return "", base_label
    filters: list[str] = []
    previous = base_label
    for index, event in enumerate(events):
        start = float(event["start"])
        end = float(event["end"])
        fade_out = max(start + 0.25, end - 0.22)
        stream = f"guided_visual_{index}"
        output = f"base_guided_visual_{index}"
        filters.extend(
            (
                f"[{input_start + index}:v]format=rgba,fps={VIDEO_FPS},"
                f"fade=t=in:st={start:.3f}:d=0.28:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.22:alpha=1[{stream}]",
                f"[{previous}][{stream}]overlay=0:0:eof_action=pass:repeatlast=0:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{output}]",
            )
        )
        previous = output
    return ";".join(filters) + ";", previous


def render_local_kit_video(
    source: Path,
    output: Path,
    workdir: Path,
    config: dict[str, Any],
    *,
    project_root: Path,
    music_path: Path | None = None,
    insert_sources: dict[str, Path] | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não está instalado.")
    duration = probe_duration(source)
    progress = on_progress or (lambda _value, _stage: None)
    generic_events = _generic_visual_events(config, duration)
    has_audio = _probe_has_audio(source, ffmpeg)
    captions: list[dict[str, Any]] = []
    transcript_reused = False
    if config.get("includeCaptions", True) and has_audio:
        transcript_path = workdir / "transcript.json"
        if transcript_path.is_file():
            try:
                transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                transcript_reused = True
                progress(8, "Usando transcrição pronta para sincronizar legendas")
            except (OSError, json.JSONDecodeError):
                progress(8, "Transcrevendo e sincronizando legendas")
                transcript = transcribe_video_to_file(
                    source,
                    transcript_path,
                    project_root=project_root,
                )
        else:
            progress(8, "Transcrevendo e sincronizando legendas")
            transcript = transcribe_video_to_file(
                source,
                transcript_path,
                project_root=project_root,
            )
        progress(22, "Desenhando legendas no estilo escolhido")
        captions = render_caption_assets(
            transcript,
            config,
            workdir / "captions",
            duration_seconds=duration,
        )
    progress(30, "Criando peças gráficas")
    assets = render_kit_assets(config, workdir / "assets", project_root=project_root)
    for index, event in enumerate(generic_events, start=1):
        event["path"] = render_overlay(
            event,
            workdir / "assets" / f"guided-visual-{index:02d}.png",
        )
    progress(42, "Ajustando o enquadramento vertical")
    crop = _detect_flat_horizontal_bars(source, duration, ffmpeg)

    include_section = _section_enabled(config)
    topic_start, section_duration = _section_timing(config, duration)
    section_end = min(duration, topic_start + section_duration)
    section_stream, section_position = _section_transition(config, topic_start, section_end)
    include_five_stack = _five_stack_enabled(config)
    five_stack_start, five_stack_duration = _five_stack_timing(config, duration)
    five_stack_end = min(duration, five_stack_start + five_stack_duration)
    claude_models = _claude_midnight_data(config)
    active_claude_models: list[tuple[str, float, float]] = []
    for key, model in claude_models.items():
        if not model["enabled"]:
            continue
        model_start, model_duration = _claude_midnight_timing(key, model, duration)
        active_claude_models.append(
            (key, model_start, min(duration, model_start + model_duration))
        )
    blocked_intervals: list[tuple[float, float]] = []
    if include_section:
        blocked_intervals.append((topic_start, section_end))
    if include_five_stack:
        blocked_intervals.append((five_stack_start, five_stack_end))
    blocked_intervals.extend(
        (model_start, model_end)
        for _key, model_start, model_end in active_claude_models
    )
    blocked_intervals.extend(
        (float(event["start"]), float(event["end"]))
        for event in generic_events
    )
    visual_intervals: list[tuple[str, float, float]] = []
    if include_section:
        visual_intervals.append(("Cartela de tópico", topic_start, section_end))
    if include_five_stack:
        visual_intervals.append(("Lista em 5 pontos", five_stack_start, five_stack_end))
    visual_intervals.extend(
        (CLAUDE_MIDNIGHT_MODELS[key].get("fields", (key,))[0], start, end)
        for key, start, end in active_claude_models
    )
    visual_intervals.extend(
        (str(event.get("visualText") or event["interactionType"]), event["start"], event["end"])
        for event in generic_events
    )
    _validate_visual_intervals(visual_intervals)
    motion_profile = _motion_profile(
        config,
        duration,
        blocked_intervals=blocked_intervals,
    )
    # A cartela final é a peça de identificação obrigatória do editor local.
    outro_tail = max(MEDICAL_MINIMUM_END_CARD_SECONDS, _outro_tail_seconds(config))
    expected_duration = duration + outro_tail
    caption_timeline = (
        write_caption_timeline(
            captions,
            workdir / "captions",
            total_duration=expected_duration,
        )
        if captions
        else None
    )
    runtime_inserts: list[dict[str, Any]] = []
    available_insert_sources = insert_sources or {}
    for raw_insert in config.get("inserts") or []:
        if not isinstance(raw_insert, dict):
            continue
        upload_id = str(raw_insert.get("uploadId") or "")
        insert_path = available_insert_sources.get(upload_id)
        if not insert_path or not insert_path.is_file():
            raise RuntimeError(f"O clipe de insert {upload_id or 'sem ID'} não foi encontrado.")
        runtime_inserts.append({**raw_insert, "path": insert_path})
    lower_start = min(2.1, max(0.0, duration - 5.0))
    lower_end = min(duration, lower_start + 4.0)
    opening_end = min(duration, 2.0)
    opening_enable = f"between(t,0,{opening_end:.3f})" if config.get("includeOpening", True) else "0"
    lower_enable = (
        f"between(t,{lower_start:.3f},{lower_end:.3f})"
        if config.get("includeLowerThird", True)
        else "0"
    )
    section_enable = (
        f"between(t,{topic_start:.3f},{section_end:.3f})"
        if include_section
        else "0"
    )
    outro_enable = f"between(t,{duration:.3f},{expected_duration:.3f})" if outro_tail else "0"

    if crop:
        top, crop_height = crop
        source_filter = (
            f"[0:v]crop={VIDEO_WIDTH}:{crop_height}:0:{top},split=2[bg0][fg0];"
        )
    else:
        source_filter = "[0:v]split=2[bg0][fg0];"
    caption_input_start = 5 + (1 if music_path else 0)
    insert_input_start = caption_input_start + (1 if caption_timeline else 0)
    insert_filter, insert_base_label = _insert_visual_filter(
        runtime_inserts,
        input_start=insert_input_start,
    )
    five_stack_input_start = insert_input_start + len(runtime_inserts)
    five_stack_filter, graphics_base_label = _five_stack_visual_filter(
        input_start=five_stack_input_start,
        row_count=5 if include_five_stack else 0,
        base_label=insert_base_label,
        start=five_stack_start,
        end=five_stack_end,
    )
    claude_model_input_start = five_stack_input_start + (5 if include_five_stack else 0)
    claude_model_filter, graphics_base_label = _claude_midnight_visual_filter(
        active_claude_models,
        input_start=claude_model_input_start,
        base_label=graphics_base_label,
    )
    generic_visual_input_start = claude_model_input_start + len(active_claude_models)
    generic_visual_filter, graphics_base_label = _generic_visual_filter(
        generic_events,
        input_start=generic_visual_input_start,
        base_label=graphics_base_label,
    )
    filter_complex = (
        source_filter
        + f"[bg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},gblur=sigma=34,eq=brightness=-0.18:saturation=0.72[bg];"
        f"[fg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[base_raw];"
        + _motion_filter(motion_profile)
        + insert_filter
        + five_stack_filter
        + claude_model_filter
        + generic_visual_filter
        + "[1:v]format=rgba[opening];[2:v]format=rgba[lower];"
        + section_stream
        + "[4:v]format=rgba[outro];"
        f"[{graphics_base_label}][opening]overlay=0:0:enable='{opening_enable}'[v1];"
        f"[v1][lower]overlay=0:0:enable='{lower_enable}'[v2];"
        f"[v2][section]overlay={section_position}:enable='{section_enable}'[v3];"
        f"[v3]tpad=stop_mode=clone:stop_duration={outro_tail:.3f}[extended];"
        f"[extended][outro]overlay=0:0:enable='{outro_enable}'[video_base]"
    )
    video_map = "[video_base]"
    if caption_timeline:
        enable_terms = [f"between(t,0,{duration:.3f})"]
        if config.get("includeOpening", True) and opening_end:
            enable_terms.append(f"not(between(t,0,{opening_end:.3f}))")
        enable_terms.extend(
            f"not(between(t,{start:.3f},{end:.3f}))"
            for start, end in blocked_intervals
        )
        caption_enable = "*".join(enable_terms)
        filter_complex += (
            f";[{caption_input_start}:v]format=rgba[caption_track];"
            "[video_base][caption_track]overlay=0:0:eof_action=pass:repeatlast=1:"
            f"enable='{caption_enable}'[captioned]"
        )
        video_map = "[captioned]"

    voice_filters = _voice_filters(config)
    audio_map: str | None = "0:a?" if has_audio and not music_path and not outro_tail else None
    audio_codec = "copy"
    if music_path:
        music_volume = min(0.25, max(0.03, float(config.get("musicVolume") or 0.12)))
        music_fade_out_start = max(0.0, expected_duration - 1.2)
        if has_audio and config.get("duckMusicDuringSpeech", True):
            filter_complex += (
                f";[0:a]{voice_filters}asplit=2[voice_raw][sidechain_raw];"
                f"[voice_raw]apad=pad_dur={outro_tail:.3f},"
                f"atrim=duration={expected_duration:.3f}[original];"
                f"[sidechain_raw]apad=pad_dur={outro_tail:.3f},"
                f"atrim=duration={expected_duration:.3f},highpass=f=90,lowpass=f=6000[speech];"
                f"[5:a]atrim=duration={expected_duration:.3f},"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={music_fade_out_start:.3f}:d=1.2,"
                f"volume={music_volume:.3f}[music_base];"
                "[music_base][speech]sidechaincompress="
                "threshold=0.018:ratio=8:attack=20:release=450[music];"
                "[original][music]amix=inputs=2:duration=longest:normalize=0[audio]"
            )
        else:
            filter_complex += (
                f";[5:a]atrim=duration={expected_duration:.3f},"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={music_fade_out_start:.3f}:d=1.2,"
                f"volume={music_volume:.3f}[music];"
                + (
                    f"[0:a]{voice_filters}apad=pad_dur={outro_tail:.3f},"
                    f"atrim=duration={expected_duration:.3f}[original];"
                    "[original][music]amix=inputs=2:duration=longest:normalize=0[audio]"
                    if has_audio
                    else "[music]anull[audio]"
                )
            )
        audio_map = "[audio]"
        audio_codec = "aac"
    elif has_audio and outro_tail:
        filter_complex += (
            f";[0:a]{voice_filters}apad=pad_dur={outro_tail:.3f},"
            f"atrim=duration={expected_duration:.3f}[audio]"
        )
        audio_map = "[audio]"
        audio_codec = "aac"
    elif has_audio and voice_filters:
        filter_complex += f";[0:a]{voice_filters}anull[audio]"
        audio_map = "[audio]"
        audio_codec = "aac"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.part.mp4")
    progress(55, "Aplicando ritmo e acabamento ao vídeo")
    input_duration = f"{expected_duration:.6f}"

    def still_input(path: Path, *, frame_rate: int = 1) -> list[str]:
        # Entradas finitas evitam que o FFmpeg permaneça aguardando imagens em
        # loop depois de já ter produzido o último quadro do vídeo.
        return [
            "-loop",
            "1",
            "-framerate",
            str(frame_rate),
            "-t",
            input_duration,
            "-i",
            str(path),
        ]

    five_stack_inputs = (
        [
            argument
            for index in range(1, 6)
            for argument in still_input(assets[f"fiveStackRow{index}"])
        ]
        if include_five_stack
        else []
    )
    claude_model_inputs = [
        argument
        for key, _start, _end in active_claude_models
        for argument in still_input(assets[f"claude{key}"])
    ]
    generic_visual_inputs = [
        argument
        for event in generic_events
        for argument in still_input(Path(event["path"]))
    ]
    ffmpeg_args = [
            ffmpeg,
            "-y",
            "-filter_complex_threads",
            "2",
            "-i",
            str(source),
            *still_input(assets["opening"]),
            *still_input(assets["lowerThird"]),
            *still_input(assets["section"]),
            *still_input(assets["outro"]),
            *(
                ["-stream_loop", "-1", "-t", input_duration, "-i", str(music_path)]
                if music_path
                else []
            ),
            *(
                ["-f", "concat", "-safe", "0", "-i", str(caption_timeline)]
                if caption_timeline
                else []
            ),
            *[
                argument
                for insert in runtime_inserts
                for argument in ("-i", str(insert["path"]))
            ],
            *five_stack_inputs,
            *claude_model_inputs,
            *generic_visual_inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            video_map,
    ]
    if audio_map:
        ffmpeg_args.extend(["-map", audio_map])
    ffmpeg_args.extend([
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            audio_codec,
            "-t",
            f"{expected_duration:.6f}",
            str(temporary),
        ])
    _run_ffmpeg_with_progress(
        ffmpeg_args,
        expected_duration=expected_duration,
        output_path=temporary,
        on_progress=progress,
    )
    temporary.replace(output)
    progress(96, "Validando o MP4 final")
    final_duration_probe = probe_duration(output)
    if abs(final_duration_probe - expected_duration) > 0.2:
        raise RuntimeError("A duração do vídeo final divergiu do original.")
    manifest = {
        "schemaVersion": "local-video-kit-v1",
        "sourceDuration": round(duration, 3),
        "outputDuration": round(final_duration_probe, 3),
        "outputPath": str(output),
        "coverPath": str(assets["cover"]),
        "detectedContentCrop": (
            {"top": crop[0], "height": crop[1]} if crop else None
        ),
        "events": [
            {"kind": "opening", "enabled": config.get("includeOpening", True), "start": 0, "end": round(opening_end, 3)},
            {"kind": "lowerThird", "enabled": config.get("includeLowerThird", True), "start": round(lower_start, 3), "end": round(lower_end, 3)},
            {"kind": "section", "enabled": include_section, "start": round(topic_start, 3), "end": round(section_end, 3)},
            {
                "kind": "claudeFiveStack",
                "enabled": include_five_stack,
                "start": round(five_stack_start, 3),
                "end": round(five_stack_end, 3),
            },
            *[
                {
                    "kind": f"claude:{key}",
                    "enabled": True,
                    "start": round(start, 3),
                    "end": round(end, 3),
                }
                for key, start, end in active_claude_models
            ],
            *[
                {
                    "kind": f"guided:{event['interactionType']}",
                    "enabled": True,
                    "start": round(float(event["start"]), 3),
                    "end": round(float(event["end"]), 3),
                    "text": str(event.get("visualText") or ""),
                    "reason": str(event.get("reason") or ""),
                    "confidence": float(event.get("confidence") or 0),
                    "screenPosition": str(event.get("screenPosition") or "top_right"),
                    "backgroundColor": str(event.get("backgroundColor") or "#073e4b"),
                    "backgroundOpacity": float(event.get("backgroundOpacity") or 0.9),
                }
                for event in generic_events
            ],
            {"kind": "outro", "enabled": True, "start": round(duration, 3), "end": round(expected_duration, 3)},
        ],
        "inserts": [
            {
                "id": str(insert.get("id") or ""),
                "uploadId": str(insert.get("uploadId") or ""),
                "sourceName": str(insert.get("sourceName") or "Clipe de apoio"),
                "timelineStartSeconds": round(float(insert["timelineStartSeconds"]), 3),
                "timelineEndSeconds": round(float(insert["timelineEndSeconds"]), 3),
                "sourceStartSeconds": round(float(insert["sourceStartSeconds"]), 3),
                "sourceEndSeconds": round(float(insert["sourceEndSeconds"]), 3),
            }
            for insert in runtime_inserts
        ],
        "sectionTransition": str(config.get("sectionTransition") or "fade"),
        "backgroundMusic": {
            "enabled": bool(music_path),
            "trackId": config.get("musicTrackId") if music_path else None,
            "volume": round(float(config.get("musicVolume") or 0.12), 3) if music_path else 0,
            "duckedDuringSpeech": bool(
                music_path and has_audio and config.get("duckMusicDuringSpeech", True)
            ),
        },
        "captions": {
            "enabled": bool(captions),
            "requested": bool(config.get("includeCaptions", True)),
            "cueCount": len(captions),
            "style": str(config.get("captionStyle") or "dynamic"),
            "position": str(config.get("captionPosition") or "safe_bottom"),
            "highlightKeywords": bool(config.get("highlightKeywords", True)),
            "engine": "faster-whisper-local",
            "transcriptReused": transcript_reused,
        },
        "motion": {
            "preset": motion_profile["preset"],
            "zoom": motion_profile["zoom"],
            "rampSeconds": motion_profile["rampSeconds"],
            "focus": "face-upper-center",
            "intervals": [
                {"start": start, "end": end}
                for start, end in motion_profile["intervals"]
            ],
        },
        "voiceEnhancement": {
            "enabled": bool(has_audio and config.get("enhanceVoice", True)),
            "chain": "highpass+compressor+limiter" if has_audio and voice_filters else None,
        },
        "externalCreditsUsed": False,
    }
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    progress(100, "Vídeo pronto")
    return manifest
