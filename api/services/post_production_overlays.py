"""Render safe-area visual events as transparent 1080x1920 PNG layers."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


def _support_icon(asset_ref: str) -> str:
    kind = asset_ref.removeprefix("generated:")
    icons = {
        "medical_molecule": """<svg viewBox='0 0 160 160' aria-hidden='true'>
          <g fill='none' stroke='currentColor' stroke-width='8'><path d='M42 52 80 30l38 22v44l-38 24-38-24Z'/>
          <path d='m42 52 38 44 38-44M80 30v66'/></g>
          <g fill='currentColor'><circle cx='80' cy='30' r='11'/><circle cx='42' cy='52' r='11'/>
          <circle cx='118' cy='52' r='11'/><circle cx='80' cy='120' r='11'/></g></svg>""",
        "consultation": """<svg viewBox='0 0 160 160' aria-hidden='true'><path fill='none' stroke='currentColor'
          stroke-width='10' stroke-linecap='round' d='M80 28v58M51 57h58'/><path fill='none' stroke='currentColor'
          stroke-width='8' d='M27 20h106v94H76l-28 24v-24H27Z'/></svg>""",
        "science": """<svg viewBox='0 0 160 160' aria-hidden='true'><path fill='none' stroke='currentColor'
          stroke-width='9' d='M60 20h40M70 20v45l-38 64c-5 9 1 19 12 19h72c11 0 17-10 12-19L90 65V20'/>
          <path fill='none' stroke='currentColor' stroke-width='8' d='M50 112h60'/></svg>""",
        "warning": """<svg viewBox='0 0 160 160' aria-hidden='true'><path fill='none' stroke='currentColor'
          stroke-width='9' stroke-linejoin='round' d='m80 18 66 122H14Z'/><path stroke='currentColor'
          stroke-width='10' stroke-linecap='round' d='M80 58v39m0 20v2'/></svg>""",
        "focus": """<svg viewBox='0 0 160 160' aria-hidden='true'><g fill='none' stroke='currentColor'
          stroke-width='9' stroke-linecap='round'><circle cx='80' cy='80' r='34'/><path d='M80 14v20m0 92v20M14 80h20m92 0h20'/></g></svg>""",
    }
    return icons.get(kind, icons["focus"])


def _event_markup(kind: str, raw_text: str, asset_ref: str) -> str:
    if kind == "progressive_list":
        items = [item.strip(" ,;:") for item in re.split(r"\s*•\s*|\n", raw_text) if item.strip(" ,;:")]
        if len(items) >= 2:
            rows = "".join(f"<li>{html.escape(item)}</li>" for item in items[:4])
            return f"<ol>{rows}</ol>"
    escaped = html.escape(raw_text).replace("\n", "<br>")
    if kind == "supporting_visual":
        return f"<div class='visual-icon'>{_support_icon(asset_ref)}</div><div class='support-copy'>{escaped}</div>"
    return escaped


def render_overlay(event: dict[str, Any], destination: Path) -> Path:
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    kind = str(event.get("interactionType") or "caption_emphasis")
    raw_text = str(event.get("visualText") or event.get("spokenText") or "")
    markup = _event_markup(kind, raw_text, str(event.get("assetRef") or "generated:focus"))
    modifier = {
        "kinetic_text": "kinetic",
        "progressive_list": "list",
        "supporting_visual": "support",
        "cta_card": "cta",
    }.get(kind, "emphasis")
    document = f"""<!doctype html><html><head><meta charset='utf-8'><style>
    * {{ box-sizing:border-box }} html,body {{ margin:0;width:1080px;height:1920px;background:transparent;overflow:hidden }}
    body {{ font-family:Arial,sans-serif;color:#fff;display:flex;align-items:flex-start;justify-content:center;padding:80px 90px 380px }}
    .card {{ max-width:860px;padding:20px 30px;border-radius:22px;background:rgba(3,23,37,.88);border:2px solid rgba(32,191,222,.8);font-size:46px;font-weight:800;line-height:1.08;text-align:center;box-shadow:0 16px 50px rgba(0,0,0,.35) }}
    .kinetic {{ font-size:58px;text-transform:uppercase;background:rgba(3,23,37,.76) }}
    .list {{ text-align:left;border-left:12px solid #20bfde;padding:26px 38px }}
    .list ol {{ margin:0;padding:0;list-style:none;display:grid;gap:12px }}
    .list li {{ position:relative;padding-left:48px;font-size:40px;text-transform:none }}
    .list li::before {{ content:'✓';position:absolute;left:0;color:#8cecff }}
    .support {{ border-color:#8cecff;background:rgba(3,23,37,.88);display:flex;align-items:center;gap:26px;text-align:left;max-width:820px }}
    .visual-icon {{ width:142px;height:142px;flex:0 0 142px;color:#8cecff;background:rgba(32,191,222,.12);border-radius:28px;padding:20px }}
    .visual-icon svg {{ width:100%;height:100% }}
    .support-copy {{ font-size:42px;line-height:1.04 }}
    .cta {{ background:#0b7891;border-color:#8cecff;text-transform:uppercase }}
    </style></head><body><div class='card {modifier}'>{markup}</div></body></html>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page = context.new_page()
        try:
            page.set_content(document, wait_until="networkidle")
            page.screenshot(path=str(destination), omit_background=True)
        finally:
            context.close()
            browser.close()
    return destination
