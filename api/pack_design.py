"""Contrato visual do carrossel do Instituto Guilherme Martins.

Este modulo concentra o vocabulario fechado de layouts, limites editoriais e
metadados das fotos. Claude escolhe conteudo e composicao; o renderer continua
deterministico.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

PACK_SCHEMA_VERSION = "institute-carousel-v1"
PACK_SLIDE_COUNT = 6

PACK_LAYOUTS = (
    "hero_photo",
    "photo_split",
    "big_statement",
    "question",
    "myth_fact",
    "number_stat",
    "three_points",
    "explainer",
    "doctor_quote",
    "photo_overlay",
    "do_dont",
    "cta_photo",
)

FALLBACK_LAYOUTS = (
    "hero_photo",
    "question",
    "myth_fact",
    "three_points",
    "doctor_quote",
    "cta_photo",
)

LEGACY_LAYOUT_MAP = {
    "hero_avatar": "hero_photo",
    "avatar_split": "photo_split",
    "big_statement": "big_statement",
    "myth_fact": "myth_fact",
    "number_stat": "number_stat",
    "three_points": "three_points",
    "quote_card": "doctor_quote",
    "editorial_photo": "photo_overlay",
    "minimal_explainer": "explainer",
    "cta_avatar": "cta_photo",
}

PHOTO_LAYOUTS = {"hero_photo", "photo_split", "doctor_quote", "photo_overlay", "cta_photo"}
FULL_BLEED_PHOTO_LAYOUTS = {"hero_photo", "photo_overlay"}
DARK_LAYOUTS = {"hero_photo", "big_statement", "three_points", "photo_overlay", "cta_photo"}

# Os arquivos vieram no kit de design com nomes semanticos. No projeto eles ja
# estavam versionados com o nome original do ensaio; o mapeamento evita duplicar
# 55 MB de fotografias no Git.
PHOTO_LIBRARY: dict[str, dict[str, Any]] = {
    "wide-office": {
        "file": "data/pack_assets/photos/vine8121.jpg",
        "name": "Consultorio aberto",
        "description": "plano aberto no consultorio, bom para capa com respiro",
        "facePointX": 0.48,
        "facePointY": 0.24,
        "brightness": 0.42,
    },
    "seated-side": {
        "file": "data/pack_assets/photos/vine8142.jpg",
        "name": "Sentado de lado",
        "description": "sentado de perfil, espaco lateral para texto",
        "facePointX": 0.46,
        "facePointY": 0.26,
        "brightness": 0.36,
    },
    "seated-lean": {
        "file": "data/pack_assets/photos/vine8150.jpg",
        "name": "Sentado inclinado",
        "description": "sentado inclinado, corpo inteiro e olhar direto",
        "facePointX": 0.44,
        "facePointY": 0.24,
        "brightness": 0.34,
    },
    "seated-arm": {
        "file": "data/pack_assets/photos/vine8163.jpg",
        "name": "Sentado com braco apoiado",
        "description": "retrato vertical com postura clinica e fundo limpo",
        "facePointX": 0.52,
        "facePointY": 0.22,
        "brightness": 0.39,
    },
    "seated-front": {
        "file": "data/pack_assets/photos/vine8172.jpg",
        "name": "Sentado de frente",
        "description": "corpo inteiro de frente, ideal para capa e CTA",
        "facePointX": 0.44,
        "facePointY": 0.16,
        "brightness": 0.31,
    },
    "portrait-closeup": {
        "file": "data/pack_assets/photos/vine8178.jpg",
        "name": "Retrato proximo",
        "description": "close-up do rosto, ideal para citacao medica",
        "facePointX": 0.52,
        "facePointY": 0.30,
        "brightness": 0.46,
    },
}

EMPTY_ITEM = {"title": "", "text": ""}
FIELD_NAMES = (
    "eyebrow",
    "headline",
    "subheadline",
    "body",
    "statistic",
    "item1",
    "item2",
    "item3",
    "quote",
    "cta",
    "footer",
    "caption",
    "disclaimer",
    "photoId",
)

LAYOUT_SPECS: dict[str, dict[str, Any]] = {
    "hero_photo": {"required": ("eyebrow", "headline", "photoId"), "max": {"eyebrow": 22, "headline": 46, "footer": 48}},
    "photo_split": {"required": ("headline", "body", "photoId"), "max": {"eyebrow": 22, "headline": 52, "body": 160, "footer": 48}},
    "big_statement": {"required": ("headline",), "max": {"headline": 64, "footer": 90}},
    "question": {"required": ("headline",), "max": {"eyebrow": 22, "headline": 52, "body": 110, "footer": 48}},
    "myth_fact": {"required": ("item1", "item2"), "max": {"body": 120}, "item_max": {"title": 12, "text": 42}},
    "number_stat": {"required": ("statistic", "headline", "caption"), "max": {"eyebrow": 22, "statistic": 6, "headline": 60, "body": 110, "caption": 72}},
    "three_points": {"required": ("headline", "item1", "item2", "item3"), "max": {"headline": 40}, "item_max": {"title": 24, "text": 90}},
    "explainer": {"required": ("headline", "body"), "max": {"eyebrow": 22, "headline": 56, "body": 200, "disclaimer": 90}, "item_max": {"title": 24, "text": 54}},
    "doctor_quote": {"required": ("quote", "caption"), "max": {"quote": 90, "caption": 48}},
    "photo_overlay": {"required": ("eyebrow", "headline", "photoId"), "max": {"eyebrow": 22, "headline": 60, "footer": 48}},
    "do_dont": {"required": ("item1", "item2"), "max": {"disclaimer": 90}, "item_max": {"title": 34, "text": 34}},
    "cta_photo": {"required": ("headline", "cta", "photoId", "disclaimer"), "max": {"headline": 62, "body": 70, "cta": 22, "disclaimer": 90}},
}


def empty_fields() -> dict[str, Any]:
    fields: dict[str, Any] = {name: "" for name in FIELD_NAMES}
    fields["item1"] = deepcopy(EMPTY_ITEM)
    fields["item2"] = deepcopy(EMPTY_ITEM)
    fields["item3"] = deepcopy(EMPTY_ITEM)
    return fields


def photo_asset(photo_id: str) -> dict[str, Any] | None:
    meta = PHOTO_LIBRARY.get(photo_id)
    if not meta:
        return None
    return {"id": photo_id, "cachedAssetPath": meta["file"], **deepcopy(meta)}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_fields(value: Any) -> dict[str, Any]:
    fields = empty_fields()
    if isinstance(value, dict):
        for name in FIELD_NAMES:
            if name.startswith("item"):
                raw_item = value.get(name)
                if isinstance(raw_item, dict):
                    fields[name] = {
                        "title": _text(raw_item.get("title")),
                        "text": _text(raw_item.get("text")),
                    }
            else:
                fields[name] = _text(value.get(name))
    return fields


def normalize_slide(slide: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Aceita o contrato novo e adapta Packs antigos sem destruir os dados salvos."""
    raw_layout = slide.get("layoutId") or slide.get("layout")
    layout_id = LEGACY_LAYOUT_MAP.get(str(raw_layout), str(raw_layout))
    if layout_id not in PACK_LAYOUTS:
        layout_id = FALLBACK_LAYOUTS[min(index, len(FALLBACK_LAYOUTS) - 1)]

    raw_fields = slide.get("fields")
    has_structured_content = isinstance(raw_fields, dict) and any(
        _text(value.get("title")) or _text(value.get("text"))
        if isinstance(value, dict)
        else _text(value)
        for value in raw_fields.values()
    )
    if has_structured_content:
        fields = normalize_fields(raw_fields)
    else:
        fields = empty_fields()
        fields["eyebrow"] = _text(slide.get("tema") or slide.get("visualIntent"))[:22]
        fields["headline"] = _text(slide.get("title"))
        fields["body"] = _text(slide.get("body"))
        fields["subheadline"] = _text(slide.get("highlight"))
        fields["footer"] = "Arraste para o lado" if index == 0 else ""
        if layout_id == "doctor_quote":
            fields["quote"] = fields["headline"]
            fields["caption"] = fields["body"] or "Dr. Guilherme Martins"
        if layout_id == "number_stat":
            match = re.search(r"\b\d+(?:[,.]\d+)?%?\b", fields["headline"])
            fields["statistic"] = match.group(0) if match else ""
        if layout_id in PHOTO_LAYOUTS:
            fields["photoId"] = "seated-front" if index in {0, PACK_SLIDE_COUNT - 1} else "seated-side"

    photo = slide.get("photoAsset") if isinstance(slide.get("photoAsset"), dict) else None
    if photo and photo.get("id") in PHOTO_LIBRARY:
        fields["photoId"] = str(photo["id"])
    elif fields["photoId"] in PHOTO_LIBRARY:
        photo = photo_asset(fields["photoId"])

    variant = _text(slide.get("variant")) or ("dark" if layout_id in DARK_LAYOUTS else "light")
    return {
        **slide,
        "layoutId": layout_id,
        "layout": layout_id,
        "variant": variant,
        "fields": fields,
        "photoAsset": photo,
    }


def _fit_copy(value: Any, maximum: int) -> str:
    """Encurta copy de forma deterministica sem deixar pontuacao solta."""
    text = _text(value)
    if len(text) <= maximum:
        return text
    clipped = text[:maximum].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return clipped.rstrip(" ,;:-–—") or text[:maximum].rstrip()


def _repair_required_items(fields: dict[str, Any], layout_id: str, spec: dict[str, Any]) -> None:
    """Preenche blocos obrigatorios ausentes sem inventar dados especificos."""
    item_limits = spec.get("item_max", {})
    if layout_id == "myth_fact":
        fallback_items = {
            "item1": {"title": "Mito", "text": "Uma indicação não serve para todos."},
            "item2": {
                "title": "Fato",
                "text": fields.get("body") or "Cada indicação precisa de avaliação individual.",
            },
        }
    elif layout_id == "do_dont":
        fallback_items = {
            "item1": {"title": "Evite", "text": fields.get("body") or "Não tome decisões sem orientação."},
            "item2": {"title": "Prefira", "text": fields.get("disclaimer") or "Converse com um profissional."},
        }
    elif layout_id == "three_points":
        fallback_items = {
            "item1": {"title": "Ponto 1", "text": fields.get("body") or fields.get("headline")},
            "item2": {"title": "Ponto 2", "text": fields.get("subheadline") or fields.get("headline")},
            "item3": {"title": "Ponto 3", "text": fields.get("caption") or fields.get("headline")},
        }
    else:
        fallback_items = {}

    for item_name in spec.get("required", ()):
        if not item_name.startswith("item") or item_name not in fallback_items:
            continue
        item = fields.get(item_name)
        if isinstance(item, dict) and (_text(item.get("title")) or _text(item.get("text"))):
            continue
        fallback = fallback_items[item_name]
        fields[item_name] = {
            "title": _fit_copy(fallback["title"], item_limits.get("title", 34)),
            "text": _fit_copy(fallback["text"], item_limits.get("text", 90)),
        }


def repair_pack_copy(pack: dict[str, Any]) -> dict[str, Any]:
    """Ajusta excesso de caracteres antes da validacao final do contrato.

    O modelo continua recebendo os limites no prompt e uma segunda chance de
    correcao. Este ultimo passo evita que uma resposta com poucos caracteres a
    mais invalide o Pack inteiro por uma diferenca editorial trivial.
    """
    repaired = deepcopy(pack)
    raw_slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else repaired.get("carousel")
    if not isinstance(raw_slides, list):
        return repaired

    slides: list[Any] = []
    for index, raw_slide in enumerate(raw_slides):
        if not isinstance(raw_slide, dict):
            slides.append(raw_slide)
            continue
        slide = normalize_slide(raw_slide, index)
        spec = LAYOUT_SPECS[slide["layoutId"]]
        fields = slide["fields"]
        _repair_required_items(fields, slide["layoutId"], spec)
        for name, maximum in spec.get("max", {}).items():
            fields[name] = _fit_copy(fields.get(name), maximum)
        for item_name in ("item1", "item2", "item3"):
            item = fields.get(item_name)
            if not isinstance(item, dict):
                continue
            for part, maximum in spec.get("item_max", {}).items():
                item[part] = _fit_copy(item.get(part), maximum)
        headline = _text(fields.get("headline"))
        if len(headline.split()) > 11:
            fields["headline"] = " ".join(headline.split()[:11])
        slides.append(slide)

    repaired["slides"] = slides
    repaired["carousel"] = slides
    return repaired


def slide_headline(slide: dict[str, Any]) -> str:
    normalized = normalize_slide(slide)
    fields = normalized["fields"]
    return fields.get("headline") or fields.get("quote") or fields.get("item1", {}).get("text") or ""


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]",
    flags=re.UNICODE,
)


def validate_pack_contract(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slides = pack.get("slides") if isinstance(pack.get("slides"), list) else pack.get("carousel")
    if not isinstance(slides, list):
        return ["slides precisa ser uma lista com 6 itens"]
    if len(slides) != PACK_SLIDE_COUNT:
        errors.append(f"slides tem {len(slides)} itens; esperado: {PACK_SLIDE_COUNT}")

    normalized = [normalize_slide(slide, index) for index, slide in enumerate(slides) if isinstance(slide, dict)]
    if len(normalized) != len(slides):
        errors.append("todos os slides precisam ser objetos")
        return errors

    layouts = [slide["layoutId"] for slide in normalized]
    if layouts and layouts[0] not in {"hero_photo", "photo_overlay"}:
        errors.append("slide 1 precisa usar hero_photo ou photo_overlay")
    if len(layouts) >= PACK_SLIDE_COUNT and layouts[-1] != "cta_photo":
        errors.append("slide 6 precisa usar cta_photo")
    if len(layouts) != len(set(layouts)):
        errors.append("os 6 layoutId precisam ser diferentes")
    if sum(layout in PHOTO_LAYOUTS for layout in layouts) > 3:
        errors.append("o carrossel pode ter no maximo 3 slides com foto")
    for index in range(1, len(layouts)):
        if layouts[index - 1] in FULL_BLEED_PHOTO_LAYOUTS and layouts[index] in FULL_BLEED_PHOTO_LAYOUTS:
            errors.append(f"slides {index} e {index + 1} usam foto full bleed em sequencia")

    dark_run = 0
    for index, slide in enumerate(normalized, start=1):
        layout_id = slide["layoutId"]
        fields = slide["fields"]
        spec = LAYOUT_SPECS[layout_id]
        dark_run = dark_run + 1 if slide["variant"] in {"dark", "deep"} else 0
        if dark_run > 2:
            errors.append(f"slide {index} cria mais de 2 fundos escuros consecutivos")

        for name in spec.get("required", ()):
            value = fields.get(name)
            if name.startswith("item"):
                if not isinstance(value, dict) or not (_text(value.get("title")) or _text(value.get("text"))):
                    errors.append(f"slide {index}: {name} e obrigatorio para {layout_id}")
            elif not _text(value):
                errors.append(f"slide {index}: {name} e obrigatorio para {layout_id}")

        for name, maximum in spec.get("max", {}).items():
            value = _text(fields.get(name))
            if len(value) > maximum:
                errors.append(f"slide {index}: {name} tem {len(value)} caracteres; maximo {maximum}")
        item_limits = spec.get("item_max", {})
        for item_name in ("item1", "item2", "item3"):
            item = fields.get(item_name)
            if not isinstance(item, dict):
                continue
            for part, maximum in item_limits.items():
                value = _text(item.get(part))
                if len(value) > maximum:
                    errors.append(
                        f"slide {index}: {item_name}.{part} tem {len(value)} caracteres; maximo {maximum}"
                    )

        all_text = " ".join(
            _text(value)
            if not isinstance(value, dict)
            else f"{_text(value.get('title'))} {_text(value.get('text'))}"
            for value in fields.values()
        )
        if _EMOJI_RE.search(all_text):
            errors.append(f"slide {index}: remova emojis")
        headline = _text(fields.get("headline"))
        if headline and len(headline.split()) > 11:
            errors.append(f"slide {index}: headline precisa ter no maximo 11 palavras")
        photo_id = _text(fields.get("photoId"))
        if photo_id and photo_id not in PHOTO_LIBRARY:
            errors.append(f"slide {index}: photoId desconhecido: {photo_id}")

    caption = _text(pack.get("caption"))
    if not caption:
        errors.append("caption e obrigatoria")
    if _EMOJI_RE.search(caption):
        errors.append("caption nao pode ter emojis")
    return list(dict.fromkeys(errors))
