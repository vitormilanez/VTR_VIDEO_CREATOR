"""Legendas gráficas locais para o kit de vídeo vertical."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


MAX_CAPTION_WORDS = 8
MAX_CAPTION_CHARS = 54
MAX_CAPTION_MS = 2400
_ACCENT_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
_WORD_PATTERN = re.compile(r"([\wÀ-ÿ-]+)", re.UNICODE)
_STOP_WORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "é",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "mais",
    "mas",
    "na",
    "nas",
    "não",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "seu",
    "sua",
    "um",
    "uma",
    "você",
}


def _clean_word(value: str) -> str:
    return re.sub(r"[^a-zà-ÿ0-9-]", "", value.casefold())


def caption_cues(transcript: dict[str, Any], duration_seconds: float) -> list[dict[str, Any]]:
    """Agrupa palavras sincronizadas em cartelas curtas e legíveis."""
    cues: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    maximum_ms = max(0, round(duration_seconds * 1000))

    def flush() -> None:
        if not current:
            return
        text = " ".join(str(word.get("text") or "").strip() for word in current).strip()
        start_ms = max(0, int(current[0].get("startMs") or 0))
        end_ms = min(
            maximum_ms,
            max(start_ms + 120, int(current[-1].get("endMs") or start_ms)),
        )
        if text and start_ms < maximum_ms and end_ms > start_ms:
            cues.append(
                {
                    "start": round(start_ms / 1000, 3),
                    "end": round(end_ms / 1000, 3),
                    "text": re.sub(r"\s+", " ", text),
                }
            )
        current.clear()

    for raw_word in transcript.get("words", []):
        word = dict(raw_word)
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        if current:
            candidate = " ".join(
                [*(str(item.get("text") or "") for item in current), text]
            )
            cue_duration = int(word.get("endMs") or 0) - int(current[0].get("startMs") or 0)
            if (
                len(current) >= MAX_CAPTION_WORDS
                or len(candidate) > MAX_CAPTION_CHARS
                or cue_duration > MAX_CAPTION_MS
            ):
                flush()
        current.append(word)
        if len(current) >= 3 and text.endswith((".", "?", "!")):
            flush()
    flush()
    return cues


def _highlighted_words(text: str, enabled: bool) -> set[str]:
    if not enabled:
        return set()
    candidates: list[tuple[int, int, str]] = []
    for index, token in enumerate(_WORD_PATTERN.findall(text)):
        key = _clean_word(token)
        if len(key) < 5 or key in _STOP_WORDS:
            continue
        number_bonus = 12 if any(character.isdigit() for character in key) else 0
        candidates.append((len(key) + number_bonus, -index, key))
    return {item[2] for item in sorted(candidates, reverse=True)[:2]}


def _caption_markup(text: str, highlight: bool) -> str:
    highlighted = _highlighted_words(text, highlight)
    fragments: list[str] = []
    cursor = 0
    for match in _WORD_PATTERN.finditer(text):
        fragments.append(html.escape(text[cursor : match.start()]))
        word = match.group(0)
        escaped = html.escape(word)
        fragments.append(
            f"<mark>{escaped}</mark>" if _clean_word(word) in highlighted else escaped
        )
        cursor = match.end()
    fragments.append(html.escape(text[cursor:]))
    return "".join(fragments)


def caption_document(text: str, config: dict[str, Any]) -> str:
    """Cria uma camada 1080×1920 transparente para uma legenda."""
    style = str(config.get("captionStyle") or "dynamic")
    if style not in {"dynamic", "clean", "editorial"}:
        style = "dynamic"
    position = str(config.get("captionPosition") or "safe_bottom")
    if position not in {"safe_bottom", "center", "upper"}:
        position = "safe_bottom"
    accent = str(config.get("accent") or "#c8e05a")
    if not _ACCENT_PATTERN.fullmatch(accent):
        accent = "#c8e05a"
    markup = _caption_markup(text, bool(config.get("highlightKeywords", True)))
    position_class = {
        "safe_bottom": "position-bottom",
        "center": "position-center",
        "upper": "position-upper",
    }[position]
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
      *{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:transparent}}
      body{{display:flex;justify-content:center;padding-left:76px;padding-right:76px;color:#fff}}
      body.position-bottom{{align-items:flex-end;padding-bottom:390px}}
      body.position-center{{align-items:center;padding-bottom:80px}}
      body.position-upper{{align-items:flex-start;padding-top:300px}}
      .caption{{max-width:928px;text-align:center;text-wrap:balance}}
      mark{{color:{accent};background:transparent}}
      body.dynamic .caption{{font-family:Arial,Helvetica,sans-serif;font-size:74px;font-weight:900;line-height:1.02;letter-spacing:-.035em;text-transform:uppercase;-webkit-text-stroke:2px rgba(8,14,18,.82);paint-order:stroke fill;text-shadow:0 8px 28px rgba(0,0,0,.72)}}
      body.clean .caption{{font-family:Arial,Helvetica,sans-serif;font-size:62px;font-weight:750;line-height:1.12;letter-spacing:-.025em;background:rgba(7,15,20,.84);border:1px solid rgba(255,255,255,.16);border-radius:28px;padding:24px 32px 27px;box-shadow:0 20px 54px rgba(0,0,0,.32);backdrop-filter:blur(12px)}}
      body.editorial .caption{{font-family:Georgia,'Times New Roman',serif;font-size:72px;font-weight:700;font-style:italic;line-height:1.04;letter-spacing:-.025em;text-shadow:0 5px 0 rgba(9,15,18,.92),0 14px 36px rgba(0,0,0,.62)}}
    </style></head><body class='{style} {position_class}'><div class='caption'>{markup}</div></body></html>"""


def render_caption_assets(
    transcript: dict[str, Any],
    config: dict[str, Any],
    destination: Path,
    *,
    duration_seconds: float,
) -> list[dict[str, Any]]:
    """Renderiza as legendas como PNGs transparentes para o FFmpeg local."""
    from playwright.sync_api import sync_playwright

    destination.mkdir(parents=True, exist_ok=True)
    cues = caption_cues(transcript, duration_seconds)
    rendered: list[dict[str, Any]] = []
    if not cues:
        return rendered
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            blank_path = destination / "blank.png"
            page.set_content(
                "<!doctype html><html><style>html,body{margin:0;width:1080px;height:1920px;background:transparent}</style><body></body></html>",
                wait_until="load",
            )
            page.screenshot(path=str(blank_path), omit_background=True)
            for index, cue in enumerate(cues, start=1):
                path = destination / f"caption-{index:03d}.png"
                page.set_content(caption_document(str(cue["text"]), config), wait_until="load")
                page.screenshot(path=str(path), omit_background=True)
                rendered.append({**cue, "path": path})
        finally:
            context.close()
            browser.close()
    return rendered


def write_caption_timeline(
    captions: list[dict[str, Any]],
    destination: Path,
    *,
    total_duration: float,
) -> Path:
    """Cria uma faixa VFR única, alternando legenda e transparência."""
    blank_path = destination / "blank.png"
    if not blank_path.is_file():
        raise RuntimeError("A camada transparente das legendas não foi renderizada.")

    lines = ["ffconcat version 1.0"]
    cursor = 0.0

    def append_frame(path: Path, duration: float) -> None:
        if duration <= 0.001:
            return
        lines.append(f"file '{path.name}'")
        lines.append(f"duration {duration:.6f}")

    for caption in captions:
        start = min(max(cursor, float(caption["start"])), total_duration)
        end = min(max(start, float(caption["end"])), total_duration)
        append_frame(blank_path, start - cursor)
        append_frame(Path(caption["path"]), end - start)
        cursor = end
    append_frame(blank_path, max(0.0, total_duration - cursor))
    # O concat demuxer ignora a duração da última entrada sem um quadro final.
    lines.append(f"file '{blank_path.name}'")
    timeline = destination / "captions.ffconcat"
    timeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return timeline
