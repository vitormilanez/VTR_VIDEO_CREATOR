"""Contrato visual do carrossel do Instituto Guilherme Martins.

Este modulo concentra o vocabulario fechado de layouts, limites editoriais e
metadados das fotos. Claude escolhe conteudo e composicao; o renderer continua
deterministico.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

PACK_SCHEMA_VERSION = "institute-carousel-v2"
PACK_SLIDE_COUNT = 7

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
    "explainer",
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
        "file": "data/pack_assets/photos/vine8178.jpg",
        "name": "Consultorio aberto",
        "description": "plano aberto no consultorio, bom para capa com respiro",
        "facePointX": 0.48,
        "facePointY": 0.24,
        "brightness": 0.42,
    },
    "seated-side": {
        "file": "data/pack_assets/photos/vine8172.jpg",
        "name": "Sentado de lado",
        "description": "sentado de perfil, espaco lateral para texto",
        "facePointX": 0.46,
        "facePointY": 0.26,
        "brightness": 0.36,
    },
    "seated-lean": {
        "file": "data/pack_assets/photos/vine8163.jpg",
        "name": "Sentado inclinado",
        "description": "sentado inclinado, corpo inteiro e olhar direto",
        "facePointX": 0.44,
        "facePointY": 0.24,
        "brightness": 0.34,
    },
    "seated-arm": {
        "file": "data/pack_assets/photos/vine8150.jpg",
        "name": "Sentado com braco apoiado",
        "description": "retrato vertical com postura clinica e fundo limpo",
        "facePointX": 0.52,
        "facePointY": 0.22,
        "brightness": 0.39,
    },
    "seated-front": {
        "file": "data/pack_assets/photos/vine8142.jpg",
        "name": "Sentado de frente",
        "description": "corpo inteiro de frente, ideal para capa e CTA",
        "facePointX": 0.44,
        "facePointY": 0.16,
        "brightness": 0.31,
    },
    "portrait-closeup": {
        "file": "data/pack_assets/photos/vine8121.jpg",
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
    "myth_fact": {"required": ("item1", "item2"), "max": {"body": 90}, "item_max": {"title": 12, "text": 38}},
    "number_stat": {"required": ("statistic", "headline", "caption"), "max": {"eyebrow": 22, "statistic": 6, "headline": 60, "body": 110, "caption": 72}},
    "three_points": {"required": ("headline", "item1", "item2", "item3"), "max": {"headline": 40}, "item_max": {"title": 24, "text": 90}},
    "explainer": {"required": ("headline", "body"), "max": {"eyebrow": 22, "headline": 56, "body": 280, "disclaimer": 90}, "item_max": {"title": 24, "text": 54}},
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
        # O ID semântico é estável; o caminho pode ter sido salvo por uma
        # versão com o mapeamento das fotos trocado. Reidrata sempre a partir
        # da biblioteca canônica para migrar Packs existentes.
        photo = photo_asset(fields["photoId"])
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
    """Encurta copy sem terminar no início de uma nova frase."""
    text = _text(value)
    if len(text) <= maximum:
        return text
    clipped = text[:maximum].rstrip()
    # Quando já existe uma frase completa dentro do limite, ela preserva o
    # sentido melhor do que um corte por palavra como "... funcionando. O".
    sentence_ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)", clipped)]
    if sentence_ends:
        complete = clipped[: sentence_ends[-1]].strip()
        if complete:
            return complete
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return _remove_dangling_words(clipped.rstrip(" ,;:-–—")) or text[:maximum].rstrip()


_DANGLING_WORDS = {
    "a",
    "as",
    "ao",
    "aos",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
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
}


def _remove_dangling_words(value: str) -> str:
    """Remove conectivos finais que denunciam um corte mecanico de copy."""
    text = _text(value)
    while text and text.split()[-1].casefold().strip(".,;:") in _DANGLING_WORDS:
        text = " ".join(text.split()[:-1]).rstrip(" ,;:-–—")
    return text


_GENERIC_MYTH_FALLBACKS = {
    "uma indicação não serve para todos.",
    "uma indicacao nao serve para todos.",
}


def _has_item_content(value: Any) -> bool:
    return isinstance(value, dict) and bool(_text(value.get("title")) or _text(value.get("text")))


def pack_slides(pack: dict[str, Any]) -> list[Any]:
    """Retorna a lista canônica do carrossel, aceitando o alias legado ``slides``."""
    # A interface edita ``carousel``. Quando um Pack antigo contém os dois
    # campos, priorizar ``slides`` restaura silenciosamente fotos e layouts
    # antigos na próxima leitura.
    candidates = [pack.get("carousel"), pack.get("slides")]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return candidate
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def _repair_layout_semantics(slide: dict[str, Any]) -> None:
    """Evita usar componentes de comparação para uma lista explicativa."""
    fields = slide["fields"]
    layout_id = slide["layoutId"]

    # O componente Evite/Prefira renderiza títulos de um lado e ações do outro.
    # Três etapas como "o que faz / e depois / resultado" são uma sequência,
    # não uma comparação, e devem renderizar como três pontos.
    if layout_id == "do_dont" and _has_item_content(fields.get("item3")):
        slide["layoutId"] = "three_points"
        slide["layout"] = "three_points"
        if slide.get("variant") not in {"dark", "light"}:
            slide["variant"] = "dark"

    if slide["layoutId"] != "myth_fact":
        return
    item1 = fields.get("item1") if isinstance(fields.get("item1"), dict) else {}
    item2 = fields.get("item2") if isinstance(fields.get("item2"), dict) else {}
    item1_text = _text(item1.get("text"))
    item2_text = _text(item2.get("text"))
    headline = _text(fields.get("headline"))
    if headline and _text(item1_text).lower() in _GENERIC_MYTH_FALLBACKS:
        fields["item1"] = {"title": "Mito", "text": headline}
        item1_text = headline

    lower_myth = item1_text.casefold()
    lower_fact = item2_text.casefold()
    if "efeitos colaterais" in lower_myth and "comuns" in lower_myth:
        fields["item1"] = {"title": "Mito", "text": "So existem efeitos comuns"}
        if any(term in lower_fact for term in ("desnutri", "alerg", "crise", "pancreat", "vesicula", "hipoglic")):
            fields["item2"] = {"title": "Fato", "text": "Alguns sinais exigem avaliação"}
            if not _text(fields.get("body")):
                fields["body"] = "Dor intensa ou reação incomum precisa ser comunicada ao médico."


def _repair_required_items(fields: dict[str, Any], layout_id: str, spec: dict[str, Any]) -> None:
    """Preenche blocos obrigatorios ausentes sem inventar dados especificos."""
    item_limits = spec.get("item_max", {})
    scalar_fallbacks = {
        "eyebrow": fields.get("headline") or "Contexto",
        "headline": fields.get("body") or fields.get("quote") or fields.get("cta") or "Informacao importante",
        "body": fields.get("subheadline") or fields.get("caption") or "Entenda o contexto antes de tomar decisoes.",
        "statistic": "1",
        "quote": fields.get("headline") or fields.get("body") or "Cada caso precisa de avaliacao individual.",
        "caption": fields.get("footer") or "Dr. Guilherme Martins",
        "cta": "Salve para revisar",
        "footer": "Arraste para o lado",
        "disclaimer": "Conteudo educativo. Nao substitui avaliacao medica.",
        "photoId": "seated-front",
    }
    if layout_id == "cta_photo":
        scalar_fallbacks.update(
            {
                "headline": fields.get("headline") or "Converse com seu medico",
                "body": fields.get("body") or "Use esta informacao para revisar sintomas e duvidas.",
                "cta": fields.get("cta") or "Salve para revisar",
                "disclaimer": fields.get("disclaimer") or "Conteudo educativo. Nao substitui avaliacao medica.",
                "photoId": fields.get("photoId") or "seated-front",
            }
        )
    elif layout_id == "doctor_quote":
        scalar_fallbacks.update(
            {
                "quote": fields.get("quote") or fields.get("headline") or "Acompanhamento individual muda a seguranca do cuidado.",
                "caption": fields.get("caption") or "Dr. Guilherme Martins",
            }
        )
    elif layout_id in PHOTO_LAYOUTS:
        scalar_fallbacks["photoId"] = fields.get("photoId") or "seated-front"

    for name in spec.get("required", ()):
        if name.startswith("item"):
            continue
        if _text(fields.get(name)):
            continue
        maximum = int(spec.get("max", {}).get(name, 90))
        fields[name] = _fit_copy(scalar_fallbacks.get(name, ""), maximum)

    if layout_id == "myth_fact":
        fallback_items = {
            "item1": {"title": "Mito", "text": fields.get("headline") or "Nem toda afirmação vale para todos."},
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


def _legacy_context_slide(raw_slides: list[Any]) -> dict[str, Any]:
    """Cria o slide de contexto para Packs antigos de seis telas.

    Esta migração precisa ser local: Packs já salvos não devem voltar a chamar
    o Claude apenas porque o contrato editorial passou de seis para sete
    slides. O texto é reaproveitado do explainer existente sempre que possível
    e cai para uma frase editorial neutra quando o Pack antigo não o possui.
    """
    source: dict[str, Any] | None = None
    for index, raw_slide in enumerate(raw_slides):
        if not isinstance(raw_slide, dict):
            continue
        normalized = normalize_slide(raw_slide, index)
        if normalized["layoutId"] == "explainer":
            source = normalized
            break

    source_fields = source["fields"] if source else {}
    headline = _text(source_fields.get("subheadline")) or _text(source_fields.get("headline"))
    body = _text(source_fields.get("body"))
    fields = empty_fields()
    fields.update(
        {
            "eyebrow": "Contexto",
            "headline": _fit_copy(headline or "O contexto também importa", 64),
            "body": _fit_copy(body, 90),
            "footer": "Entenda antes de decidir",
        }
    )
    return {"layoutId": "explainer", "variant": "light", "fields": fields}


def _repair_missing_context_slide(slides: list[Any]) -> None:
    """Garante o explainer central inclusive em Packs já migrados e salvos."""
    if len(slides) != PACK_SLIDE_COUNT:
        return
    if any(
        isinstance(slide, dict) and slide.get("layoutId") == "explainer"
        for slide in slides[2:5]
    ):
        return

    target = slides[3]
    if not isinstance(target, dict):
        return
    fields = target.get("fields") if isinstance(target.get("fields"), dict) else empty_fields()
    neighbor_bodies = [
        (slide.get("fields") or {}).get("body")
        for slide in (slides[4], slides[2])
        if isinstance(slide, dict) and isinstance(slide.get("fields"), dict)
    ]
    fields["eyebrow"] = _fit_copy(fields.get("eyebrow") or "Contexto", 22)
    fields["headline"] = _fit_copy(fields.get("headline") or "O contexto também importa", 56)
    fields["body"] = _fit_copy(
        fields.get("body")
        or next((_text(body) for body in neighbor_bodies if _text(body)), "")
        or "Cada pessoa precisa de avaliação individual e acompanhamento médico.",
        280,
    )
    target["layoutId"] = "explainer"
    target["layout"] = "explainer"
    target["variant"] = "light"
    target["fields"] = fields
    _repair_required_items(fields, "explainer", LAYOUT_SPECS["explainer"])


def repair_pack_copy(pack: dict[str, Any]) -> dict[str, Any]:
    """Ajusta excesso de caracteres antes da validacao final do contrato.

    O modelo continua recebendo os limites no prompt e uma segunda chance de
    correcao. Este ultimo passo evita que uma resposta com poucos caracteres a
    mais invalide o Pack inteiro por uma diferenca editorial trivial.
    """
    repaired = deepcopy(pack)
    raw_slides = pack_slides(repaired)
    if not raw_slides:
        return repaired

    migrated_six_slide_pack = len(raw_slides) == PACK_SLIDE_COUNT - 1
    if migrated_six_slide_pack:
        # O slide novo entra antes do explainer/autoridade antigo para manter
        # a narrativa: gancho -> tensao -> contexto -> explicacao -> CTA.
        raw_slides = [*raw_slides[:3], _legacy_context_slide(raw_slides), *raw_slides[3:]]

    slides: list[Any] = []
    for index, raw_slide in enumerate(raw_slides):
        if not isinstance(raw_slide, dict):
            slides.append(raw_slide)
            continue
        slide = normalize_slide(raw_slide, index)
        _repair_layout_semantics(slide)
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
        if slide["layoutId"] == "myth_fact":
            body = _text(fields.get("body"))
            fact_item = fields.get("item2") if isinstance(fields.get("item2"), dict) else {}
            fact = _text(fact_item.get("text"))
            fact_limit = int(spec.get("item_max", {}).get("text", 42))
            # Corrige Packs já salvos por uma versão anterior que havia cortado
            # o fato no começo da frase seguinte (por exemplo, terminando em "O").
            if body and fact and body.lower().startswith(fact.lower()):
                improved_fact = _fit_copy(body, fact_limit)
                if improved_fact.endswith((".", "!", "?")):
                    fact_item["text"] = improved_fact
                    fields["item2"] = fact_item
                    fact = improved_fact
            if fact and body.lower().startswith(fact.lower()):
                fields["body"] = body[len(fact):].lstrip(" .:;–—")
        slides.append(slide)

    _repair_missing_context_slide(slides)
    repaired["slides"] = slides
    repaired["carousel"] = slides
    if migrated_six_slide_pack:
        repaired["schemaVersion"] = PACK_SCHEMA_VERSION
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
    slides = pack_slides(pack)
    if not slides:
        return [f"slides precisa ser uma lista com {PACK_SLIDE_COUNT} itens"]
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
        errors.append(f"slide {PACK_SLIDE_COUNT} precisa usar cta_photo")
    if len(layouts) >= 4 and "explainer" not in layouts[2:5]:
        errors.append("slides 3 a 5 precisam incluir um explainer com contexto da IA")
    if len(set(layouts)) < 4:
        errors.append("use pelo menos 4 tipos de layout para manter ritmo visual")
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
