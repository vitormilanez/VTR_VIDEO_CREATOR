#!/usr/bin/env python3
"""Renderer deterministico do carrossel Instituto Guilherme Martins.

Claude entrega apenas ``{layoutId, variant, fields}``. Este modulo aplica os
tokens da marca, resolve fotos locais e exporta PNG 1080x1350, tamanho padrao
para carrossel 4:5 no Instagram.
"""
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from typing import Any, Iterable

from api.pack_design import (
    LAYOUT_SPECS,
    PACK_FAMILIES,
    PACK_LAYOUTS,
    PACK_THEMES,
    PHOTO_LIBRARY,
    normalize_slide,
    photo_asset,
)
from api.services.medical_identity import (
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
    MEDICAL_ROLE_AND_REGISTERED_SPECIALTY,
    safe_editorial_cta,
)

ROOT = Path(__file__).resolve().parent.parent

COLORS = {
    "dark": "#0A1A2F",
    "deep": "#06121F",
    "light": "#F4F2ED",
    "warm": "#E9E4DA",
    "white": "#FFFFFF",
    "teal": "#12B2A6",
    "sand": "#C8A96A",
    "body_dark": "#3E5165",
    "body_light": "#B7C4D0",
    "muted": "#8496A8",
    "footer_dark": "#5D6E80",
    "subtle": "#63768A",
}

MODERNIST_COLORS = {
    "dark": "#171717",
    "deep": "#0C0C0C",
    "light": "#F4EFE6",
    "warm": "#E7DED1",
    "white": "#FFFFFF",
    "teal": "#C8392B",
    "sand": "#E36A54",
    "body_dark": "#3E3833",
    "body_light": "#E9DFD2",
    "muted": "#9A8E80",
    "footer_dark": "#675E55",
    "subtle": "#74685D",
}

SOFT_SAGE_COLORS = {
    "dark": "#28443E",
    "deep": "#1B322D",
    "light": "#F3F4EE",
    "warm": "#E5E7D9",
    "white": "#FFFFFF",
    "teal": "#86A996",
    "sand": "#C6AE86",
    "body_dark": "#536960",
    "body_light": "#D5E1DB",
    "muted": "#97AAA1",
    "footer_dark": "#71877D",
    "subtle": "#82948C",
}

SOFT_ROSE_COLORS = {
    "dark": "#513944",
    "deep": "#34252D",
    "light": "#FBF5F2",
    "warm": "#F0E3DD",
    "white": "#FFFFFF",
    "teal": "#C78B93",
    "sand": "#D9B79D",
    "body_dark": "#725D65",
    "body_light": "#EADADF",
    "muted": "#B59DA5",
    "footer_dark": "#907980",
    "subtle": "#A79198",
}

THEME_COLOR_SETS = {
    "modernist-red": MODERNIST_COLORS,
    "soft-sage": SOFT_SAGE_COLORS,
    "soft-rose": SOFT_ROSE_COLORS,
}

FONT_ARCHIVO = ROOT / "assets/fonts/archivo/archivo-latin-wght-normal.woff2"
FONT_INSTRUMENT = ROOT / "assets/fonts/instrument-serif/instrument-serif-latin-400-italic.woff2"


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _data_uri(path: Path) -> str:
    if not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _font_css() -> str:
    archivo = _data_uri(FONT_ARCHIVO)
    instrument = _data_uri(FONT_INSTRUMENT)
    if not archivo or not instrument:
        raise RuntimeError("Fontes locais do Pack nao foram encontradas em assets/fonts.")
    return f"""
    @font-face {{ font-family:'Archivo'; src:url('{archivo}') format('woff2'); font-style:normal; font-weight:400 800; font-display:block; }}
    @font-face {{ font-family:'Instrument Serif'; src:url('{instrument}') format('woff2'); font-style:italic; font-weight:400; font-display:block; }}
    """


def _photo(slide: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    normalized = normalize_slide(slide)
    fields = normalized["fields"]
    asset = normalized.get("photoAsset") if isinstance(normalized.get("photoAsset"), dict) else None
    if not asset:
        asset = photo_asset(str(fields.get("photoId") or ""))
    if not asset:
        return "", {}
    raw_path = str(asset.get("cachedAssetPath") or asset.get("file") or "")
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    meta = {**PHOTO_LIBRARY.get(str(fields.get("photoId") or asset.get("id") or ""), {}), **asset}
    return _data_uri(path), meta


def _brand(*, dark: bool = True, cta: bool = False) -> str:
    color = COLORS["light"] if dark else COLORS["dark"]
    size_institute = 22 if cta else 18
    size_name = 34 if cta else 26
    return (
        f'<div class="brand{(" brand-cta" if cta else "")}">'
        f'<div style="font-size:{size_institute}px">Instituto</div>'
        f'<strong style="font-size:{size_name}px;color:{color}">Guilherme Martins</strong>'
        "</div>"
    )


def _counter(index: int, total: int, *, light: bool = False) -> str:
    color = COLORS["body_light"] if light else COLORS["footer_dark"]
    return f'<div class="counter" style="color:{color}">{index:02d} / {total:02d}</div>'


def _headline_size(layout_id: str, headline: str, base: int) -> int:
    maximum = int(LAYOUT_SPECS.get(layout_id, {}).get("max", {}).get("headline", max(len(headline), 1)))
    ratio = len(headline) / max(maximum, 1)
    return base - 16 if ratio > 0.94 else base - 8 if ratio > 0.82 else base


def _copy_size(text: str, *, base: int, medium: int, small: int, medium_at: int, small_at: int) -> int:
    length = len(str(text or ""))
    if length >= small_at:
        return small
    if length >= medium_at:
        return medium
    return base


def _photo_markup(uri: str, meta: dict[str, Any], css_class: str = "photo") -> str:
    if not uri:
        return ""
    x = float(meta.get("facePointX") or 0.5) * 100
    y = float(meta.get("facePointY") or 0.25) * 100
    return f'<img class="{css_class}" src="{uri}" alt="Dr. Guilherme Martins" style="object-position:{x:.0f}% {y:.0f}%">'


def _overlay_alpha(meta: dict[str, Any], default: float = 0.28) -> float:
    return 0.45 if float(meta.get("brightness") or 0) > 0.5 else default


def _items(fields: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for name in ("item1", "item2", "item3"):
        value = fields.get(name)
        if isinstance(value, dict) and (value.get("title") or value.get("text")):
            result.append({"title": _esc(value.get("title")), "text": _esc(value.get("text"))})
    return result


def _cover_note(value: Any, *, overlay: bool = False) -> str:
    """Bloco opcional da capa, com fonte reduzida no browser até caber."""
    note = str(value or "").strip()
    if not note:
        return ""
    classes = "cover-note cover-note-overlay" if overlay else "cover-note"
    return (
        f'<aside class="{classes}"><p class="cover-note-text auto-fit" '
        f'data-max-font-size="44" data-min-font-size="24">{_esc(note)}</p></aside>'
    )


def _hero_photo(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    size = _headline_size("hero_photo", f["headline"], 98)
    return f"""
    <section class="slide hero-photo bg-dark">
      {_photo_markup(uri, meta)}<div class="hero-top-fade"></div><div class="hero-bottom-fade"></div>
      {_brand(dark=True)}
      <div class="hero-copy"><div class="accent-bar"></div><div class="eyebrow">{_esc(f['eyebrow'])}</div>
        <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div>
      {_cover_note(f.get('coverNote'))}
      <div class="footer-row"><span>{_esc(f['footer'] or 'Arraste para o lado')}</span>{_counter(index,total,light=True)}</div>
    </section>"""


def _photo_split(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    right = slide.get("variant") == "photo-right"
    size = _headline_size("photo_split", f["headline"], 76)
    photo = f'<div class="split-photo">{_photo_markup(uri, meta)}<div style="background:rgba(6,18,31,{_overlay_alpha(meta, .14)})"></div></div>'
    copy = f"""<div class="split-copy">{_brand(dark=False)}<div class="split-spacer"></div><div class="accent-bar small"></div>
      <div class="eyebrow">{_esc(f['eyebrow'])}</div><h1 style="font-size:{size}px">{_esc(f['headline'])}</h1>
      <p>{_esc(f['body'])}</p><div class="split-footer"><span>{_esc(f['footer'] or 'Dr. Guilherme Martins')}</span>{_counter(index,total)}</div></div>"""
    return f'<section class="slide photo-split bg-light">{copy + photo if right else photo + copy}</section>'


def _big_statement(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    light = slide.get("variant") == "light"
    size = _headline_size("big_statement", f["headline"], 90)
    eyebrow = _esc(f.get("eyebrow") or "Ponto-chave")
    return f"""<section class="slide big-statement {'bg-light' if light else 'bg-dark'} {'light-text' if not light else ''}">
      {_brand(dark=not light)}<aside class="statement-index" aria-hidden="true"><strong>{index:02d}</strong><span>ideia-chave</span></aside>
      <div class="statement-copy"><div class="eyebrow">{eyebrow}</div><div class="accent-bar"></div><h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div>
      <div class="statement-footer"><span>{_esc(f['footer'])}</span>{_counter(index,total,light=not light)}</div></section>"""


def _question(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    dark = slide.get("variant") == "dark"
    size = _headline_size("question", f["headline"], 82)
    supporting_copy = (
        f'<div class="question-answer"><p>{_esc(f["body"])}</p></div>' if str(f.get("body") or "").strip() else ""
    )
    return f"""<section class="slide question {'bg-dark light-text' if dark else 'bg-light'}">
      {_brand(dark=dark)}<aside class="question-guide" aria-hidden="true"><span>Dúvida comum</span><div class="question-mark">?</div></aside>
      <div class="question-copy"><div class="question-label"><span>{index:02d}</span><div class="eyebrow">{_esc(f['eyebrow'] or 'Pergunta frequente')}</div></div>
        <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1>{supporting_copy}</div>
      <div class="footer-row"><span>{_esc(f['footer'] or 'Resposta no próximo card')}</span>{_counter(index,total,light=dark)}</div></section>"""


def _myth_fact(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    myth = f["item1"]
    fact = f["item2"]
    myth_text = _esc(myth.get("text"))
    fact_text = _esc(fact.get("text"))
    myth_size = _copy_size(str(myth.get("text") or ""), base=66, medium=58, small=50, medium_at=28, small_at=36)
    fact_size = _copy_size(str(fact.get("text") or ""), base=66, medium=58, small=50, medium_at=28, small_at=36)
    return f"""<section class="slide myth-fact bg-light"><div class="myth-panel">{_brand(dark=True)}
      <div class="label label-myth">{_esc(myth.get('title') or 'Mito')}</div><h2 style="font-size:{myth_size}px">{myth_text}</h2></div>
      <div class="split-accent"></div><div class="fact-panel"><div class="label label-fact">{_esc(fact.get('title') or 'Fato')}</div>
      <h2 style="font-size:{fact_size}px">{fact_text}</h2><p>{_esc(f['body'])}</p><div class="fact-counter">{_counter(index,total)}</div></div></section>"""


def _number_stat(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    dark = slide.get("variant") == "dark"
    statistic = _esc(f["statistic"])
    supporting_copy = f'<p>{_esc(f["body"])}</p>' if str(f.get("body") or "").strip() else ""
    return f"""<section class="slide number-stat {'bg-dark light-text' if dark else 'bg-light'}">{_brand(dark=dark)}
      <div class="stat-copy"><div class="eyebrow">{_esc(f['eyebrow'])}</div><div class="stat-figure"><div class="statistic">{statistic}</div><div class="stat-guide"></div></div>
      <div class="stat-reading"><h1>{_esc(f['headline'])}</h1>{supporting_copy}</div></div>
      <div class="footer-row"><span>{_esc(f['caption'])}</span>{_counter(index,total,light=dark)}</div></section>"""


def _three_points(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    light = slide.get("variant") == "light"
    rows = "".join(
        f'<div class="point-row"><div class="point-number">{idx:02d}</div><div><h3>{item["title"]}</h3><p>{item["text"]}</p></div></div>'
        for idx, item in enumerate(_items(f), start=1)
    )
    return f"""<section class="slide three-points {'bg-light' if light else 'bg-dark light-text'}">{_brand(dark=not light)}
      <div class="three-copy"><div class="eyebrow">{_esc(f.get('eyebrow') or 'Em prática')}</div><h1>{_esc(f['headline'])}</h1><div class="points">{rows}</div></div><div class="bottom-counter">{_counter(index,total,light=not light)}</div></section>"""


def _explainer(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    items = _items(f)[:3]
    steps = "".join(
        '<article class="step {}"><span>{:02d}</span><strong>{}</strong>{}</article>'.format(
            "step-final" if idx == len(items) else "",
            idx,
            item["title"] or item["text"],
            f"<p>{item['text']}</p>" if item["text"] else "",
        )
        for idx, item in enumerate(items, start=1)
    )
    return f"""<section class="slide explainer bg-light">{_brand(dark=False)}<div class="explainer-copy">
      <div class="eyebrow">{_esc(f['eyebrow'] or 'Como funciona')}</div><h1>{_esc(f['headline'])}</h1><p>{_esc(f['body'])}</p>
      <div class="steps">{steps}</div></div><div class="explainer-footer"><span>{_esc(f['disclaimer'])}</span>{_counter(index,total)}</div></section>"""


def _doctor_quote(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    dark = slide.get("variant") == "dark"
    uri, meta = _photo(slide)
    caption = _esc(f["caption"])
    if caption.casefold().replace(".", "") in {"dr guilherme martins", "guilherme martins"}:
        caption = MEDICAL_ROLE_AND_REGISTERED_SPECIALTY
    return f"""<section class="slide doctor-quote {'bg-dark light-text' if dark else 'bg-warm'}">{_brand(dark=dark)}
      <div class="quote-copy"><div class="opening-quote">“</div><blockquote>{_esc(f['quote'])}</blockquote></div>
      <div class="quote-footer">{_photo_markup(uri, meta, 'quote-photo')}<div><strong>Dr. Guilherme Martins</strong><span>{caption}</span></div>
      <div class="quote-counter">{_counter(index,total,light=dark)}</div></div></section>"""


def _photo_overlay(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    size = _headline_size("photo_overlay", f["headline"], 84)
    top = slide.get("variant") == "text-top"
    has_cover_note = bool(str(f.get("coverNote") or "").strip())
    copy_classes = "overlay-copy" + (" overlay-copy-top" if top else "") + (
        " overlay-copy-with-note" if top and has_cover_note else ""
    )
    return f"""<section class="slide photo-overlay bg-deep">{_photo_markup(uri, meta)}<div class="photo-gradient"></div>{_brand(dark=True)}
      <div class="{copy_classes}"><div class="accent-bar"></div><div class="eyebrow">{_esc(f['eyebrow'])}</div>
      <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div>{_cover_note(f.get('coverNote'), overlay=True)}<div class="footer-row"><span>{_esc(f['footer'])}</span>{_counter(index,total,light=True)}</div></section>"""


def _do_dont(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    items = _items(f)
    avoids = "".join(f'<div class="compare-item">{item["title"]}</div>' for item in items)
    prefers = "".join(f'<div class="compare-item">{item["text"]}</div>' for item in items)
    return f"""<section class="slide do-dont"><div class="avoid-panel">{_brand(dark=True)}<div class="compare-spacer"></div>
      <div class="compare-label muted-label">Evite</div><div class="compare-list">{avoids}</div><div class="compare-note">{_esc(f['disclaimer'] or 'Conteúdo educativo.')}</div></div>
      <div class="prefer-panel"><div class="prefer-spacer"></div><div class="compare-label">Prefira</div><div class="compare-list">{prefers}</div>
      <div class="compare-counter">{_counter(index,total)}</div></div></section>"""


def _cta_photo(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    left = slide.get("variant") == "photo-left"
    size = _headline_size("cta_photo", f["headline"], 82)
    body_size = _copy_size(str(f.get("body") or ""), base=32, medium=28, small=25, medium_at=52, small_at=66)
    return f"""<section class="slide cta-photo bg-dark {'photo-left' if left else ''}">{_photo_markup(uri, meta)}<div class="cta-fade"></div>
      {_brand(dark=True,cta=True)}<div class="cta-copy"><div class="accent-bar"></div><h1 style="font-size:{size}px">{_esc(f['headline'])}</h1>
      <p style="font-size:{body_size}px">{_esc(f['body'])}</p><div class="cta-pill">{_esc(safe_editorial_cta(f['cta']))}</div></div>
      <div class="cta-footer"><div class="cta-compliance"><span>{_esc(MEDICAL_EDUCATIONAL_DISCLAIMER)}</span><strong>{_esc(MEDICAL_PROFESSIONAL_IDENTIFICATION)}</strong></div>{_counter(index,total,light=True)}</div></section>"""


RENDERERS = {
    "hero_photo": _hero_photo,
    "photo_split": _photo_split,
    "big_statement": _big_statement,
    "question": _question,
    "myth_fact": _myth_fact,
    "number_stat": _number_stat,
    "three_points": _three_points,
    "explainer": _explainer,
    "doctor_quote": _doctor_quote,
    "photo_overlay": _photo_overlay,
    "do_dont": _do_dont,
    "cta_photo": _cta_photo,
}


def _css() -> str:
    template = r"""
    {_font_css()}
    *{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1350px;overflow:hidden}}body{{font-family:Archivo,Arial,sans-serif}}
    .slide{{position:relative;width:1080px;height:1350px;overflow:hidden}}.bg-dark{{background:{COLORS['dark']}}}.bg-deep{{background:{COLORS['deep']}}}
    .bg-light{{background:{COLORS['light']};color:{COLORS['dark']}}}.bg-warm{{background:{COLORS['warm']};color:{COLORS['dark']}}}.light-text{{color:#fff}}
    .brand{{position:absolute;z-index:8;left:80px;top:96px;display:flex;flex-direction:column;gap:6px;text-transform:uppercase}}
    .brand div{{font-weight:600;line-height:1;letter-spacing:.42em;color:{COLORS['teal']}}}.brand strong{{font-weight:700;line-height:1;letter-spacing:.06em}}
    .counter{{font-size:24px;font-weight:500;line-height:1.4;letter-spacing:.14em;white-space:nowrap}}.eyebrow{{font-size:26px;font-weight:600;line-height:1.2;letter-spacing:.18em;text-transform:uppercase;color:{COLORS['teal']}}}
    h1,h2,h3,p{{margin:0}}h1,h2,h3{{text-wrap:balance}}p{{text-wrap:pretty}}.accent-bar{{width:120px;height:10px;background:{COLORS['teal']}}.accent-bar.small{{width:96px}}
    .footer-row{{position:absolute;z-index:8;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:center;font-size:24px;font-weight:500;line-height:1.4;color:{COLORS['body_light']}}}.question.bg-light .footer-row,.number-stat.bg-light .footer-row{{color:{COLORS['footer_dark']}}}
    .hero-photo>.photo{{position:absolute;left:0;top:430px;width:1080px;height:920px;object-fit:cover}}.hero-top-fade{{position:absolute;left:0;top:430px;width:1080px;height:300px;background:linear-gradient(180deg,{COLORS['dark']} 0%,rgba(10,26,47,0) 100%)}}
    .hero-bottom-fade{{position:absolute;left:0;bottom:0;width:1080px;height:360px;background:linear-gradient(180deg,rgba(6,18,31,0),rgba(6,18,31,.9))}}.hero-copy{{position:absolute;z-index:5;left:80px;top:250px;width:920px;display:flex;flex-direction:column;gap:32px}}.hero-copy h1{{font-weight:800;line-height:.94;letter-spacing:-.035em;color:#fff}}.cover-note{{position:absolute;z-index:7;left:80px;bottom:174px;width:520px;height:232px;padding:28px 30px;border:1px solid rgba(244,242,237,.32);border-radius:18px;background:rgba(6,18,31,.78);box-shadow:0 16px 38px rgba(6,18,31,.25);display:flex;align-items:center}}.cover-note-text{{width:100%;height:176px;overflow:hidden;overflow-wrap:anywhere;font-weight:700;line-height:1.1;letter-spacing:-.02em;color:#fff;white-space:pre-wrap}}.cover-note-overlay{{top:350px;bottom:auto}}.overlay-copy-top.overlay-copy-with-note{{top:650px}}
    .photo-split{{display:flex}}.split-photo{{position:relative;width:486px;height:1350px;flex:none}}.split-photo img,.split-photo div{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.split-copy{{position:relative;flex:1;padding:96px 80px 88px 72px;display:flex;flex-direction:column}}.split-copy .brand{{position:static}}.split-spacer{{height:88px;flex:none}}.split-copy .eyebrow{{margin-top:32px}}.split-copy h1{{margin-top:28px;font-weight:800;line-height:1;letter-spacing:-.03em}}.split-copy p{{margin-top:40px;font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}}.split-footer{{margin-top:auto;display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(10,26,47,.14);padding-top:28px;font-size:24px;color:{COLORS['footer_dark']}}}
    .statement-copy{{position:absolute;left:80px;right:80px;top:380px;display:flex;flex-direction:column;gap:44px}}.statement-copy h1{{font-weight:800;line-height:.94;letter-spacing:-.04em}}.statement-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:flex-end;border-top:1px solid rgba(10,26,47,.14);padding-top:32px;font-size:30px;line-height:1.4;color:{COLORS['body_dark']}}.big-statement.light-text .statement-footer{{border-color:rgba(244,242,237,.14);color:{COLORS['body_light']}}}.statement-footer>span{{max-width:640px}}
    .question-copy{{position:absolute;left:80px;right:80px;top:440px;display:flex;flex-direction:column;gap:48px}}.question-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.035em}}.question-copy p{{max-width:820px;font-size:36px;line-height:1.5;color:{COLORS['body_dark']}}.question.light-text .question-copy p{{color:{COLORS['body_light']}}}
    .myth-fact{{display:flex;flex-direction:column}}.myth-panel{{height:620px;background:{COLORS['dark']};padding:96px 80px 64px;display:flex;flex-direction:column;gap:36px;position:relative}}.myth-panel .brand{{position:static}}.label{{display:inline-flex;align-self:flex-start;padding:14px 24px;border-radius:4px;font-size:24px;font-weight:700;line-height:1;letter-spacing:.24em;text-transform:uppercase;color:{COLORS['dark']}}.label-myth{{background:{COLORS['muted']}}}.label-fact{{background:{COLORS['sand']}}}.myth-panel h2,.fact-panel h2{{font-size:72px;font-weight:800;line-height:1.02;letter-spacing:-.025em}}.myth-panel h2{{color:{COLORS['light']}}}.split-accent{{height:8px;background:{COLORS['teal']}}.fact-panel{{position:relative;flex:1;padding:64px 80px 120px;display:flex;flex-direction:column;gap:36px}}.fact-panel p{{font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}.fact-counter{{position:absolute;right:80px;bottom:88px}}
    .stat-copy{{position:absolute;left:80px;right:80px;top:300px;display:flex;flex-direction:column;gap:24px}}.statistic{{font-size:270px;font-weight:800;line-height:.82;letter-spacing:-.055em;color:{COLORS['teal']}}.hairline{{height:1px;background:rgba(10,26,47,.16);margin-top:18px}}.number-stat.light-text .hairline{{background:rgba(244,242,237,.16)}}.stat-copy h1{{max-width:880px;font-size:58px;font-weight:700;line-height:1.08;letter-spacing:-.02em}}.stat-copy p{{max-width:820px;font-size:32px;line-height:1.5;color:{COLORS['body_dark']}}.number-stat.light-text .stat-copy p{{color:{COLORS['body_light']}}}
    .three-copy{{position:absolute;left:80px;right:80px;top:240px}}.three-copy>h1{{max-width:860px;font-size:68px;font-weight:800;line-height:1.02;letter-spacing:-.025em}}.points{{margin-top:64px;display:flex;flex-direction:column;gap:38px}}.point-row{{display:flex;gap:40px;align-items:flex-start;border-top:1px solid rgba(244,242,237,.14);padding-top:34px}}.three-points.bg-light .point-row{{border-color:rgba(10,26,47,.14)}}.point-number{{width:110px;flex:none;font-size:64px;font-weight:800;line-height:.9;letter-spacing:-.03em;color:{COLORS['teal']}}.point-row h3{{font-size:43px;font-weight:700;line-height:1.1;letter-spacing:-.02em}}.point-row p{{margin-top:12px;font-size:28px;line-height:1.4;color:{COLORS['body_light']}}.three-points.bg-light .point-row p{{color:{COLORS['body_dark']}}}.bottom-counter{{position:absolute;right:80px;bottom:88px}}
    .explainer-copy{{position:absolute;left:80px;right:80px;top:260px}}.explainer-copy h1{{margin-top:28px;max-width:880px;font-size:66px;font-weight:800;line-height:1.03;letter-spacing:-.025em}}.explainer-copy>p{{margin-top:36px;max-width:880px;font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}.steps{{margin-top:72px;display:flex;align-items:center;gap:24px}}.steps i{{flex:1;height:2px;background:rgba(10,26,47,.18)}}.step{{width:250px;height:150px;padding:0 28px;border-radius:12px;background:{COLORS['dark']};display:flex;flex-direction:column;justify-content:center;gap:8px;color:#fff}}.step span{{font-size:20px;font-weight:600;letter-spacing:.2em;color:{COLORS['teal']}}}.step strong{{font-size:32px;line-height:1.1}}.step-final{{background:{COLORS['teal']};color:{COLORS['deep']}}}.step-final span{{color:{COLORS['deep']}}}.explainer-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(10,26,47,.14);padding-top:28px;font-size:22px;color:{COLORS['footer_dark']}}}
    .quote-copy{{position:absolute;left:80px;right:80px;top:285px}}.opening-quote{{height:110px;font-family:'Instrument Serif';font-size:200px;line-height:.6;color:{COLORS['sand']}}blockquote{{max-width:900px;margin:0;font-family:'Instrument Serif';font-style:italic;font-size:82px;line-height:1.14;text-wrap:balance}}.quote-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;align-items:center;gap:32px;border-top:1px solid rgba(10,26,47,.16);padding-top:40px}}.doctor-quote.light-text .quote-footer{{border-color:rgba(244,242,237,.16)}}.quote-photo{{width:150px;height:150px;flex:none;border-radius:999px;object-fit:cover}}.quote-footer>div:not(.quote-counter):not(.counter){{display:flex;flex-direction:column;gap:8px}}.quote-footer strong{{font-size:38px;line-height:1.1}}.quote-footer span{{font-size:26px;line-height:1.3;color:{COLORS['footer_dark']}}.doctor-quote.light-text .quote-footer span{{color:{COLORS['body_light']}}}.quote-counter{{margin-left:auto}}
    .photo-overlay>.photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.photo-gradient{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,18,31,.75) 0%,rgba(6,18,31,0) 38%,rgba(6,18,31,.9) 100%)}}.overlay-copy{{position:absolute;z-index:5;left:80px;right:80px;bottom:180px;display:flex;flex-direction:column;gap:32px}}.overlay-copy-top{{top:280px;bottom:auto}}.overlay-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.03em;color:#fff}}
    .do-dont{{display:flex}}.avoid-panel,.prefer-panel{{position:relative;width:540px;padding:96px 48px 88px 80px;display:flex;flex-direction:column}}.avoid-panel{{background:{COLORS['dark']};color:{COLORS['light']}}}.prefer-panel{{background:{COLORS['light']};color:{COLORS['dark']};padding-left:48px;padding-right:80px}}.avoid-panel .brand{{position:static}}.compare-spacer{{height:120px}}.prefer-spacer{{height:167px}}.compare-label{{font-size:26px;font-weight:700;letter-spacing:.24em;text-transform:uppercase;color:{COLORS['teal']}}.muted-label{{color:{COLORS['muted']}}.compare-list{{margin-top:44px;display:flex;flex-direction:column;gap:36px}}.compare-item{{padding-top:32px;border-top:1px solid rgba(10,26,47,.16);font-size:40px;font-weight:600;line-height:1.15;letter-spacing:-.015em}}.avoid-panel .compare-item{{border-color:rgba(244,242,237,.16)}}.compare-note,.compare-counter{{margin-top:auto;font-size:22px;color:{COLORS['subtle']}}.compare-counter{{margin-left:auto}}
    .cta-photo>.photo{{position:absolute;right:0;top:0;width:600px;height:1350px;object-fit:cover}}.cta-photo.photo-left>.photo{{left:0;right:auto}}.cta-fade{{position:absolute;right:0;top:0;width:600px;height:1350px;background:linear-gradient(90deg,{COLORS['dark']} 0%,rgba(10,26,47,.65) 34%,rgba(10,26,47,.18) 100%)}}.photo-left .cta-fade{{left:0;right:auto;transform:scaleX(-1)}}.cta-copy{{position:absolute;z-index:5;left:80px;top:500px;width:650px;display:flex;flex-direction:column;gap:34px}}.photo-left .cta-copy{{left:350px}}.cta-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.03em;color:#fff}}.cta-copy p{{font-size:32px;line-height:1.45;color:{COLORS['body_light']}}.cta-pill{{display:inline-flex;align-self:flex-start;padding:28px 44px;border-radius:999px;background:{COLORS['teal']};color:{COLORS['deep']};font-size:32px;font-weight:700;line-height:1}}.cta-footer{{position:absolute;z-index:6;left:80px;right:80px;bottom:48px;display:flex;justify-content:space-between;align-items:flex-end;gap:24px;border-top:1px solid rgba(244,242,237,.16);padding-top:22px;color:{COLORS['muted']}}.cta-compliance{{max-width:800px;display:flex;flex-direction:column;gap:10px}}.cta-compliance span{{color:{COLORS['body_light']};font-size:24px;line-height:1.36;font-weight:560}}.cta-compliance strong{{color:#fff;font-size:24px;line-height:1.38;font-weight:700;letter-spacing:-.012em}}
    html[data-family='manifesto'] .brand{{top:72px}}html[data-family='manifesto'] .brand div{{display:inline-flex;align-self:flex-start;padding:10px 14px;background:{COLORS['teal']};color:{COLORS['deep']};letter-spacing:.18em}}html[data-family='manifesto'] .brand strong{{padding-left:2px;letter-spacing:.035em}}html[data-family='manifesto'] .accent-bar{{width:176px;height:16px}}html[data-family='manifesto'] .hero-photo>.photo,html[data-family='manifesto'] .photo-overlay>.photo,html[data-family='manifesto'] .cta-photo>.photo,html[data-family='manifesto'] .split-photo img,html[data-family='manifesto'] .quote-photo{{filter:grayscale(.92) contrast(1.18)}}html[data-family='manifesto'] .cover-note,html[data-family='manifesto'] .label,html[data-family='manifesto'] .step,html[data-family='manifesto'] .cta-pill{{border-radius:0}}html[data-family='manifesto'] .question-mark{{color:rgba(18,178,166,.19)}}html[data-family='manifesto'] .statement-copy h1,html[data-family='manifesto'] .hero-copy h1{{letter-spacing:-.055em}}
    html[data-family='clinico'] .bg-light{{background-image:linear-gradient(rgba(18,178,166,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(18,178,166,.045) 1px,transparent 1px);background-size:48px 48px}}html[data-family='clinico'] .brand div{{font-size:18px;letter-spacing:.28em}}html[data-family='clinico'] .accent-bar{{width:72px;height:8px;border-radius:999px}}html[data-family='clinico'] .hero-photo>.photo,html[data-family='clinico'] .photo-overlay>.photo,html[data-family='clinico'] .cta-photo>.photo,html[data-family='clinico'] .split-photo img,html[data-family='clinico'] .quote-photo{{filter:saturate(.72) contrast(.94)}}html[data-family='clinico'] .cover-note{{border-radius:12px;background:rgba(6,18,31,.88);box-shadow:none}}html[data-family='clinico'] .step{{border:1px solid rgba(18,178,166,.35);border-radius:16px;box-shadow:0 18px 38px rgba(6,18,31,.12)}}html[data-family='clinico'] .label{{border-radius:999px}}html[data-family='clinico'] .question-mark{{font-size:600px;color:rgba(18,178,166,.07)}}html[data-family='clinico'] .hairline{{background:rgba(18,178,166,.42)}}html[data-family='clinico'] .cta-pill{{border-radius:14px;box-shadow:0 12px 24px rgba(6,18,31,.20)}}
    """
    template += r"""
    /* Sistema didático: leitura em blocos, contraste calmo e nenhum elemento decorativo dominante. */
    .big-statement .statement-index{position:absolute;z-index:4;right:80px;top:318px;width:172px;padding:22px 0 18px;border-top:2px solid rgba(10,26,47,.22);display:flex;flex-direction:column;gap:6px}.big-statement.light-text .statement-index{border-color:rgba(244,242,237,.3)}.statement-index strong{font-size:58px;font-weight:700;line-height:.82;letter-spacing:-.05em}.statement-index span{font-size:17px;font-weight:700;line-height:1.2;letter-spacing:.16em;text-transform:uppercase;color:{COLORS['teal']}}.statement-copy{right:304px;top:336px;gap:26px}.statement-copy .accent-bar{width:84px;height:8px}.statement-copy h1{line-height:.98;letter-spacing:-.038em}.statement-footer{padding-top:24px;font-size:25px}.statement-footer>span{max-width:590px}
    .question-guide{position:absolute;z-index:4;right:80px;top:300px;width:224px;height:416px;padding:30px 28px 22px;border:1px solid rgba(10,26,47,.16);border-radius:24px;background:{COLORS['warm']};display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}.question-guide>span{font-size:18px;font-weight:700;line-height:1.2;letter-spacing:.16em;text-transform:uppercase;color:{COLORS['body_dark']}}.question-guide .question-mark{position:static;align-self:flex-end;font-size:212px;font-weight:700;line-height:.72;letter-spacing:-.09em;color:{COLORS['teal']}}.question-copy{left:80px;right:350px;top:316px;gap:28px}.question-label{display:flex;align-items:center;gap:18px}.question-label>span{display:inline-flex;align-items:center;justify-content:center;width:44px;height:34px;border-radius:999px;background:{COLORS['dark']};color:{COLORS['light']};font-size:16px;font-weight:700;letter-spacing:.1em}.question-copy h1{line-height:1.01;letter-spacing:-.034em}.question-answer{max-width:650px;margin-top:4px;padding:28px 30px;border-left:7px solid {COLORS['teal']};border-radius:0 18px 18px 0;background:rgba(10,26,47,.055)}.question-copy .question-answer p{max-width:none;font-size:31px;line-height:1.42;color:{COLORS['body_dark']}}.question .footer-row,.number-stat .footer-row{padding-top:24px;border-top:1px solid rgba(10,26,47,.14)}.question.light-text .question-guide{border-color:rgba(244,242,237,.18);background:rgba(244,242,237,.08)}.question.light-text .question-guide>span{color:{COLORS['body_light']}}.question.light-text .question-label>span{background:{COLORS['light']};color:{COLORS['dark']}}.question.light-text .question-answer{background:rgba(244,242,237,.08);border-color:{COLORS['teal']}}.question.light-text .question-answer p{color:{COLORS['body_light']}}.question.light-text .footer-row,.number-stat.light-text .footer-row{border-color:rgba(244,242,237,.16)}
    .stat-copy{top:286px;gap:18px}.stat-figure{display:flex;align-items:flex-end;gap:30px}.statistic{font-size:220px;line-height:.84}.stat-guide{flex:1;height:8px;margin-bottom:28px;background:{COLORS['teal']}}.stat-reading{max-width:860px;padding-top:30px;border-top:1px solid rgba(10,26,47,.16);display:flex;flex-direction:column;gap:18px}.number-stat.light-text .stat-reading{border-color:rgba(244,242,237,.16)}.stat-copy h1{max-width:800px;font-size:56px;line-height:1.1}.stat-reading p{max-width:780px;font-size:30px;line-height:1.45;color:{COLORS['body_dark']}}.number-stat.light-text .stat-reading p{color:{COLORS['body_light']}}
    .three-copy{top:252px}.three-copy>h1{margin-top:22px;font-size:64px;line-height:1.05}.points{margin-top:48px;gap:30px}.point-row{gap:34px;padding-top:28px}.point-number{width:116px;font-size:58px}.point-row h3{font-size:40px}.point-row p{margin-top:10px;font-size:27px}
    .explainer-copy{top:246px}.explainer-copy h1{margin-top:24px;font-size:62px;line-height:1.06}.explainer-copy>p{margin-top:28px;max-width:900px;font-size:30px;line-height:1.46}.steps{margin-top:52px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.steps i{display:none}.step{width:auto;height:246px;padding:28px 26px;border:1px solid rgba(10,26,47,.14);border-radius:20px;background:{COLORS['white']};display:flex;flex-direction:column;justify-content:flex-start;gap:10px;color:{COLORS['dark']};box-shadow:0 14px 28px rgba(10,26,47,.05)}.step span{font-size:18px;font-weight:700;letter-spacing:.16em;color:{COLORS['teal']}}.step strong{font-size:31px;line-height:1.08;letter-spacing:-.02em}.step p{font-size:22px;line-height:1.3;color:{COLORS['body_dark']}}.step-final{background:{COLORS['dark']};color:{COLORS['light']};border-color:{COLORS['dark']};box-shadow:none}.step-final span{color:{COLORS['teal']}}.step-final p{color:{COLORS['body_light']}}.explainer-footer{padding-top:24px}
    html[data-theme='soft-sage'] .bg-light .eyebrow,html[data-theme='soft-rose'] .bg-light .eyebrow{color:{COLORS['body_dark']}}html[data-family='manifesto'] .question-guide,html[data-family='manifesto'] .step{border-radius:0}html[data-family='clinico'] .question-guide{border-radius:16px;box-shadow:0 18px 38px rgba(10,26,47,.08)}html[data-family='clinico'] .step{border-radius:16px;box-shadow:0 18px 38px rgba(10,26,47,.10)}
    """
    for name, value in COLORS.items():
        template = template.replace("{COLORS['" + name + "']}", value)
    return template.replace("{_font_css()}", _font_css()).replace("{{", "{").replace("}}", "}")


def _rgba_prefix(color: str) -> str:
    return "rgba(" + ",".join(str(int(color[offset : offset + 2], 16)) for offset in (1, 3, 5))


def _apply_theme(document: str, theme_id: str) -> str:
    """Troca somente tokens fechados; conteúdo e composição permanecem intactos."""
    palette = THEME_COLOR_SETS.get(theme_id)
    if not palette:
        return document
    themed = document
    for name, source in COLORS.items():
        themed = themed.replace(source, palette[name])
    # Alguns overlays usam rgba para preservar opacidade sobre fotografia.
    for name in ("dark", "deep", "teal", "light"):
        themed = themed.replace(_rgba_prefix(COLORS[name]), _rgba_prefix(palette[name]))
    return themed


def slide_html(
    slide: dict[str, Any],
    *,
    index: int,
    total: int,
    family: str = "didatico",
    theme_id: str = "ocean-deep",
) -> str:
    normalized = normalize_slide(slide, index - 1)
    layout_id = normalized["layoutId"]
    if layout_id not in PACK_LAYOUTS:
        raise ValueError(f"Layout desconhecido: {layout_id}")
    resolved_family = family if family in PACK_FAMILIES else "didatico"
    resolved_theme = theme_id if theme_id in PACK_THEMES else "ocean-deep"
    body = RENDERERS[layout_id](normalized, index, total)
    document = (
        "<!doctype html>"
        f"<html lang='pt-BR' data-family='{resolved_family}' data-theme='{resolved_theme}'>"
        f"<head><meta charset='utf-8'><style>{_css()}</style></head><body>{body}<script>"
        "(function(){const fit=()=>document.querySelectorAll('.auto-fit').forEach((node)=>{"
        "const max=Number(node.dataset.maxFontSize||44);const min=Number(node.dataset.minFontSize||24);"
        "let size=max;node.style.fontSize=size+'px';"
        "while(size>min&&(node.scrollHeight>node.clientHeight+1||node.scrollWidth>node.clientWidth+1)){"
        "size-=1;node.style.fontSize=size+'px';}node.dataset.fittedFontSize=String(size);});"
        "if(document.fonts&&document.fonts.ready){document.fonts.ready.then(fit);}else{fit();}})();"
        f"</script></body></html>"
    )
    return _apply_theme(document, resolved_theme)


def _legacy_extra_html(title: str, body: str, *, width: int, height: int) -> str:
    template = """<!doctype html><html><head><meta charset='utf-8'><style>__FONTS__*{box-sizing:border-box}html,body{margin:0;width:__WIDTH__px;height:__HEIGHT__px;overflow:hidden}body{background:__DARK__;color:#fff;font-family:Archivo;padding:96px 80px;display:flex;flex-direction:column}.ey{color:__TEAL__;font-size:22px;letter-spacing:.2em;text-transform:uppercase}h1{margin:auto 0 32px;font-size:82px;line-height:1;font-weight:800}p{margin:0 0 auto;font-size:34px;line-height:1.5;color:__BODY_LIGHT__}small{font-size:20px;line-height:1.45;color:__MUTED__}small strong{display:block;margin-top:10px;color:#fff}</style></head><body><div class='ey'>Instituto Guilherme Martins</div><h1>__TITLE__</h1><p>__BODY__</p><small>__DISCLAIMER__<strong>__IDENTIFICATION__</strong></small></body></html>"""
    return (
        template.replace("__FONTS__", _font_css())
        .replace("__WIDTH__", str(width))
        .replace("__HEIGHT__", str(height))
        .replace("__DARK__", COLORS["dark"])
        .replace("__TEAL__", COLORS["teal"])
        .replace("__BODY_LIGHT__", COLORS["body_light"])
        .replace("__MUTED__", COLORS["muted"])
        .replace("__TITLE__", _esc(title))
        .replace("__BODY__", _esc(body))
        .replace("__DISCLAIMER__", _esc(MEDICAL_EDUCATIONAL_DISCLAIMER))
        .replace("__IDENTIFICATION__", _esc(MEDICAL_PROFESSIONAL_IDENTIFICATION))
    )


def render_pack_images(
    img_root: Path,
    carousel: Iterable[dict],
    stories: Iterable[dict] = (),
    static_post: dict[str, Any] | None = None,
    *,
    design_direction: str = "institute_carousel_v1",
    avatar_asset: dict[str, Any] | None = None,
    family: str = "didatico",
    theme_id: str = "ocean-deep",
    render_extras: bool = True,
) -> dict[str, Any]:
    """Renderiza carrossel 1080x1350 e, apenas para Packs legados, post/stories."""
    from playwright.sync_api import sync_playwright

    slides = list(carousel)
    story_rows = list(stories)
    car_dir = img_root / "carrossel"
    car_dir.mkdir(parents=True, exist_ok=True)
    generated = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1080, "height": 1350},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            for index, slide in enumerate(slides, start=1):
                page.set_content(
                    slide_html(
                        slide,
                        index=index,
                        total=len(slides),
                        family=family,
                        theme_id=theme_id,
                    ),
                    wait_until="networkidle",
                )
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(car_dir / f"carrossel-{index:02d}.png"))
                generated += 1

            if render_extras and static_post:
                page.set_viewport_size({"width": 1080, "height": 1080})
                page.set_content(
                    _legacy_extra_html(
                        str(static_post.get("headline") or ""),
                        str(static_post.get("subline") or ""),
                        width=1080,
                        height=1080,
                    ),
                    wait_until="networkidle",
                )
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(img_root / "post-fixo.png"))
                generated += 1

            if render_extras and story_rows:
                story_dir = img_root / "stories"
                story_dir.mkdir(parents=True, exist_ok=True)
                page.set_viewport_size({"width": 1080, "height": 1920})
                for index, story in enumerate(story_rows, start=1):
                    normalized = normalize_slide(story, index - 1)
                    fields = normalized["fields"]
                    page.set_content(
                        _legacy_extra_html(
                            str(fields.get("headline") or fields.get("eyebrow") or ""),
                            str(fields.get("body") or fields.get("subheadline") or ""),
                            width=1080,
                            height=1920,
                        ),
                        wait_until="networkidle",
                    )
                    page.evaluate("document.fonts.ready")
                    page.screenshot(path=str(story_dir / f"story-{index:02d}.png"))
                    generated += 1
        finally:
            context.close()
            browser.close()

    return {
        "images": generated,
        "carouselImages": len(slides),
        "width": 1080,
        "height": 1350,
        "scale": 1,
        "family": family,
        "themeId": theme_id,
    }
