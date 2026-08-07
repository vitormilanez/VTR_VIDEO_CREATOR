"""Renderer deterministico dos apoios visuais de videos verticais.

O Visual Director escolhe apenas o tipo, layout e copy curta. Este modulo
controla o canvas, tipografia, cores, safe areas e o HTML final. Ele gera PNGs
1080x1920 para revisao; a composicao do video fica para um slice posterior.
"""
from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path
from typing import Any

from api.slides import COLORS, _font_css

VIDEO_SLIDE_WIDTH = 1080
VIDEO_SLIDE_HEIGHT = 1920


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-") or "script"


def _visual_class(visual: dict[str, Any]) -> str:
    visual_type = str(visual.get("type") or "none")
    layout = str(visual.get("layout") or "big_statement")
    return f"type-{_slug(visual_type)} layout-{_slug(layout)}"


def _accent(visual: dict[str, Any]) -> str:
    visual_type = str(visual.get("type") or "")
    if visual_type == "comparison":
        return '<div class="comparison-mark"><span>ANTES</span><i></i><span>AGORA</span></div>'
    if visual_type == "quote":
        return '<div class="quote-mark">“</div>'
    if visual_type == "statistic":
        return '<div class="stat-mark">01</div>'
    return '<div class="accent-bar"></div>'


def _compact_text(value: Any, *, max_words: int, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" .,:;") + "…"
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip(" .,:;") + "…"
    return text


def _semantic_label(value: Any) -> str:
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
    return _compact_text(text, max_words=3, max_chars=24)


def _body_points(value: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    raw_points = re.split(r"\s*[•·;]\s*|\s+\d+[.)]\s+", text)
    points = [_semantic_label(point.strip(" -–—:.")) for point in raw_points]
    return [point for point in points if point][:3]


def _visual_motif(visual: dict[str, Any]) -> str:
    visual_type = str(visual.get("type") or "")
    layout = str(visual.get("layout") or "")
    if visual_type == "comparison" or layout == "myth_fact":
        return """
        <div class="motif comparison-motif" aria-hidden="true">
          <span></span><i></i><strong></strong>
        </div>
        """
    if visual_type == "statistic" or layout == "number_stat":
        return '<div class="motif stat-motif" aria-hidden="true">01</div>'
    if visual_type == "quote" or layout == "doctor_quote":
        return '<div class="motif quote-motif" aria-hidden="true">“</div>'
    return """
    <div class="motif orbit-motif" aria-hidden="true">
      <span></span><i></i><strong></strong>
    </div>
    """


def _points_html(points: list[str]) -> str:
    if not points:
        return ""
    return "<div class='point-pills'>" + "".join(
        f"<span><b>{position:02d}</b>{_esc(point)}</span>"
        for position, point in enumerate(points, start=1)
    ) + "</div>"


def _scene_body(scene: dict[str, Any], *, index: int, total: int) -> str:
    visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
    headline = _esc(_compact_text(visual.get("headline"), max_words=7, max_chars=58))
    points = _body_points(visual.get("body"))
    body = _esc(_compact_text(visual.get("body"), max_words=8, max_chars=76))
    return f"""
    <main class="slide {_visual_class(visual)}">
      <div class="glow glow-one"></div><div class="glow glow-two"></div>{_visual_motif(visual)}
      <header class="brand"><strong>Guilherme Martins</strong></header>
      <div class="scene-label">TRANSIÇÃO {index:02d}</div>
      <section class="copy">
        {_accent(visual)}
        <h1>{headline or "A ideia principal da cena"}</h1>
        {_points_html(points) if points else (f'<p>{body}</p>' if body else '')}
      </section>
    </main>
    """


def video_slide_html(scene: dict[str, Any], *, index: int, total: int) -> str:
    """Retorna um documento autocontido pronto para screenshot no Playwright."""
    visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
    if str(visual.get("type") or "none") == "none":
        raise ValueError("Cenas sem apoio visual nao devem ser renderizadas como slide.")
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
    <style>{_css()}</style></head><body>{_scene_body(scene, index=index, total=total)}</body></html>"""


def _wrap_lines(value: Any, *, width: int, max_lines: int) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = kept[-1].rstrip(" .,:;") + "…"
    return kept


def _svg_text(
    lines: list[str],
    *,
    x: int,
    y: int,
    size: int,
    fill: str,
    weight: int = 700,
    line_height: float = 1.16,
    letter_spacing: str = "0",
) -> str:
    if not lines:
        return ""
    spans = []
    for offset, line in enumerate(lines):
        dy = 0 if offset == 0 else round(size * line_height)
        spans.append(
            f"<tspan x='{x}' dy='{dy}'>{_esc(line)}</tspan>"
        )
    return (
        f"<text x='{x}' y='{y}' fill='{fill}' font-family='Arial, Helvetica, sans-serif' "
        f"font-size='{size}' font-weight='{weight}' letter-spacing='{letter_spacing}'>"
        f"{''.join(spans)}</text>"
    )


def _svg_accent(visual: dict[str, Any], *, dark: bool) -> str:
    visual_type = str(visual.get("type") or "")
    ink = COLORS["dark"] if dark else COLORS["light"]
    muted = COLORS["muted"]
    teal = COLORS["teal"]
    if visual_type == "comparison":
        return (
            f"<text x='112' y='536' fill='{muted}' font-family='Arial, Helvetica, sans-serif' "
            "font-size='25' font-weight='800' letter-spacing='5'>ANTES</text>"
            f"<rect x='238' y='523' width='124' height='3' fill='{teal}' />"
            f"<text x='390' y='536' fill='{ink}' font-family='Arial, Helvetica, sans-serif' "
            "font-size='25' font-weight='800' letter-spacing='5'>AGORA</text>"
        )
    if visual_type == "quote":
        return (
            f"<text x='112' y='590' fill='{COLORS['sand']}' font-family='Georgia, serif' "
            "font-size='260' font-style='italic'>“</text>"
        )
    if visual_type == "statistic":
        return (
            f"<text x='112' y='620' fill='{teal}' font-family='Arial, Helvetica, sans-serif' "
            "font-size='210' font-weight='800' letter-spacing='-14'>01</text>"
        )
    return f"<rect x='112' y='558' width='132' height='12' rx='6' fill='{teal}' />"


def _svg_point_pills(points: list[str], *, x: int, y: int, dark: bool) -> str:
    if not points:
        return ""
    fill = "rgba(10,26,47,.06)" if dark else "rgba(244,242,237,.08)"
    stroke = "rgba(10,26,47,.12)" if dark else "rgba(244,242,237,.14)"
    text_fill = COLORS["dark"] if dark else COLORS["light"]
    parts = []
    for position, point in enumerate(points, start=1):
        top = y + ((position - 1) * 108)
        parts.append(
            f"<rect x='{x}' y='{top}' width='780' height='86' rx='26' fill='{fill}' stroke='{stroke}' />"
            f"<text x='{x + 28}' y='{top + 54}' fill='{COLORS['teal']}' font-family='Arial, Helvetica, sans-serif' "
            "font-size='28' font-weight='800' letter-spacing='3'>"
            f"{position:02d}</text>"
            f"<text x='{x + 114}' y='{top + 56}' fill='{text_fill}' font-family='Arial, Helvetica, sans-serif' "
            "font-size='36' font-weight='700'>"
            f"{_esc(point)}</text>"
        )
    return "".join(parts)


def video_slide_svg(scene: dict[str, Any], *, index: int, total: int) -> str:
    """Fallback sem dependencias externas: SVG que o navegador renderiza direto."""
    visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
    if str(visual.get("type") or "none") == "none":
        raise ValueError("Cenas sem apoio visual nao devem ser renderizadas como slide.")

    visual_type = str(visual.get("type") or "")
    layout = str(visual.get("layout") or "Apoio visual").replace("_", " ")
    dark_layout = visual_type in {"comparison", "quote"}
    background = COLORS["light"] if visual_type == "comparison" else COLORS["warm"] if visual_type == "quote" else COLORS["deep"]
    foreground = COLORS["dark"] if dark_layout else COLORS["light"]
    body_fill = COLORS["body_dark"] if dark_layout else COLORS["body_light"]
    border = "rgba(10,26,47,.18)" if dark_layout else "rgba(244,242,237,.16)"

    headline_lines = _wrap_lines(
        _compact_text(visual.get("headline") or "A ideia principal", max_words=7, max_chars=58),
        width=15,
        max_lines=4,
    )
    points = _body_points(visual.get("body"))
    body_lines = _wrap_lines(_compact_text(visual.get("body"), max_words=8, max_chars=76), width=30, max_lines=2)
    top = 650 if visual_type == "statistic" else 680 if visual_type == "quote" else 620

    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='{VIDEO_SLIDE_WIDTH}' height='{VIDEO_SLIDE_HEIGHT}' viewBox='0 0 {VIDEO_SLIDE_WIDTH} {VIDEO_SLIDE_HEIGHT}'>
  <defs>
    <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='{background}' />
      <stop offset='100%' stop-color='{COLORS['dark'] if not dark_layout else COLORS['warm']}' />
    </linearGradient>
    <radialGradient id='glow' cx='50%' cy='50%' r='50%'>
      <stop offset='0%' stop-color='{COLORS['teal']}' stop-opacity='.35' />
      <stop offset='100%' stop-color='{COLORS['teal']}' stop-opacity='0' />
    </radialGradient>
  </defs>
  <rect width='1080' height='1920' fill='url(#bg)' />
  <circle cx='1060' cy='720' r='390' fill='url(#glow)' />
  <circle cx='-40' cy='1460' r='310' fill='{COLORS['sand']}' opacity='.10' />
  <rect x='42' y='42' width='996' height='1836' fill='none' stroke='{border}' />
  <text x='112' y='170' fill='{foreground}' font-family='Arial, Helvetica, sans-serif' font-size='28' font-weight='800' letter-spacing='2'>Guilherme Martins</text>
  <text x='748' y='168' fill='{COLORS['teal']}' font-family='Arial, Helvetica, sans-serif' font-size='22' font-weight='800' letter-spacing='5'>TRANSIÇÃO {index:02d}</text>
  {_svg_accent(visual, dark=dark_layout)}
  {_svg_text(headline_lines, x=112, y=top, size=112, fill=foreground, weight=800, line_height=.96)}
  {_svg_point_pills(points, x=112, y=top + (len(headline_lines) * 108) + 56, dark=dark_layout) if points else _svg_text(body_lines, x=112, y=top + (len(headline_lines) * 108) + 56, size=44, fill=body_fill, weight=650, line_height=1.22)}
</svg>"""


def _css() -> str:
    return f"""
    {_font_css()}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: {VIDEO_SLIDE_WIDTH}px; height: {VIDEO_SLIDE_HEIGHT}px; overflow: hidden; }}
    body {{ background: {COLORS['deep']}; font-family: Archivo, Arial, sans-serif; }}
    .slide {{ position: relative; width: {VIDEO_SLIDE_WIDTH}px; height: {VIDEO_SLIDE_HEIGHT}px; overflow: hidden; color: {COLORS['light']}; background: linear-gradient(145deg, {COLORS['dark']} 0%, {COLORS['deep']} 100%); }}
    .slide::before {{ content: ''; position: absolute; inset: 42px; border: 1px solid rgba(244,242,237,.12); pointer-events: none; }}
    .brand {{ position: absolute; z-index: 3; left: 112px; top: 132px; display: flex; text-transform: uppercase; }}
    .brand strong {{ color: {COLORS['light']}; font-size: 28px; letter-spacing: .08em; line-height: 1; }}
    .scene-label {{ position: absolute; z-index: 3; right: 112px; top: 132px; color: {COLORS['teal']}; font-size: 22px; font-weight: 800; letter-spacing: .22em; text-transform: uppercase; }}
    .copy {{ position: absolute; z-index: 3; left: 112px; right: 112px; top: 520px; }}
    .accent-bar {{ width: 104px; height: 12px; border-radius: 999px; background: {COLORS['teal']}; margin-bottom: 44px; }}
    h1 {{ max-width: 820px; margin: 0; color: {COLORS['light']}; font-size: 126px; font-weight: 850; line-height: .92; letter-spacing: -.06em; text-wrap: balance; }}
    p {{ max-width: 720px; margin: 46px 0 0; color: {COLORS['body_light']}; font-size: 44px; font-weight: 650; line-height: 1.18; text-wrap: balance; }}
    .point-pills {{ margin-top: 54px; display: grid; gap: 18px; max-width: 780px; }}
    .point-pills span {{ display: flex; align-items: center; gap: 20px; min-height: 86px; padding: 20px 28px; border: 1px solid rgba(244,242,237,.14); border-radius: 26px; background: rgba(244,242,237,.08); color: {COLORS['light']}; font-size: 36px; font-weight: 720; line-height: 1.08; backdrop-filter: blur(10px); }}
    .point-pills b {{ color: {COLORS['teal']}; font-size: 28px; letter-spacing: .12em; }}
    footer {{ position: absolute; z-index: 2; left: 112px; right: 112px; bottom: 126px; display: flex; justify-content: space-between; gap: 32px; border-top: 1px solid rgba(244,242,237,.18); padding-top: 28px; color: {COLORS['muted']}; font-size: 21px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }}
    footer span:first-child {{ max-width: 580px; }}
    .glow {{ position: absolute; border-radius: 999px; filter: blur(4px); opacity: .22; }}
    .glow-one {{ width: 880px; height: 880px; right: -380px; top: 270px; background: {COLORS['teal']}; opacity: .26; }}
    .glow-two {{ width: 620px; height: 620px; left: -360px; bottom: 150px; background: {COLORS['sand']}; opacity: .10; }}
    .motif {{ position: absolute; z-index: 1; pointer-events: none; }}
    .orbit-motif {{ right: 76px; top: 660px; width: 360px; height: 360px; border: 3px solid rgba(18,178,166,.42); border-radius: 999px; opacity: .82; }}
    .orbit-motif span,.orbit-motif i,.orbit-motif strong {{ position: absolute; display: block; border-radius: 999px; background: {COLORS['teal']}; }}
    .orbit-motif span {{ width: 46px; height: 46px; right: 38px; top: 32px; }}
    .orbit-motif i {{ width: 150px; height: 150px; left: 104px; top: 104px; opacity: .16; }}
    .orbit-motif strong {{ width: 26px; height: 26px; left: 54px; bottom: 58px; }}
    .comparison-motif {{ right: 88px; top: 670px; width: 310px; height: 310px; }}
    .comparison-motif span,.comparison-motif strong {{ position:absolute; inset:auto; width:180px; height:180px; border-radius:50%; border:4px solid {COLORS['teal']}; }}
    .comparison-motif span {{ left:0; top:0; opacity:.28; }}
    .comparison-motif strong {{ right:0; bottom:0; background:{COLORS['teal']}; opacity:.62; }}
    .comparison-motif i {{ position:absolute; left:72px; top:150px; width:172px; height:5px; border-radius:99px; background:{COLORS['sand']}; transform:rotate(-26deg); }}
    .stat-motif {{ right: 80px; top: 550px; color: rgba(18,178,166,.20); font-size: 360px; font-weight: 850; line-height: .8; letter-spacing: -.08em; }}
    .quote-motif {{ right: 70px; top: 480px; color: rgba(179,139,77,.28); font-family: 'Instrument Serif'; font-size: 520px; font-style: italic; line-height: .75; }}
    .type-overlay {{ background: linear-gradient(155deg, #071521 0%, {COLORS['dark']} 56%, #0b4d50 100%); }}
    .type-statistic .copy {{ top: 560px; }}
    .type-statistic .stat-mark {{ margin-bottom: 38px; color: {COLORS['teal']}; font-size: 210px; font-weight: 800; line-height: .8; letter-spacing: -.08em; }}
    .type-statistic h1 {{ font-size: 104px; }}
    .type-comparison {{ background: {COLORS['light']}; color: {COLORS['dark']}; }}
    .type-comparison::before {{ border-color: rgba(10,26,47,.16); }}
    .type-comparison .brand strong, .type-comparison h1 {{ color: {COLORS['dark']}; }}
    .type-comparison .copy {{ top: 560px; }}
    .type-comparison p {{ color: {COLORS['body_dark']}; }}
    .type-comparison .point-pills span {{ background: rgba(10,26,47,.06); border-color: rgba(10,26,47,.12); color: {COLORS['dark']}; }}
    .comparison-mark {{ display: flex; align-items: center; gap: 22px; margin-bottom: 58px; color: {COLORS['dark']}; font-size: 23px; font-weight: 800; letter-spacing: .18em; }}
    .comparison-mark span:first-child {{ color: {COLORS['muted']}; }}
    .comparison-mark i {{ width: 120px; height: 2px; background: {COLORS['teal']}; }}
    .type-quote {{ background: {COLORS['warm']}; color: {COLORS['dark']}; }}
    .type-quote::before {{ border-color: rgba(10,26,47,.16); }}
    .type-quote .brand strong, .type-quote h1 {{ color: {COLORS['dark']}; }}
    .type-quote p {{ color: {COLORS['body_dark']}; }}
    .type-quote .point-pills span {{ background: rgba(10,26,47,.06); border-color: rgba(10,26,47,.12); color: {COLORS['dark']}; }}
    .type-quote .copy {{ top: 500px; }}
    .quote-mark {{ height: 140px; color: {COLORS['sand']}; font-family: 'Instrument Serif'; font-size: 260px; font-style: italic; line-height: .65; }}
    .layout-question .glow-one {{ background: {COLORS['sand']}; opacity: .15; }}
    .layout-question h1 {{ font-size: 112px; }}
    .layout-number_stat .copy {{ top: 470px; }}
    .layout-cta_photo {{ background: linear-gradient(150deg, {COLORS['deep']} 0%, #12494a 100%); }}
    .layout-cta_photo .glow-one {{ width: 860px; height: 860px; right: -420px; top: 360px; opacity: .38; }}
    """


def render_video_slides(output_dir: Path, visual_plan: dict[str, Any]) -> dict[str, Any]:
    """Gera somente as cenas com visual e retorna metadados estáveis."""
    scenes = [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]
    renderable = [
        scene for scene in scenes
        if isinstance(scene.get("visual"), dict) and str(scene["visual"].get("type") or "none") != "none"
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []

    def asset_record(scene: dict[str, Any], index: int) -> dict[str, Any]:
        visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
        return {
            "sceneId": str(scene.get("sceneId") or f"scene-{index}"),
            "index": index,
            "type": str(visual.get("type") or "none"),
            "layout": str(visual.get("layout") or ""),
            "headline": str(visual.get("headline") or ""),
            "body": str(visual.get("body") or ""),
            "startRatio": visual.get("startRatio", 0),
            "durationSeconds": visual.get("durationSeconds", 0),
            "motionPreset": str(visual.get("motionPreset") or "none"),
            "assetPath": None,
        }

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        for index, scene in enumerate(scenes, start=1):
            record = asset_record(scene, index)
            if record["type"] != "none":
                filename = f"scene-{index:02d}.svg"
                (output_dir / filename).write_text(
                    video_slide_svg(scene, index=index, total=len(scenes)),
                    encoding="utf-8",
                )
                record["assetPath"] = filename
            assets.append(record)
        return {
            "width": VIDEO_SLIDE_WIDTH,
            "height": VIDEO_SLIDE_HEIGHT,
            "scale": 1,
            "format": "svg",
            "sceneCount": len(scenes),
            "renderedCount": len(renderable),
            "assets": assets,
        }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": VIDEO_SLIDE_WIDTH, "height": VIDEO_SLIDE_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            for index, scene in enumerate(scenes, start=1):
                record = asset_record(scene, index)
                if record["type"] != "none":
                    filename = f"scene-{index:02d}.png"
                    page.set_content(video_slide_html(scene, index=index, total=len(scenes)), wait_until="networkidle")
                    page.evaluate("document.fonts.ready")
                    page.screenshot(path=str(output_dir / filename))
                    record["assetPath"] = filename
                assets.append(record)
        finally:
            context.close()
            browser.close()
    return {
        "width": VIDEO_SLIDE_WIDTH,
        "height": VIDEO_SLIDE_HEIGHT,
        "scale": 1,
        "format": "png",
        "sceneCount": len(scenes),
        "renderedCount": len(renderable),
        "assets": assets,
    }
