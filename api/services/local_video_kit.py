"""Renderiza e aplica o kit gráfico vertical sem APIs ou créditos externos."""
from __future__ import annotations

import base64
import html
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
ACCENT_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


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
    name = _safe_text(config.get("name"), "Dr. Guilherme Martins", 80)
    role = _safe_text(config.get("role"), "Médico", 90)
    title = _safe_text(config.get("title"), "Saúde e desempenho", 120)
    subtitle = _safe_text(config.get("subtitle"), "Informação clara, direto ao ponto.", 150)
    section_number = _safe_text(config.get("sectionNumber"), "Ponto 01", 30)
    section_title = _safe_text(config.get("sectionTitle"), "O que realmente ajuda", 100)
    cta = _safe_text(config.get("cta"), "Quer mais dicas?", 90)
    site = _safe_text(config.get("site"), "@drguilhermemartins", 80)
    base = f"""
      {fonts}
      *{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden}}
      body{{font-family:'ArchivoLocal',Arial,sans-serif;color:#f5f3ee}}
      .serif{{font-family:'InstrumentLocal',Georgia,serif;font-style:italic}}
    """
    opening = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;padding:180px 90px 520px;display:flex;flex-direction:column;justify-content:center}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(80% 50% at 50% 26%,rgba(255,255,255,.09),transparent 66%)}}
      .name{{position:absolute;top:180px;left:90px;display:flex;align-items:center;gap:18px;color:#a3a098;font-size:26px;font-weight:650;letter-spacing:.18em;text-transform:uppercase}}
      .dot{{width:14px;height:14px;border-radius:50%;background:{accent}}}.content{{position:relative}}
      .line{{width:220px;height:4px;background:{accent};margin-bottom:44px}}h1{{margin:0;font-size:132px;line-height:.94;font-weight:400;letter-spacing:-.025em;max-width:900px}}
      p{{margin:38px 0 0;color:#aaa79f;font-size:42px;line-height:1.32;max-width:830px}}
    </style></head><body><div class='name'><span class='dot'></span>{name}</div><div class='content'><div class='line'></div><h1 class='serif'>{title}</h1><p>{subtitle}</p></div></body></html>"""
    lower = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{background:transparent;position:relative}}.lower{{position:absolute;left:70px;bottom:570px;display:flex;filter:drop-shadow(0 20px 34px rgba(0,0,0,.34))}}
      .bar{{width:10px;background:{accent}}}.card{{min-width:690px;max-width:900px;background:rgba(15,15,16,.94);padding:32px 52px 34px 40px}}
      h2{{margin:0;font-size:58px;line-height:1.04;letter-spacing:-.02em}}p{{margin:12px 0 0;color:{accent};font-size:29px;line-height:1.25;letter-spacing:.045em}}
    </style></head><body><div class='lower'><div class='bar'></div><div class='card'><h2>{name}</h2><p>{role}</p></div></div></body></html>"""
    section = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{background:{accent};color:#0f0f10;display:flex;align-items:center;justify-content:center;padding:120px 90px 520px;text-align:center}}
      .number{{font-size:27px;letter-spacing:.3em;text-transform:uppercase;color:rgba(15,15,16,.58);font-weight:700;margin-bottom:30px}}
      h2{{margin:0;font-size:118px;line-height:.98;font-weight:400;letter-spacing:-.02em;max-width:920px}}
    </style></head><body><main><div class='number'>{section_number}</div><h2 class='serif'>{section_title}</h2></main></body></html>"""
    outro = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;display:flex;align-items:center;justify-content:center;padding:120px 90px 520px;text-align:center}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(70% 42% at 50% 38%,rgba(255,255,255,.08),transparent 67%)}}
      main{{position:relative;display:flex;flex-direction:column;align-items:center;gap:46px}}h2{{margin:0;font-size:104px;line-height:1;font-weight:400}}
      .site{{border:2px solid {accent};padding:26px 46px;font-size:38px;font-weight:650}}.site span{{color:{accent};margin-right:16px}}
      .name{{color:#68665f;font-size:25px;letter-spacing:.2em;text-transform:uppercase;font-weight:700}}
    </style></head><body><main><h2 class='serif'>{cta}</h2><div class='site'><span>●</span>{site}</div><div class='name'>{name}</div></main></body></html>"""
    cover = f"""<!doctype html><html><head><meta charset='utf-8'><style>{base}
      body{{position:relative;background:#0f0f10;padding:170px 90px 520px;display:flex;flex-direction:column;justify-content:flex-end}}
      body:before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 72% 20%,rgba(200,224,90,.2),transparent 36%),repeating-linear-gradient(135deg,#19191b 0 14px,#121214 14px 28px)}}
      main{{position:relative}}.line{{height:4px;width:170px;background:{accent};margin-bottom:34px}}h2{{margin:0;font-size:108px;line-height:.95;font-weight:400;letter-spacing:-.025em}}
      .name{{margin-top:30px;color:{accent};font-size:28px;letter-spacing:.15em;text-transform:uppercase;font-weight:700}}
    </style></head><body><main><div class='line'></div><h2 class='serif'>{title}</h2><div class='name'>{name}</div></main></body></html>"""
    return {
        "opening": (opening, False),
        "lowerThird": (lower, True),
        "section": (section, False),
        "outro": (outro, False),
        "cover": (cover, False),
    }


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


def render_local_kit_video(
    source: Path,
    output: Path,
    workdir: Path,
    config: dict[str, Any],
    *,
    project_root: Path,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não está instalado.")
    duration = probe_duration(source)
    progress = on_progress or (lambda _value, _stage: None)
    progress(18, "Criando peças gráficas")
    assets = render_kit_assets(config, workdir / "assets", project_root=project_root)
    progress(38, "Ajustando o enquadramento vertical")
    crop = _detect_flat_horizontal_bars(source, duration, ffmpeg)

    topic_start = float(config.get("sectionStartSeconds") or round(duration * 0.52, 2))
    topic_start = min(max(8.0, topic_start), max(8.0, duration - 6.0))
    outro_start = max(topic_start + 1.5, duration - 3.0)
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
        f"between(t,{topic_start:.3f},{topic_start + 1.0:.3f})"
        if config.get("includeSection", True)
        else "0"
    )
    outro_enable = (
        f"between(t,{outro_start:.3f},{duration:.3f})"
        if config.get("includeOutro", True)
        else "0"
    )

    if crop:
        top, crop_height = crop
        source_filter = (
            f"[0:v]crop={VIDEO_WIDTH}:{crop_height}:0:{top},split=2[bg0][fg0];"
        )
    else:
        source_filter = "[0:v]split=2[bg0][fg0];"
    filter_complex = (
        source_filter
        + f"[bg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},gblur=sigma=34,eq=brightness=-0.18:saturation=0.72[bg];"
        f"[fg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[base];"
        "[1:v]format=rgba[opening];[2:v]format=rgba[lower];[3:v]format=rgba[section];[4:v]format=rgba[outro];"
        f"[base][opening]overlay=0:0:enable='{opening_enable}'[v1];"
        f"[v1][lower]overlay=0:0:enable='{lower_enable}'[v2];"
        f"[v2][section]overlay=0:0:enable='{section_enable}'[v3];"
        f"[v3][outro]overlay=0:0:enable='{outro_enable}'[video]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.part.mp4")
    progress(48, "Aplicando o kit ao vídeo")
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-loop",
            "1",
            "-framerate",
            str(VIDEO_FPS),
            "-i",
            str(assets["opening"]),
            "-loop",
            "1",
            "-framerate",
            str(VIDEO_FPS),
            "-i",
            str(assets["lowerThird"]),
            "-loop",
            "1",
            "-framerate",
            str(VIDEO_FPS),
            "-i",
            str(assets["section"]),
            "-loop",
            "1",
            "-framerate",
            str(VIDEO_FPS),
            "-i",
            str(assets["outro"]),
            "-filter_complex",
            filter_complex,
            "-map",
            "[video]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-t",
            f"{duration:.6f}",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    temporary.replace(output)
    progress(96, "Validando o MP4 final")
    final_duration = probe_duration(output)
    if abs(final_duration - duration) > 0.2:
        raise RuntimeError("A duração do vídeo final divergiu do original.")
    manifest = {
        "schemaVersion": "local-video-kit-v1",
        "sourceDuration": round(duration, 3),
        "outputDuration": round(final_duration, 3),
        "outputPath": str(output),
        "coverPath": str(assets["cover"]),
        "detectedContentCrop": (
            {"top": crop[0], "height": crop[1]} if crop else None
        ),
        "events": [
            {"kind": "opening", "enabled": config.get("includeOpening", True), "start": 0, "end": round(opening_end, 3)},
            {"kind": "lowerThird", "enabled": config.get("includeLowerThird", True), "start": round(lower_start, 3), "end": round(lower_end, 3)},
            {"kind": "section", "enabled": config.get("includeSection", True), "start": round(topic_start, 3), "end": round(topic_start + 1, 3)},
            {"kind": "outro", "enabled": config.get("includeOutro", True), "start": round(outro_start, 3), "end": round(duration, 3)},
        ],
        "externalCreditsUsed": False,
    }
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    progress(100, "Vídeo pronto")
    return manifest
