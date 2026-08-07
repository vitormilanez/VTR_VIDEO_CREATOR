"""Renderer deterministico dos apoios visuais de videos verticais.

O Visual Director escolhe apenas o tipo, layout e copy curta. Este modulo
controla o canvas, tipografia, cores, safe areas e o HTML final. Ele gera PNGs
1080x1920 para revisao; a composicao do video fica para um slice posterior.
"""
from __future__ import annotations

import html
import re
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


def _scene_body(scene: dict[str, Any], *, index: int, total: int) -> str:
    visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
    headline = _esc(visual.get("headline"))
    body = _esc(visual.get("body"))
    purpose = _esc(visual.get("purpose"))
    layout = _esc(visual.get("layout") or "Apoio visual")
    return f"""
    <main class="slide {_visual_class(visual)}">
      <div class="glow glow-one"></div><div class="glow glow-two"></div>
      <header class="brand"><span>Instituto</span><strong>Guilherme Martins</strong></header>
      <div class="scene-label">APOIO VISUAL · {index:02d}/{total:02d}</div>
      <section class="copy">
        {_accent(visual)}
        <div class="layout-label">{layout}</div>
        <h1>{headline or "A ideia principal da cena"}</h1>
        {f'<p>{body}</p>' if body else ''}
      </section>
      <footer><span>{purpose or "Conteúdo educativo"}</span><span>REVISÃO · 1080×1920</span></footer>
    </main>
    """


def video_slide_html(scene: dict[str, Any], *, index: int, total: int) -> str:
    """Retorna um documento autocontido pronto para screenshot no Playwright."""
    visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
    if str(visual.get("type") or "none") == "none":
        raise ValueError("Cenas sem apoio visual nao devem ser renderizadas como slide.")
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
    <style>{_css()}</style></head><body>{_scene_body(scene, index=index, total=total)}</body></html>"""


def _css() -> str:
    return f"""
    {_font_css()}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: {VIDEO_SLIDE_WIDTH}px; height: {VIDEO_SLIDE_HEIGHT}px; overflow: hidden; }}
    body {{ background: {COLORS['deep']}; font-family: Archivo, Arial, sans-serif; }}
    .slide {{ position: relative; width: {VIDEO_SLIDE_WIDTH}px; height: {VIDEO_SLIDE_HEIGHT}px; overflow: hidden; color: {COLORS['light']}; background: linear-gradient(145deg, {COLORS['dark']} 0%, {COLORS['deep']} 100%); }}
    .slide::before {{ content: ''; position: absolute; inset: 42px; border: 1px solid rgba(244,242,237,.14); pointer-events: none; }}
    .brand {{ position: absolute; z-index: 2; left: 112px; top: 128px; display: flex; flex-direction: column; gap: 9px; text-transform: uppercase; }}
    .brand span {{ color: {COLORS['teal']}; font-size: 24px; font-weight: 700; letter-spacing: .42em; line-height: 1; }}
    .brand strong {{ color: {COLORS['light']}; font-size: 32px; letter-spacing: .05em; line-height: 1; }}
    .scene-label, .layout-label {{ color: {COLORS['teal']}; font-size: 22px; font-weight: 700; letter-spacing: .20em; text-transform: uppercase; }}
    .scene-label {{ position: absolute; z-index: 2; right: 112px; top: 140px; }}
    .copy {{ position: absolute; z-index: 2; left: 112px; right: 112px; top: 600px; }}
    .accent-bar {{ width: 132px; height: 12px; background: {COLORS['teal']}; margin-bottom: 42px; }}
    .layout-label {{ margin-bottom: 34px; }}
    h1 {{ max-width: 830px; margin: 0; color: {COLORS['light']}; font-size: 104px; font-weight: 800; line-height: .98; letter-spacing: -.045em; text-wrap: balance; }}
    p {{ max-width: 790px; margin: 46px 0 0; color: {COLORS['body_light']}; font-size: 38px; line-height: 1.38; text-wrap: pretty; }}
    footer {{ position: absolute; z-index: 2; left: 112px; right: 112px; bottom: 126px; display: flex; justify-content: space-between; gap: 32px; border-top: 1px solid rgba(244,242,237,.18); padding-top: 28px; color: {COLORS['muted']}; font-size: 21px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }}
    footer span:first-child {{ max-width: 580px; }}
    .glow {{ position: absolute; border-radius: 999px; filter: blur(4px); opacity: .22; }}
    .glow-one {{ width: 720px; height: 720px; right: -300px; top: 250px; background: {COLORS['teal']}; }}
    .glow-two {{ width: 520px; height: 520px; left: -300px; bottom: 180px; background: {COLORS['sand']}; opacity: .10; }}
    .type-overlay {{ background: linear-gradient(155deg, #071521 0%, {COLORS['dark']} 56%, #0b4d50 100%); }}
    .type-statistic .copy {{ top: 520px; }}
    .type-statistic .stat-mark {{ margin-bottom: 38px; color: {COLORS['teal']}; font-size: 210px; font-weight: 800; line-height: .8; letter-spacing: -.08em; }}
    .type-statistic h1 {{ font-size: 88px; }}
    .type-comparison {{ background: {COLORS['light']}; color: {COLORS['dark']}; }}
    .type-comparison::before {{ border-color: rgba(10,26,47,.16); }}
    .type-comparison .brand strong, .type-comparison h1 {{ color: {COLORS['dark']}; }}
    .type-comparison .copy {{ top: 530px; }}
    .type-comparison p {{ color: {COLORS['body_dark']}; }}
    .comparison-mark {{ display: flex; align-items: center; gap: 22px; margin-bottom: 58px; color: {COLORS['dark']}; font-size: 23px; font-weight: 800; letter-spacing: .18em; }}
    .comparison-mark span:first-child {{ color: {COLORS['muted']}; }}
    .comparison-mark i {{ width: 120px; height: 2px; background: {COLORS['teal']}; }}
    .type-quote {{ background: {COLORS['warm']}; color: {COLORS['dark']}; }}
    .type-quote::before {{ border-color: rgba(10,26,47,.16); }}
    .type-quote .brand strong, .type-quote h1 {{ color: {COLORS['dark']}; }}
    .type-quote p {{ color: {COLORS['body_dark']}; }}
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
    from playwright.sync_api import sync_playwright

    scenes = [scene for scene in visual_plan.get("scenes", []) if isinstance(scene, dict)]
    renderable = [
        scene for scene in scenes
        if isinstance(scene.get("visual"), dict) and str(scene["visual"].get("type") or "none") != "none"
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": VIDEO_SLIDE_WIDTH, "height": VIDEO_SLIDE_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            for index, scene in enumerate(scenes, start=1):
                visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
                record: dict[str, Any] = {
                    "sceneId": str(scene.get("sceneId") or f"scene-{index}"),
                    "index": index,
                    "type": str(visual.get("type") or "none"),
                    "layout": str(visual.get("layout") or ""),
                    "headline": str(visual.get("headline") or ""),
                    "body": str(visual.get("body") or ""),
                    "assetPath": None,
                }
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
        "sceneCount": len(scenes),
        "renderedCount": len(renderable),
        "assets": assets,
    }

