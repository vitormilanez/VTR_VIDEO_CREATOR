"""Render safe-area visual events as transparent 1080x1920 PNG layers."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from api.services.medical_identity import MEDICAL_DEFAULT_SAFE_CTA, has_prohibited_editorial_cta


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


def _stacked_copy(raw_text: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return f"<strong class='headline'>{html.escape(lines[0])}</strong>"
    eyebrow = html.escape(lines[0])
    headline = html.escape(lines[1])
    detail = "<br>".join(html.escape(line) for line in lines[2:])
    detail_markup = f"<span class='detail'>{detail}</span>" if detail else ""
    return (
        f"<span class='eyebrow'>{eyebrow}</span>"
        f"<strong class='headline'>{headline}</strong>"
        f"{detail_markup}"
    )


def _event_markup(kind: str, raw_text: str, asset_ref: str) -> str:
    if kind == "progressive_list":
        items = [item.strip(" ,;:") for item in re.split(r"\s*•\s*|\n", raw_text) if item.strip(" ,;:")]
        if len(items) >= 2:
            rows = "".join(f"<li>{html.escape(item)}</li>" for item in items[:4])
            return f"<ol>{rows}</ol>"
    if kind == "comparison_card":
        parts = [
            part.strip(" ,;:")
            for part in re.split(r"\s*•\s*|\s+(?:vs\.?|versus)\s+|\n", raw_text, flags=re.IGNORECASE)
            if part.strip(" ,;:")
        ]
        if len(parts) >= 2:
            return (
                f"<div class='comparison-side'>{html.escape(parts[0])}</div>"
                "<div class='comparison-vs'>×</div>"
                f"<div class='comparison-side comparison-strong'>{html.escape(parts[1])}</div>"
            )
    if kind == "number_card":
        match = re.search(r"\b\d+(?:[,.]\d+)?\s*%?\b", raw_text)
        if match:
            before = raw_text[: match.start()].strip(" ,;:-")
            after = raw_text[match.end() :].strip(" ,;:-")
            return (
                f"<span class='eyebrow'>{html.escape(before)}</span>"
                f"<strong class='big-number'>{html.escape(match.group(0))}</strong>"
                f"<span class='detail'>{html.escape(after)}</span>"
            )
    if kind == "quote_card":
        return f"<blockquote>“{html.escape(raw_text.strip())}”</blockquote>"
    stacked = _stacked_copy(raw_text)
    if kind == "supporting_visual":
        return f"<div class='visual-icon'>{_support_icon(asset_ref)}</div><div class='support-copy'>{stacked}</div>"
    return stacked


_POSITION_STYLES = {
    "top_left": ("flex-start", "flex-start"),
    "top_center": ("center", "flex-start"),
    "top_right": ("flex-end", "flex-start"),
    "center_left": ("flex-start", "center"),
    "center": ("center", "center"),
    "center_right": ("flex-end", "center"),
    "bottom_left": ("flex-start", "flex-end"),
    "bottom_center": ("center", "flex-end"),
    "bottom_right": ("flex-end", "flex-end"),
}


def _overlay_appearance(event: dict[str, Any]) -> tuple[str, float, str]:
    position = str(event.get("screenPosition") or "top_right")
    if position not in _POSITION_STYLES:
        position = "top_right"
    color = str(event.get("backgroundColor") or "#073e4b").strip().lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", color):
        color = "#073e4b"
    try:
        opacity = float(event.get("backgroundOpacity", 0.9))
    except (TypeError, ValueError):
        opacity = 0.9
    return position, min(1.0, max(0.15, opacity)), color


def overlay_document(event: dict[str, Any]) -> str:
    kind = str(event.get("interactionType") or "caption_emphasis")
    raw_text = str(event.get("visualText") or event.get("spokenText") or "")
    if has_prohibited_editorial_cta(raw_text):
        raw_text = MEDICAL_DEFAULT_SAFE_CTA
    markup = _event_markup(kind, raw_text, str(event.get("assetRef") or "generated:focus"))
    modifier = {
        "kinetic_text": "kinetic",
        "progressive_list": "list",
        "supporting_visual": "support",
        "definition_card": "definition",
        "number_card": "number",
        "comparison_card": "comparison",
        "quote_card": "quote",
        "evidence_card": "evidence",
        "cta_card": "cta",
    }.get(kind, "emphasis")
    position, opacity, color = _overlay_appearance(event)
    justify_content, align_items = _POSITION_STYLES[position]
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    deep_red, deep_green, deep_blue = (
        max(0, round(channel * 0.48)) for channel in (red, green, blue)
    )
    background = f"rgba({red},{green},{blue},{opacity:.2f})"
    deep_background = f"rgba({deep_red},{deep_green},{deep_blue},{opacity:.2f})"
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
    * {{ box-sizing:border-box }} html,body {{ margin:0;width:1080px;height:1920px;background:transparent;overflow:hidden }}
    body {{ position:relative;font-family:Arial,sans-serif;color:#fff }}
    .stage {{ position:absolute;inset:230px 64px 390px;display:flex;justify-content:{justify_content};align-items:{align_items} }}
    .card {{ position:relative;width:470px;min-height:280px;padding:38px;border-radius:34px;background:linear-gradient(145deg,{background},{deep_background});border:1px solid rgba(140,236,255,.72);font-weight:800;line-height:1.05;text-align:left;box-shadow:0 26px 70px rgba(0,0,0,.34);overflow:hidden }}
    .card::before {{ content:'';position:absolute;left:38px;right:38px;top:0;height:7px;border-radius:0 0 8px 8px;background:linear-gradient(90deg,#20bfde,#8cecff) }}
    .eyebrow {{ display:block;margin-bottom:18px;color:#8cecff;font-size:20px;font-weight:800;letter-spacing:4px;text-transform:uppercase }}
    .headline {{ display:block;font-size:50px;line-height:.98;letter-spacing:-1.6px;text-transform:uppercase }}
    .detail {{ display:block;margin-top:20px;padding-top:18px;border-top:1px solid rgba(255,255,255,.2);color:rgba(255,255,255,.9);font-size:27px;font-weight:600;line-height:1.2 }}
    .kinetic {{ background:linear-gradient(145deg,{background},{deep_background}) }}
    .kinetic .headline {{ font-size:54px }}
    .emphasis {{ min-height:250px }}
    .list {{ border-left:10px solid #20bfde;padding:34px 38px }}
    .list ol {{ margin:0;padding:0;list-style:none;display:grid;gap:12px }}
    .list li {{ position:relative;padding-left:44px;font-size:34px;line-height:1.15;text-transform:none }}
    .list li::before {{ content:'✓';position:absolute;left:0;color:#8cecff }}
    .support {{ border-color:#8cecff;display:flex;align-items:flex-start;gap:22px }}
    .visual-icon {{ width:94px;height:94px;flex:0 0 94px;color:#8cecff;background:rgba(32,191,222,.12);border-radius:24px;padding:16px }}
    .visual-icon svg {{ width:100%;height:100% }}
    .support-copy {{ min-width:0;flex:1 }}
    .support .headline {{ font-size:40px }}
    .support .detail {{ font-size:24px }}
    .definition {{ border-left:10px solid #8cecff }}
    .definition .eyebrow::before {{ content:'DEFINIÇÃO · ' }}
    .number {{ min-height:330px }}
    .big-number {{ display:block;color:#8cecff;font-size:112px;line-height:.9;letter-spacing:-5px }}
    .comparison {{ display:grid;grid-template-columns:1fr auto 1fr;align-items:stretch;gap:12px;width:620px }}
    .comparison-side {{ display:flex;align-items:center;padding:22px;border-radius:20px;background:rgba(255,255,255,.08);font-size:28px;line-height:1.15 }}
    .comparison-strong {{ color:#8cecff;border:1px solid rgba(140,236,255,.45) }}
    .comparison-vs {{ align-self:center;color:#8cecff;font-size:42px }}
    .quote blockquote {{ margin:0;font-family:Georgia,serif;font-size:43px;font-weight:600;line-height:1.12 }}
    .evidence {{ border-color:#8cecff }}
    .evidence::after {{ content:'EVIDÊNCIA';position:absolute;right:28px;bottom:22px;color:#8cecff;font-size:16px;letter-spacing:3px }}
    .cta {{ background:linear-gradient(145deg,{background},{deep_background});border-color:#8cecff }}
    .cta .headline {{ font-size:43px }}
    </style></head><body><div class='stage position-{position}'><div class='card {modifier}'>{markup}</div></div></body></html>"""


def render_overlay(event: dict[str, Any], destination: Path) -> Path:
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = overlay_document(event)
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
