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

from api.services.local_video_captions import render_caption_assets, write_caption_timeline
from api.services.transcript_service import transcribe_video_to_file


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
    section_title = _safe_text(config.get("sectionTitle"), "", 100)
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
      h2{{margin:0;font-size:118px;line-height:.98;font-weight:400;letter-spacing:-.02em;max-width:920px}}
    </style></head><body><main><h2 class='serif'>{section_title}</h2></main></body></html>"""
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
    return min(max(0.0, tail), 120.0)


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


def render_local_kit_video(
    source: Path,
    output: Path,
    workdir: Path,
    config: dict[str, Any],
    *,
    project_root: Path,
    music_path: Path | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não está instalado.")
    duration = probe_duration(source)
    progress = on_progress or (lambda _value, _stage: None)
    has_audio = _probe_has_audio(source, ffmpeg)
    captions: list[dict[str, Any]] = []
    if config.get("includeCaptions", True) and has_audio:
        progress(8, "Transcrevendo e sincronizando legendas")
        transcript_path = workdir / "transcript.json"
        if transcript_path.is_file():
            try:
                transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                transcript = transcribe_video_to_file(
                    source,
                    transcript_path,
                    project_root=project_root,
                )
        else:
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
    progress(42, "Ajustando o enquadramento vertical")
    crop = _detect_flat_horizontal_bars(source, duration, ffmpeg)

    include_section = _section_enabled(config)
    topic_start, section_duration = _section_timing(config, duration)
    section_end = min(duration, topic_start + section_duration)
    section_stream, section_position = _section_transition(config, topic_start, section_end)
    motion_profile = _motion_profile(
        config,
        duration,
        blocked_intervals=(
            [(topic_start, section_end)] if include_section else []
        ),
    )
    outro_tail = _outro_tail_seconds(config) if config.get("includeOutro", True) else 0.0
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
    filter_complex = (
        source_filter
        + f"[bg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},gblur=sigma=34,eq=brightness=-0.18:saturation=0.72[bg];"
        f"[fg0]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[base_raw];"
        + _motion_filter(motion_profile)
        + "[1:v]format=rgba[opening];[2:v]format=rgba[lower];"
        + section_stream
        + "[4:v]format=rgba[outro];"
        f"[base][opening]overlay=0:0:enable='{opening_enable}'[v1];"
        f"[v1][lower]overlay=0:0:enable='{lower_enable}'[v2];"
        f"[v2][section]overlay={section_position}:enable='{section_enable}'[v3];"
        f"[v3]tpad=stop_mode=clone:stop_duration={outro_tail:.3f}[extended];"
        f"[extended][outro]overlay=0:0:enable='{outro_enable}'[video_base]"
    )
    video_map = "[video_base]"
    caption_input_start = 5 + (1 if music_path else 0)
    if caption_timeline:
        enable_terms = [f"between(t,0,{duration:.3f})"]
        if config.get("includeOpening", True) and opening_end:
            enable_terms.append(f"not(between(t,0,{opening_end:.3f}))")
        if include_section:
            enable_terms.append(
                f"not(between(t,{topic_start:.3f},{section_end:.3f}))"
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

    ffmpeg_args = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            *still_input(assets["opening"]),
            *still_input(assets["lowerThird"]),
            *still_input(assets["section"], frame_rate=VIDEO_FPS),
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
            "-movflags",
            "+faststart",
            str(temporary),
        ])
    _run(ffmpeg_args)
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
            {"kind": "outro", "enabled": config.get("includeOutro", True), "start": round(duration, 3), "end": round(expected_duration, 3)},
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
