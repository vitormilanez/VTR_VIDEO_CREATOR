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
    PACK_LAYOUTS,
    PHOTO_LIBRARY,
    normalize_slide,
    photo_asset,
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


def _hero_photo(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    size = _headline_size("hero_photo", f["headline"], 108)
    return f"""
    <section class="slide hero-photo bg-dark">
      {_photo_markup(uri, meta)}<div class="hero-top-fade"></div><div class="hero-bottom-fade"></div>
      {_brand(dark=True)}
      <div class="hero-copy"><div class="accent-bar"></div><div class="eyebrow">{_esc(f['eyebrow'])}</div>
        <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div>
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
    size = _headline_size("big_statement", f["headline"], 112)
    return f"""<section class="slide big-statement {'bg-light' if light else 'bg-dark'} {'light-text' if not light else ''}">
      {_brand(dark=not light)}<div class="statement-copy"><div class="accent-bar"></div><h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div>
      <div class="statement-footer"><span>{_esc(f['footer'])}</span>{_counter(index,total,light=not light)}</div></section>"""


def _question(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    dark = slide.get("variant") == "dark"
    size = _headline_size("question", f["headline"], 96)
    return f"""<section class="slide question {'bg-dark light-text' if dark else 'bg-light'}">
      <div class="question-mark">?</div>{_brand(dark=dark)}
      <div class="question-copy"><div class="eyebrow">{_esc(f['eyebrow'] or 'Pergunta frequente')}</div>
        <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1><p>{_esc(f['body'])}</p></div>
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
    return f"""<section class="slide number-stat {'bg-dark light-text' if dark else 'bg-light'}">{_brand(dark=dark)}
      <div class="stat-copy"><div class="eyebrow">{_esc(f['eyebrow'])}</div><div class="statistic">{statistic}</div><div class="hairline"></div>
      <h1>{_esc(f['headline'])}</h1><p>{_esc(f['body'])}</p></div>
      <div class="footer-row"><span>{_esc(f['caption'])}</span>{_counter(index,total,light=dark)}</div></section>"""


def _three_points(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    light = slide.get("variant") == "light"
    rows = "".join(
        f'<div class="point-row"><div class="point-number">{idx:02d}</div><div><h3>{item["title"]}</h3><p>{item["text"]}</p></div></div>'
        for idx, item in enumerate(_items(f), start=1)
    )
    return f"""<section class="slide three-points {'bg-light' if light else 'bg-dark light-text'}">{_brand(dark=not light)}
      <div class="three-copy"><h1>{_esc(f['headline'])}</h1><div class="points">{rows}</div></div><div class="bottom-counter">{_counter(index,total,light=not light)}</div></section>"""


def _explainer(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    items = _items(f)[:3]
    steps = "".join(
        f'<div class="step {"step-final" if idx == len(items) else ""}"><span>ETAPA {idx}</span><strong>{item["title"] or item["text"]}</strong></div>{"<i></i>" if idx < len(items) else ""}'
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
        caption = "Endocrinologia e Metabologia"
    return f"""<section class="slide doctor-quote {'bg-dark light-text' if dark else 'bg-warm'}">{_brand(dark=dark)}
      <div class="quote-copy"><div class="opening-quote">“</div><blockquote>{_esc(f['quote'])}</blockquote></div>
      <div class="quote-footer">{_photo_markup(uri, meta, 'quote-photo')}<div><strong>Dr. Guilherme Martins</strong><span>{caption}</span></div>
      <div class="quote-counter">{_counter(index,total,light=dark)}</div></div></section>"""


def _photo_overlay(slide: dict[str, Any], index: int, total: int) -> str:
    f = slide["fields"]
    uri, meta = _photo(slide)
    size = _headline_size("photo_overlay", f["headline"], 84)
    top = slide.get("variant") == "text-top"
    return f"""<section class="slide photo-overlay bg-deep">{_photo_markup(uri, meta)}<div class="photo-gradient"></div>{_brand(dark=True)}
      <div class="overlay-copy {'overlay-copy-top' if top else ''}"><div class="accent-bar"></div><div class="eyebrow">{_esc(f['eyebrow'])}</div>
      <h1 style="font-size:{size}px">{_esc(f['headline'])}</h1></div><div class="footer-row"><span>{_esc(f['footer'])}</span>{_counter(index,total,light=True)}</div></section>"""


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
      <p style="font-size:{body_size}px">{_esc(f['body'])}</p><div class="cta-pill">{_esc(f['cta'])}</div></div>
      <div class="cta-footer"><span>{_esc(f['disclaimer'])}</span>{_counter(index,total,light=True)}</div></section>"""


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
    .footer-row{{position:absolute;z-index:8;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:center;font-size:24px;font-weight:500;line-height:1.4;color:{COLORS['body_light']}}}
    .hero-photo>.photo{{position:absolute;left:0;top:430px;width:1080px;height:920px;object-fit:cover}}.hero-top-fade{{position:absolute;left:0;top:430px;width:1080px;height:300px;background:linear-gradient(180deg,{COLORS['dark']} 0%,rgba(10,26,47,0) 100%)}}
    .hero-bottom-fade{{position:absolute;left:0;bottom:0;width:1080px;height:360px;background:linear-gradient(180deg,rgba(6,18,31,0),rgba(6,18,31,.9))}}.hero-copy{{position:absolute;z-index:5;left:80px;top:250px;width:920px;display:flex;flex-direction:column;gap:32px}}.hero-copy h1{{font-weight:800;line-height:.94;letter-spacing:-.035em;color:#fff}}
    .photo-split{{display:flex}}.split-photo{{position:relative;width:486px;height:1350px;flex:none}}.split-photo img,.split-photo div{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.split-copy{{position:relative;flex:1;padding:96px 80px 88px 72px;display:flex;flex-direction:column}}.split-copy .brand{{position:static}}.split-spacer{{height:88px;flex:none}}.split-copy .eyebrow{{margin-top:32px}}.split-copy h1{{margin-top:28px;font-weight:800;line-height:1;letter-spacing:-.03em}}.split-copy p{{margin-top:40px;font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}}.split-footer{{margin-top:auto;display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(10,26,47,.14);padding-top:28px;font-size:24px;color:{COLORS['footer_dark']}}}
    .statement-copy{{position:absolute;left:80px;right:80px;top:380px;display:flex;flex-direction:column;gap:44px}}.statement-copy h1{{font-weight:800;line-height:.94;letter-spacing:-.04em}}.statement-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:flex-end;border-top:1px solid rgba(10,26,47,.14);padding-top:32px;font-size:30px;line-height:1.4;color:{COLORS['body_dark']}}.big-statement.light-text .statement-footer{{border-color:rgba(244,242,237,.14);color:{COLORS['body_light']}}}.statement-footer>span{{max-width:640px}}
    .question-mark{{position:absolute;right:-60px;top:180px;font-size:760px;font-weight:800;line-height:.7;letter-spacing:-.06em;color:rgba(18,178,166,.10)}}.question-copy{{position:absolute;left:80px;right:80px;top:440px;display:flex;flex-direction:column;gap:48px}}.question-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.035em}}.question-copy p{{max-width:820px;font-size:36px;line-height:1.5;color:{COLORS['body_dark']}}.question.light-text .question-copy p{{color:{COLORS['body_light']}}}
    .myth-fact{{display:flex;flex-direction:column}}.myth-panel{{height:620px;background:{COLORS['dark']};padding:96px 80px 64px;display:flex;flex-direction:column;gap:36px;position:relative}}.myth-panel .brand{{position:static}}.label{{display:inline-flex;align-self:flex-start;padding:14px 24px;border-radius:4px;font-size:24px;font-weight:700;line-height:1;letter-spacing:.24em;text-transform:uppercase;color:{COLORS['dark']}}.label-myth{{background:{COLORS['muted']}}}.label-fact{{background:{COLORS['sand']}}}.myth-panel h2,.fact-panel h2{{font-size:72px;font-weight:800;line-height:1.02;letter-spacing:-.025em}}.myth-panel h2{{color:{COLORS['light']}}}.split-accent{{height:8px;background:{COLORS['teal']}}.fact-panel{{position:relative;flex:1;padding:64px 80px 120px;display:flex;flex-direction:column;gap:36px}}.fact-panel p{{font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}.fact-counter{{position:absolute;right:80px;bottom:88px}}
    .stat-copy{{position:absolute;left:80px;right:80px;top:300px;display:flex;flex-direction:column;gap:24px}}.statistic{{font-size:270px;font-weight:800;line-height:.82;letter-spacing:-.055em;color:{COLORS['teal']}}.hairline{{height:1px;background:rgba(10,26,47,.16);margin-top:18px}}.number-stat.light-text .hairline{{background:rgba(244,242,237,.16)}}.stat-copy h1{{max-width:880px;font-size:58px;font-weight:700;line-height:1.08;letter-spacing:-.02em}}.stat-copy p{{max-width:820px;font-size:32px;line-height:1.5;color:{COLORS['body_dark']}}.number-stat.light-text .stat-copy p{{color:{COLORS['body_light']}}}
    .three-copy{{position:absolute;left:80px;right:80px;top:240px}}.three-copy>h1{{max-width:860px;font-size:68px;font-weight:800;line-height:1.02;letter-spacing:-.025em}}.points{{margin-top:64px;display:flex;flex-direction:column;gap:38px}}.point-row{{display:flex;gap:40px;align-items:flex-start;border-top:1px solid rgba(244,242,237,.14);padding-top:34px}}.three-points.bg-light .point-row{{border-color:rgba(10,26,47,.14)}}.point-number{{width:110px;flex:none;font-size:64px;font-weight:800;line-height:.9;letter-spacing:-.03em;color:{COLORS['teal']}}.point-row h3{{font-size:43px;font-weight:700;line-height:1.1;letter-spacing:-.02em}}.point-row p{{margin-top:12px;font-size:28px;line-height:1.4;color:{COLORS['body_light']}}.three-points.bg-light .point-row p{{color:{COLORS['body_dark']}}}.bottom-counter{{position:absolute;right:80px;bottom:88px}}
    .explainer-copy{{position:absolute;left:80px;right:80px;top:260px}}.explainer-copy h1{{margin-top:28px;max-width:880px;font-size:66px;font-weight:800;line-height:1.03;letter-spacing:-.025em}}.explainer-copy>p{{margin-top:36px;max-width:880px;font-size:34px;line-height:1.5;color:{COLORS['body_dark']}}.steps{{margin-top:72px;display:flex;align-items:center;gap:24px}}.steps i{{flex:1;height:2px;background:rgba(10,26,47,.18)}}.step{{width:250px;height:150px;padding:0 28px;border-radius:12px;background:{COLORS['dark']};display:flex;flex-direction:column;justify-content:center;gap:8px;color:#fff}}.step span{{font-size:20px;font-weight:600;letter-spacing:.2em;color:{COLORS['teal']}}}.step strong{{font-size:32px;line-height:1.1}}.step-final{{background:{COLORS['teal']};color:{COLORS['deep']}}}.step-final span{{color:{COLORS['deep']}}}.explainer-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(10,26,47,.14);padding-top:28px;font-size:22px;color:{COLORS['footer_dark']}}}
    .quote-copy{{position:absolute;left:80px;right:80px;top:285px}}.opening-quote{{height:110px;font-family:'Instrument Serif';font-size:200px;line-height:.6;color:{COLORS['sand']}}blockquote{{max-width:900px;margin:0;font-family:'Instrument Serif';font-style:italic;font-size:82px;line-height:1.14;text-wrap:balance}}.quote-footer{{position:absolute;left:80px;right:80px;bottom:88px;display:flex;align-items:center;gap:32px;border-top:1px solid rgba(10,26,47,.16);padding-top:40px}}.doctor-quote.light-text .quote-footer{{border-color:rgba(244,242,237,.16)}}.quote-photo{{width:150px;height:150px;flex:none;border-radius:999px;object-fit:cover}}.quote-footer>div:not(.quote-counter):not(.counter){{display:flex;flex-direction:column;gap:8px}}.quote-footer strong{{font-size:38px;line-height:1.1}}.quote-footer span{{font-size:26px;line-height:1.3;color:{COLORS['footer_dark']}}.doctor-quote.light-text .quote-footer span{{color:{COLORS['body_light']}}}.quote-counter{{margin-left:auto}}
    .photo-overlay>.photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.photo-gradient{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,18,31,.75) 0%,rgba(6,18,31,0) 38%,rgba(6,18,31,.9) 100%)}}.overlay-copy{{position:absolute;z-index:5;left:80px;right:80px;bottom:180px;display:flex;flex-direction:column;gap:32px}}.overlay-copy-top{{top:280px;bottom:auto}}.overlay-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.03em;color:#fff}}
    .do-dont{{display:flex}}.avoid-panel,.prefer-panel{{position:relative;width:540px;padding:96px 48px 88px 80px;display:flex;flex-direction:column}}.avoid-panel{{background:{COLORS['dark']};color:{COLORS['light']}}}.prefer-panel{{background:{COLORS['light']};color:{COLORS['dark']};padding-left:48px;padding-right:80px}}.avoid-panel .brand{{position:static}}.compare-spacer{{height:120px}}.prefer-spacer{{height:167px}}.compare-label{{font-size:26px;font-weight:700;letter-spacing:.24em;text-transform:uppercase;color:{COLORS['teal']}}.muted-label{{color:{COLORS['muted']}}.compare-list{{margin-top:44px;display:flex;flex-direction:column;gap:36px}}.compare-item{{padding-top:32px;border-top:1px solid rgba(10,26,47,.16);font-size:40px;font-weight:600;line-height:1.15;letter-spacing:-.015em}}.avoid-panel .compare-item{{border-color:rgba(244,242,237,.16)}}.compare-note,.compare-counter{{margin-top:auto;font-size:22px;color:{COLORS['subtle']}}.compare-counter{{margin-left:auto}}
    .cta-photo>.photo{{position:absolute;right:0;top:0;width:600px;height:1350px;object-fit:cover}}.cta-photo.photo-left>.photo{{left:0;right:auto}}.cta-fade{{position:absolute;right:0;top:0;width:600px;height:1350px;background:linear-gradient(90deg,{COLORS['dark']} 0%,rgba(10,26,47,.65) 34%,rgba(10,26,47,.18) 100%)}}.photo-left .cta-fade{{left:0;right:auto;transform:scaleX(-1)}}.cta-copy{{position:absolute;z-index:5;left:80px;top:500px;width:650px;display:flex;flex-direction:column;gap:34px}}.photo-left .cta-copy{{left:350px}}.cta-copy h1{{font-weight:800;line-height:.98;letter-spacing:-.03em;color:#fff}}.cta-copy p{{font-size:32px;line-height:1.45;color:{COLORS['body_light']}}.cta-pill{{display:inline-flex;align-self:flex-start;padding:28px 44px;border-radius:999px;background:{COLORS['teal']};color:{COLORS['deep']};font-size:32px;font-weight:700;line-height:1}}.cta-footer{{position:absolute;z-index:6;left:80px;right:80px;bottom:88px;display:flex;justify-content:space-between;align-items:flex-end;border-top:1px solid rgba(244,242,237,.16);padding-top:28px;color:{COLORS['muted']}}.cta-footer>span{{max-width:620px;font-size:22px;line-height:1.4}}
    """
    for name, value in COLORS.items():
        template = template.replace("{COLORS['" + name + "']}", value)
    return template.replace("{_font_css()}", _font_css()).replace("{{", "{").replace("}}", "}")


def slide_html(slide: dict[str, Any], *, index: int, total: int) -> str:
    normalized = normalize_slide(slide, index - 1)
    layout_id = normalized["layoutId"]
    if layout_id not in PACK_LAYOUTS:
        raise ValueError(f"Layout desconhecido: {layout_id}")
    body = RENDERERS[layout_id](normalized, index, total)
    return f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><style>{_css()}</style></head><body>{body}</body></html>"


def _legacy_extra_html(title: str, body: str, *, width: int, height: int) -> str:
    template = """<!doctype html><html><head><meta charset='utf-8'><style>__FONTS__*{box-sizing:border-box}html,body{margin:0;width:__WIDTH__px;height:__HEIGHT__px;overflow:hidden}body{background:__DARK__;color:#fff;font-family:Archivo;padding:96px 80px;display:flex;flex-direction:column}.ey{color:__TEAL__;font-size:22px;letter-spacing:.2em;text-transform:uppercase}h1{margin:auto 0 32px;font-size:82px;line-height:1;font-weight:800}p{margin:0 0 auto;font-size:34px;line-height:1.5;color:__BODY_LIGHT__}small{font-size:20px;color:__MUTED__}</style></head><body><div class='ey'>Instituto Guilherme Martins</div><h1>__TITLE__</h1><p>__BODY__</p><small>Conteúdo educativo. Não substitui avaliação médica individual.</small></body></html>"""
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
    )


def render_pack_images(
    img_root: Path,
    carousel: Iterable[dict],
    stories: Iterable[dict] = (),
    static_post: dict[str, Any] | None = None,
    *,
    design_direction: str = "institute_carousel_v1",
    avatar_asset: dict[str, Any] | None = None,
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
                page.set_content(slide_html(slide, index=index, total=len(slides)), wait_until="networkidle")
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
    }
