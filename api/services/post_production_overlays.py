"""Render safe-area visual events as transparent 1080x1920 PNG layers."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def render_overlay(event: dict[str, Any], destination: Path) -> Path:
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    kind = str(event.get("interactionType") or "caption_emphasis")
    text = html.escape(str(event.get("visualText") or event.get("spokenText") or ""))
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
    .list {{ text-align:left;border-left:12px solid #20bfde }}
    .support {{ border-color:#fff;background:rgba(3,23,37,.72) }}
    .cta {{ background:#0b7891;border-color:#8cecff;text-transform:uppercase }}
    </style></head><body><div class='card {modifier}'>{text}</div></body></html>"""
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
