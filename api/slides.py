#!/usr/bin/env python3
"""
Renderiza os slides do Pack de Conteudo como PNG prontos para postar.

O Claude fornece apenas um design plan com vocabulario fechado. Este modulo
transforma esse plano em HTML/CSS controlado pelo projeto e renderiza via
Playwright.

Formatos:
- Carrossel: 1080x1350
- Stories:   1080x1920
"""
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent

NAVY = "#152640"
INK = "#1b2b3f"
CREAM = "#f6f8f9"
TEAL = "#5cbdb9"
CORAL = "#d86f5d"
SAGE = "#87a96b"
GRAY = "#5a6a7d"

LAYOUTS = {
    "hero_avatar",
    "avatar_split",
    "big_statement",
    "myth_fact",
    "number_stat",
    "three_points",
    "quote_card",
    "editorial_photo",
    "minimal_explainer",
    "cta_avatar",
}

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Urbanist:wght@600;700;800&family=Epilogue:wght@400;500;600"
    '&display=swap" rel="stylesheet">'
)


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _safe_layout(value: Any, fallback: str = "minimal_explainer") -> str:
    candidate = str(value or fallback)
    return candidate if candidate in LAYOUTS else fallback


def _page(inner: str, css: str, width: int, height: int) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">{_FONTS}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{width}px; height:{height}px; overflow:hidden; }}
  body {{
    font-family:'Epilogue',-apple-system,system-ui,sans-serif;
    -webkit-font-smoothing:antialiased;
    display:flex;
    color:{INK};
  }}
  .display {{ font-family:'Urbanist',-apple-system,system-ui,sans-serif; letter-spacing:0; }}
  {css}
</style></head><body>{inner}</body></html>"""


def _asset_uri(avatar_asset: dict[str, Any] | None) -> str:
    if not avatar_asset:
        return ""
    raw_path = str(avatar_asset.get("cachedAssetPath") or "")
    if not raw_path:
        return ""
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


INTENT_LABELS = {
    "provocative": "Ponto de atenção",
    "educational": "Entenda o contexto",
    "reassuring": "O que importa",
    "contrast": "Mito ou fato",
    "authority": "Visão clínica",
    "action": "Próximo passo",
}


def _direction_tokens(direction: str, background: str) -> dict[str, str]:
    if background in {"clinical_light", "teal_soft", "warm_neutral", "data_panel"}:
        accent = "#258d91" if background != "warm_neutral" else "#c85f50"
        return {"accent": accent, "muted": "#526276", "panel": "rgba(255,255,255,.90)"}
    if direction == "dark_provocative":
        return {"accent": "#ff836e", "muted": "#d7e0ea", "panel": "rgba(255,255,255,.10)"}
    if direction == "human_lifestyle":
        return {"accent": "#4f8d7d", "muted": "#415465", "panel": "rgba(255,255,255,.84)"}
    if direction == "editorial_premium":
        return {"accent": "#7ed4cd", "muted": "#d8e0e7", "panel": "rgba(255,255,255,.12)"}
    if background == "data_panel":
        return {"accent": "#d86f5d", "muted": "#526276", "panel": "rgba(255,255,255,.90)"}
    return {"accent": "#258d91", "muted": "#526276", "panel": "rgba(255,255,255,.90)"}


def _background_css(direction: str, background: str) -> str:
    if background == "dark_gradient":
        return f"linear-gradient(145deg,{NAVY} 0%,#203854 54%,#101d2f 100%)"
    if background == "editorial_ink":
        return "linear-gradient(145deg,#0e1c2e 0%,#1d3552 100%)"
    if background == "teal_soft":
        return "linear-gradient(145deg,#dcefed 0%,#f8fbfb 65%,#ffffff 100%)"
    if background == "warm_neutral":
        return "linear-gradient(145deg,#f2eee7 0%,#faf9f6 68%,#ffffff 100%)"
    if background == "data_panel":
        return "linear-gradient(145deg,#eaf2f4 0%,#f8fafb 100%)"
    return "linear-gradient(145deg,#f4f8f9 0%,#ffffff 75%)"


def _title_size(title: str, layout: str, story: bool) -> int:
    base = 68 if story else 76
    if layout in {"big_statement", "quote_card"}:
        base += 10
    if len(title) > 58:
        base -= 14
    elif len(title) > 42:
        base -= 8
    return max(50 if story else 54, base)


def _body_size(body: str, story: bool) -> int:
    base = 34 if story else 30
    if len(body) > 240:
        base -= 4
    return max(24, base)


def _intent_label(value: Any) -> str:
    return INTENT_LABELS.get(str(value or ""), "Conteúdo educativo")


def _avatar_html(slide: dict[str, Any], avatar_uri: str) -> str:
    avatar = slide.get("avatar") if isinstance(slide.get("avatar"), dict) else {}
    photo_asset = slide.get("photoAsset") if isinstance(slide.get("photoAsset"), dict) else None
    photo_uri = _asset_uri(photo_asset)
    media_uri = photo_uri or avatar_uri
    if not media_uri or (not photo_uri and not avatar.get("show")):
        return ""
    position = str(avatar.get("position") or "right")
    crop = str(avatar.get("crop") or "waist")
    try:
        # A scaled-down image exposes the neutral figure background as a box.
        # Keep the asset covering its editorial frame; layout controls its size.
        scale = max(1, min(1.35, float(avatar.get("scale") or 1)))
    except (TypeError, ValueError):
        scale = 1
    cls = f"avatar avatar-{position} avatar-{crop}"
    return (
        f'<figure class="{cls}" style="--avatar-scale:{scale};">'
        f'<img src="{media_uri}" alt=""></figure>'
    )


def _slide_html(
    slide: dict[str, Any],
    *,
    index: int,
    total: int,
    width: int,
    height: int,
    design_direction: str,
    avatar_uri: str,
    story: bool = False,
) -> str:
    raw_title = str(slide.get("title") or "")
    raw_body = str(slide.get("body") or "")
    title = _esc(raw_title)
    body = _esc(raw_body)
    highlight = _esc(slide.get("highlight") or slide.get("title"))
    layout = _safe_layout(slide.get("layout"), "hero_avatar" if index == 1 else "minimal_explainer")
    background = str(slide.get("background") or "clinical_light")
    tokens = _direction_tokens(design_direction, background)
    dark = background in {"dark_gradient", "editorial_ink"}
    text_color = "#ffffff" if dark else INK
    muted = tokens["muted"]
    avatar = _avatar_html(slide, avatar_uri)
    has_avatar = bool(avatar)
    note = (
        '<div class="medical-note">Conteúdo educativo. Não substitui avaliação médica individual.</div>'
        if layout == "cta_avatar" or index == total
        else ""
    )
    inner = f"""
    <section class="slide layout-{layout}{' has-avatar' if has_avatar else ''}">
      <div class="brand"><strong>DR. GUILHERME</strong><span>METABOLISMO</span></div>
      <div class="counter">{index:02d}<span>/ {total:02d}</span></div>
      <div class="content">
        <div class="kicker">{_esc(_intent_label(slide.get("visualIntent")))}</div>
        <h1 class="display">{title}</h1>
        <p>{body}</p>
        <div class="highlight">{highlight}</div>
      </div>
      {avatar}
      {note}
    </section>"""
    css = _base_css(
        width,
        height,
        background_css=_background_css(design_direction, background),
        text_color=text_color,
        muted=muted,
        accent=tokens["accent"],
        panel=tokens["panel"],
        story=story,
        title_size=_title_size(raw_title, layout, story),
        body_size=_body_size(raw_body, story),
    )
    return _page(inner, css, width, height)


def _base_css(
    width: int,
    height: int,
    *,
    background_css: str,
    text_color: str,
    muted: str,
    accent: str,
    panel: str,
    story: bool,
    title_size: int,
    body_size: int,
) -> str:
    padding_y = 72 if not story else 96
    padding_x = 76 if not story else 82
    return f"""
    body {{ background:{background_css}; color:{text_color}; }}
    .slide {{ position:relative; width:{width}px; height:{height}px; padding:{padding_y}px {padding_x}px; overflow:hidden; }}
    .brand {{ position:absolute; z-index:5; left:{padding_x}px; top:{padding_y}px; color:{muted}; font-size:16px; letter-spacing:.08em; display:flex; gap:14px; align-items:center; }}
    .brand strong {{ color:{text_color}; font-size:17px; letter-spacing:.06em; }}
    .brand span {{ border-left:1px solid {muted}; padding-left:14px; font-size:13px; }}
    .counter {{ position:absolute; z-index:5; right:{padding_x}px; top:{padding_y - 8}px; font-size:26px; font-weight:800; color:{accent}; letter-spacing:.04em; }}
    .counter span {{ color:{muted}; font-weight:600; }}
    .medical-note {{ position:absolute; z-index:5; right:{padding_x}px; bottom:48px; max-width:365px; text-align:right; font-size:16px; line-height:1.38; color:{muted}; }}
    .content {{ position:relative; z-index:3; max-width:790px; padding-top:{250 if not story else 310}px; }}
    .kicker {{ color:{accent}; text-transform:uppercase; font-size:16px; font-weight:800; letter-spacing:.11em; margin-bottom:22px; }}
    h1 {{ font-size:{title_size}px; font-weight:800; line-height:1.02; text-wrap:balance; letter-spacing:0; }}
    p {{ margin-top:28px; font-size:{body_size}px; line-height:1.34; color:{muted}; max-width:770px; }}
    .highlight {{ margin-top:34px; max-width:620px; border-left:6px solid {accent}; padding:7px 0 7px 18px; font-size:23px; line-height:1.22; color:{text_color}; font-weight:700; }}
    .avatar {{ position:absolute; z-index:2; margin:0; overflow:hidden; background:#dce2e4; }}
    .avatar img {{ display:block; width:100%; height:100%; object-fit:cover; object-position:center; transform:scale(var(--avatar-scale)); transform-origin:center; }}
    .layout-hero_avatar.has-avatar .content, .layout-avatar_split.has-avatar .content {{ max-width:530px; }}
    .layout-hero_avatar .avatar, .layout-avatar_split .avatar {{ right:0; top:0; width:45%; height:100%; }}
    .layout-hero_avatar .avatar::after, .layout-avatar_split .avatar::after {{ content:""; position:absolute; inset:0; background:linear-gradient(90deg,{NAVY} 0%,transparent 30%); opacity:.28; pointer-events:none; }}
    .layout-hero_avatar .highlight {{ margin-top:42px; }}
    .layout-avatar_split .content {{ max-width:670px; }}
    .layout-avatar_split.has-avatar .content {{ max-width:500px; }}
    .layout-big_statement .content {{ max-width:840px; padding-top:{320 if not story else 410}px; }}
    .layout-big_statement h1 {{ font-size:{title_size + 8}px; max-width:800px; }}
    .layout-big_statement.has-avatar .content {{ max-width:720px; padding-top:220px; }}
    .layout-big_statement.has-avatar .avatar {{ left:{padding_x}px; right:{padding_x}px; bottom:58px; height:270px; }}
    .layout-big_statement.has-avatar .avatar img {{ object-position:center 28%; }}
    .layout-big_statement.has-avatar .highlight {{ margin-top:24px; }}
    .layout-myth_fact .content {{ max-width:820px; padding:62px; margin-top:{120 if not story else 150}px; background:{panel}; border:1px solid rgba(255,255,255,.34); }}
    .layout-myth_fact .content::before {{ content:"MITO"; display:inline-block; color:{accent}; font-size:17px; font-weight:800; letter-spacing:.12em; margin-bottom:28px; }}
    .layout-myth_fact .kicker {{ display:none; }}
    .layout-myth_fact .highlight {{ margin-top:30px; }}
    .layout-myth_fact .highlight::before {{ content:"FATO"; display:block; color:{accent}; font-size:15px; letter-spacing:.1em; margin-bottom:8px; }}
    .layout-number_stat .content {{ max-width:770px; padding-top:310px; }}
    .layout-number_stat .highlight {{ border:0; padding:0; color:{accent}; font-size:48px; }}
    .layout-three_points .content {{ max-width:730px; padding-top:230px; }}
    .layout-three_points .highlight {{ margin-top:30px; background:{panel}; border-left:0; border-top:5px solid {accent}; padding:20px 22px; }}
    .layout-three_points.has-avatar .avatar {{ right:0; bottom:0; width:46%; height:34%; }}
    .layout-three_points.has-avatar .content {{ max-width:720px; }}
    .layout-quote_card .content {{ max-width:840px; padding-top:305px; }}
    .layout-quote_card h1::before {{ content:"“"; color:{accent}; }}
    .layout-quote_card h1::after {{ content:"”"; color:{accent}; }}
    .layout-quote_card p {{ max-width:660px; }}
    .layout-quote_card .highlight {{ border:0; padding-left:0; color:{accent}; }}
    .layout-editorial_photo.has-avatar .avatar {{ inset:0; height:100%; width:100%; }}
    .layout-editorial_photo.has-avatar .avatar::after {{ content:""; position:absolute; inset:0; background:linear-gradient(0deg,rgba(10,24,42,.9) 2%,rgba(10,24,42,.08) 72%); }}
    .layout-editorial_photo .content {{ max-width:800px; padding-top:{720 if not story else 1040}px; }}
    .layout-editorial_photo .brand, .layout-editorial_photo .counter {{ color:#fff; }}
    .layout-editorial_photo .brand span, .layout-editorial_photo p {{ color:#e7eef2; }}
    .layout-minimal_explainer .content {{ max-width:770px; padding:58px; margin-top:{140 if not story else 180}px; background:{panel}; border-top:7px solid {accent}; }}
    .layout-minimal_explainer .highlight {{ display:none; }}
    .layout-cta_avatar.has-avatar .content {{ width:47%; margin-left:auto; padding-top:{310 if not story else 500}px; }}
    .layout-cta_avatar .avatar {{ left:0; top:0; width:46%; height:100%; }}
    .layout-cta_avatar .avatar::after {{ content:""; position:absolute; inset:0; background:linear-gradient(90deg,transparent 64%,{NAVY} 100%); }}
    .layout-cta_avatar .medical-note {{ max-width:390px; color:{muted}; }}
    .layout-cta_avatar:not(.has-avatar) .content {{ max-width:780px; padding-top:{350 if not story else 500}px; }}
    """


def _static_post_html(
    static_post: dict[str, Any],
    *,
    design_direction: str,
    avatar_uri: str,
    width: int,
    height: int,
) -> str:
    slide = {
        "title": static_post.get("headline"),
        "body": static_post.get("subline"),
        "highlight": static_post.get("subline"),
        "layout": static_post.get("layout") or "big_statement",
        "visualIntent": static_post.get("visualIntent") or "educational",
        "avatar": static_post.get("avatar") or {"show": False},
        "background": static_post.get("background") or "clinical_light",
        "photoAsset": static_post.get("photoAsset"),
    }
    return _slide_html(
        slide,
        index=1,
        total=1,
        width=width,
        height=height,
        design_direction=design_direction,
        avatar_uri=avatar_uri,
    )


def render_pack_images(
    img_root: Path,
    carousel: Iterable[dict],
    stories: Iterable[dict],
    static_post: dict | None = None,
    *,
    design_direction: str = "medical_modern",
    avatar_asset: dict[str, Any] | None = None,
) -> dict:
    """
    Gera as imagens prontas para postar dentro de `img_root`:
      carrossel/carrossel-NN.png (1080x1350)
      stories/story-NN.png       (1080x1920)
      post-fixo.png              (1080x1080)
    """
    from playwright.sync_api import sync_playwright

    carousel = list(carousel)
    stories = list(stories)
    avatar_uri = _asset_uri(avatar_asset)
    car_dir = img_root / "carrossel"
    sto_dir = img_root / "stories"
    car_dir.mkdir(parents=True, exist_ok=True)
    sto_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            total = len(carousel)
            for i, slide in enumerate(carousel, start=1):
                doc = _slide_html(
                    slide,
                    index=i,
                    total=total,
                    width=1080,
                    height=1350,
                    design_direction=design_direction,
                    avatar_uri=avatar_uri,
                )
                page.set_content(doc, wait_until="load")
                page.wait_for_timeout(220)
                page.screenshot(path=str(car_dir / f"carrossel-{i:02d}.png"))
                generated += 1

            if static_post:
                page.set_viewport_size({"width": 1080, "height": 1080})
                page.set_content(
                    _static_post_html(
                        static_post,
                        design_direction=design_direction,
                        avatar_uri=avatar_uri,
                        width=1080,
                        height=1080,
                    ),
                    wait_until="load",
                )
                page.wait_for_timeout(220)
                page.screenshot(path=str(img_root / "post-fixo.png"))
                generated += 1

            page.set_viewport_size({"width": 1080, "height": 1920})
            total_stories = len(stories)
            for i, story in enumerate(stories, start=1):
                doc = _slide_html(
                    story,
                    index=i,
                    total=total_stories,
                    width=1080,
                    height=1920,
                    design_direction=design_direction,
                    avatar_uri=avatar_uri,
                    story=True,
                )
                page.set_content(doc, wait_until="load")
                page.wait_for_timeout(220)
                page.screenshot(path=str(sto_dir / f"story-{i:02d}.png"))
                generated += 1
        finally:
            browser.close()

    return {"images": generated}
