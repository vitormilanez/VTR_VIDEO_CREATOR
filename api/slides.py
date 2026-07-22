#!/usr/bin/env python3
"""
Renderiza os slides do Pack de Conteudo como PNG prontos para postar.

Usa Chromium headless (Playwright) para ter tipografia real, quebra de linha
correta e emoji colorido — coisas que um desenho manual em PIL nao entrega.

Formatos:
- Carrossel: 1080x1350 (4:5, o melhor para feed do Instagram)
- Stories:   1080x1920 (9:16)
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

# Paleta "Ocean Deep" do app.
NAVY = "#152640"
NAVY_SOFT = "#1d3557"
CREAM = "#f6f8f9"
TEAL = "#5cbdb9"
INK = "#1b2b3f"
GRAY = "#5a6a7d"

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Urbanist:wght@600;700;800&family=Epilogue:wght@400;500;600"
    '&display=swap" rel="stylesheet">'
)


def _page(inner: str, css: str, width: int, height: int) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">{_FONTS}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{width}px; height:{height}px; }}
  body {{
    font-family:'Epilogue',-apple-system,system-ui,sans-serif;
    -webkit-font-smoothing:antialiased;
    display:flex; flex-direction:column;
  }}
  .display {{ font-family:'Urbanist',-apple-system,system-ui,sans-serif; letter-spacing:-0.02em; }}
  {css}
</style></head><body>{inner}</body></html>"""


def _cover_html(title: str, body: str, tema: str, width: int, height: int) -> str:
    inner = f"""
    <div class="wrap">
      <div class="top">
        <span class="chip">{html.escape(tema or "Educativo")}</span>
      </div>
      <div class="mid">
        <div class="bar"></div>
        <h1 class="display">{html.escape(title)}</h1>
        <p class="sub">{html.escape(body)}</p>
      </div>
      <div class="foot">Dr. Guilherme · conteúdo educativo</div>
    </div>"""
    css = f"""
    body {{ background:{NAVY}; color:#fff; }}
    .wrap {{ flex:1; display:flex; flex-direction:column; justify-content:space-between; padding:96px 88px; }}
    .chip {{ display:inline-block; padding:14px 28px; border:2px solid rgba(92,189,185,.5);
             border-radius:999px; color:{TEAL}; font-size:30px; font-weight:600; }}
    .bar {{ width:120px; height:10px; background:{TEAL}; border-radius:999px; margin-bottom:44px; }}
    h1 {{ font-size:{86 if len(title) < 60 else 68}px; font-weight:800; line-height:1.08; }}
    .sub {{ margin-top:40px; font-size:38px; line-height:1.45; color:rgba(255,255,255,.78); }}
    .foot {{ font-size:26px; color:rgba(255,255,255,.5); }}
    """
    return _page(inner, css, width, height)


def _content_html(
    index: int, total: int, title: str, body: str, width: int, height: int
) -> str:
    inner = f"""
    <div class="wrap">
      <div class="num">{index:02d} <span class="of">/ {total:02d}</span></div>
      <div class="mid">
        <h2 class="display">{html.escape(title)}</h2>
        <p class="body">{html.escape(body)}</p>
      </div>
      <div class="foot"><span class="dot"></span> Dr. Guilherme</div>
    </div>"""
    css = f"""
    body {{ background:{CREAM}; color:{INK}; }}
    .wrap {{ flex:1; display:flex; flex-direction:column; justify-content:space-between; padding:96px 88px; }}
    .num {{ font-size:30px; font-weight:700; color:{TEAL}; letter-spacing:.06em; }}
    .of {{ color:#b4c0cc; }}
    h2 {{ font-size:{72 if len(title) < 46 else 58}px; font-weight:700; line-height:1.12; color:{NAVY}; }}
    .body {{ margin-top:40px; font-size:38px; line-height:1.5; color:{GRAY}; }}
    .foot {{ font-size:26px; color:#93a2b2; display:flex; align-items:center; gap:14px; }}
    .dot {{ width:14px; height:14px; border-radius:999px; background:{TEAL}; display:inline-block; }}
    """
    return _page(inner, css, width, height)


def _cta_html(title: str, body: str, width: int, height: int) -> str:
    inner = f"""
    <div class="wrap">
      <div class="bar"></div>
      <h2 class="display">{html.escape(title)}</h2>
      <p class="body">{html.escape(body)}</p>
      <div class="foot">Conteúdo educativo. Não substitui avaliação médica individual.</div>
    </div>"""
    css = f"""
    body {{ background:linear-gradient(160deg,{NAVY} 0%,{NAVY_SOFT} 100%); color:#fff; }}
    .wrap {{ flex:1; display:flex; flex-direction:column; justify-content:center; padding:96px 88px; }}
    .bar {{ width:120px; height:10px; background:{TEAL}; border-radius:999px; margin-bottom:48px; }}
    h2 {{ font-size:76px; font-weight:800; line-height:1.1; }}
    .body {{ margin-top:36px; font-size:40px; line-height:1.45; color:rgba(255,255,255,.85); }}
    .foot {{ margin-top:auto; font-size:24px; color:rgba(255,255,255,.45); }}
    """
    return _page(inner, css, width, height)


def _story_html(index: int, title: str, body: str, width: int, height: int) -> str:
    inner = f"""
    <div class="wrap">
      <div class="chip">{html.escape(title)}</div>
      <p class="body display">{html.escape(body)}</p>
      <div class="foot">Dr. Guilherme · {index:02d}</div>
    </div>"""
    css = f"""
    body {{ background:linear-gradient(170deg,{NAVY} 0%,{NAVY_SOFT} 100%); color:#fff; }}
    .wrap {{ flex:1; display:flex; flex-direction:column; justify-content:center; padding:140px 96px; }}
    .chip {{ align-self:flex-start; padding:16px 32px; border:2px solid rgba(92,189,185,.5);
             border-radius:999px; color:{TEAL}; font-size:32px; font-weight:600; margin-bottom:56px; }}
    .body {{ font-size:64px; font-weight:700; line-height:1.25; }}
    .foot {{ margin-top:auto; font-size:28px; color:rgba(255,255,255,.45); }}
    """
    return _page(inner, css, width, height)


def render_pack_images(
    folder: Path,
    carousel: Iterable[dict],
    stories: Iterable[dict],
) -> dict:
    """Gera PNGs do carrossel (1080x1350) e dos stories (1080x1920)."""
    from playwright.sync_api import sync_playwright

    carousel = list(carousel)
    stories = list(stories)
    car_dir = folder / "carrossel" / "png"
    sto_dir = folder / "stories" / "png"
    car_dir.mkdir(parents=True, exist_ok=True)
    sto_dir.mkdir(parents=True, exist_ok=True)

    gerados = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            total = len(carousel)
            for i, slide in enumerate(carousel, start=1):
                titulo = str(slide.get("title") or "")
                corpo = str(slide.get("body") or "")
                if i == 1:
                    doc = _cover_html(titulo, corpo, str(slide.get("tema") or ""), 1080, 1350)
                elif i == total:
                    doc = _cta_html(titulo, corpo, 1080, 1350)
                else:
                    doc = _content_html(i, total, titulo, corpo, 1080, 1350)
                page.set_content(doc, wait_until="load")
                page.wait_for_timeout(220)  # deixa a fonte do Google carregar
                page.screenshot(path=str(car_dir / f"slide-{i:02d}.png"))
                gerados += 1

            page.set_viewport_size({"width": 1080, "height": 1920})
            for i, story in enumerate(stories, start=1):
                doc = _story_html(
                    i, str(story.get("title") or ""), str(story.get("body") or ""), 1080, 1920
                )
                page.set_content(doc, wait_until="load")
                page.wait_for_timeout(220)
                page.screenshot(path=str(sto_dir / f"story-{i:02d}.png"))
                gerados += 1
        finally:
            browser.close()

    return {"images": gerados, "carrossel_dir": str(car_dir), "stories_dir": str(sto_dir)}
