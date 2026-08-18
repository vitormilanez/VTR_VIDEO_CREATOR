"""Contrato visual do carrossel do Instituto Guilherme Martins.

Este modulo concentra o vocabulario fechado de layouts, limites editoriais e
metadados das fotos. Claude escolhe conteudo e composicao; o renderer continua
deterministico.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from api.services.medical_identity import (
    MEDICAL_DEFAULT_SAFE_CTA,
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
    ensure_medical_professional_identification,
    has_medical_publication_notice,
    has_prohibited_editorial_cta,
    safe_editorial_cta,
)

PACK_SCHEMA_VERSION = "institute-carousel-v2"
PACK_SLIDE_COUNT = 7
EDUCATIONAL_FLOW_VERSION = "educational-flow-v1"

# A apresentação é uma preferência local do Pack. Ela nunca participa do
# prompt/cache de conteúdo e pode mudar sem chamar o Claude.
PACK_FAMILIES = ("editorial", "didatico", "storytelling", "manifesto", "clinico")
PACK_THEMES = (
    "modernist-red",
    "modernist-teal",
    "ocean-deep",
    "soft-sage",
    "soft-rose",
)
DEFAULT_PACK_FAMILY = "didatico"
DEFAULT_PACK_THEME = "modernist-red"
LEGACY_PACK_THEME = "ocean-deep"

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

# Todos os Packs novos seguem esta sequência. Ela é usada no prompt, nos
# metadados de qualidade e em uma validação leve antes de salvar a resposta do
# Claude. O objetivo é ensinar em progressão, não colecionar frases de efeito.
EDUCATIONAL_SLIDE_STEPS = (
    ("Tema e objetivo", "Apresenta o assunto e o que a pessoa vai entender."),
    ("Contexto", "Organiza uma dúvida comum sem julgamento."),
    ("Conceito-chave", "Define o ponto central em linguagem simples."),
    ("Como funciona", "Explica o mecanismo ou contexto em etapas."),
    ("O que a fonte mostra", "Traduz dado, evidência ou implicação."),
    ("Cuidados e limites", "Mostra a ressalva necessária com clareza."),
    ("Resumo e próximo passo", "Retoma o aprendizado e orienta com segurança."),
)
EDUCATIONAL_EXPLANATORY_LAYOUTS = {
    "explainer",
    "three_points",
    "myth_fact",
    "number_stat",
    "do_dont",
    "doctor_quote",
}
_EDUCATIONAL_TONE_PATTERNS = (
    (
        re.compile(r"\bvoc[eê]\s+confunde\b", re.I),
        "substitua o tom acusatorio por uma comparacao ou explicacao neutra",
    ),
    (
        re.compile(r"\bvoc[eê]\s+(?:esta|está|ta)\s+fazendo\s+(?:tudo\s+)?errado\b", re.I),
        "retire o julgamento direto sobre quem le",
    ),
    (
        re.compile(r"\bningu[eé]m\s+(?:te\s+)?contou\b", re.I),
        "troque a frase de efeito por uma explicacao objetiva",
    ),
    (
        re.compile(r"\baquele\s+(?:produto|rem[eé]dio|medicamento|caneta)\s+que\s+(?:achei|vi)\s+por\s+a[ií]\b", re.I),
        "nomeie a duvida de forma objetiva em vez de usar uma referencia vaga",
    ),
)

# Biblioteca canônica de fotos do Pack. Os IDs permanecem estáveis para que
# carrosséis já salvos continuem apontando para a imagem escolhida.
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
    "institute-desk-pose": {
        "file": "data/pack_assets/photos/gui-instituto-escritorio-pose.png",
        "name": "Escritorio com mao apoiada",
        "description": "sentado a mesa, com livros e a marca do Instituto ao fundo",
        "facePointX": 0.46,
        "facePointY": 0.30,
        "brightness": 0.40,
    },
    "institute-reading-front": {
        "file": "data/pack_assets/photos/gui-instituto-leitura-frente.png",
        "name": "Leitura de frente",
        "description": "de frente a mesa com livro aberto e a marca do Instituto acima",
        "facePointX": 0.50,
        "facePointY": 0.34,
        "brightness": 0.42,
    },
    "institute-reading-side": {
        "file": "data/pack_assets/photos/gui-instituto-leitura-lateral.png",
        "name": "Leitura lateral",
        "description": "sentado de lado lendo um livro, com espaco escuro para texto",
        "facePointX": 0.38,
        "facePointY": 0.32,
        "brightness": 0.36,
    },
    "white-polo-portrait": {
        "file": "data/pack_assets/photos/gui-polo-retrato-escuro.jpeg",
        "name": "Retrato de polo branco",
        "description": "retrato vertical com mao no queixo e fundo escuro limpo",
        "facePointX": 0.50,
        "facePointY": 0.36,
        "brightness": 0.34,
    },
    "vivance-horizontal-portrait": {
        "file": "data/pack_assets/photos/gui-vivance-retrato-horizontal.png",
        "name": "Vivance — retrato horizontal",
        "description": "retrato horizontal externo, com marca parcial e espaco lateral para texto",
        "facePointX": 0.46,
        "facePointY": 0.38,
        "brightness": 0.54,
    },
    "vivance-seated-sign": {
        "file": "data/pack_assets/photos/gui-vivance-sentado-placa.png",
        "name": "Vivance — sentado com placa",
        "description": "sentado em primeiro plano com a placa do Instituto ao fundo e area livre a direita",
        "facePointX": 0.31,
        "facePointY": 0.39,
        "brightness": 0.48,
    },
    "vivance-seated-full-body": {
        "file": "data/pack_assets/photos/gui-vivance-sentado-corpo-inteiro.png",
        "name": "Vivance — sentado corpo inteiro",
        "description": "corpo inteiro sentado nos degraus, com fachada e marca do Instituto ao fundo",
        "facePointX": 0.42,
        "facePointY": 0.35,
        "brightness": 0.50,
    },
    "vivance-standing-crossed-arms": {
        "file": "data/pack_assets/photos/gui-vivance-em-pe-bracos-cruzados.png",
        "name": "Vivance — em pe, bracos cruzados",
        "description": "corpo inteiro em pe e de bracos cruzados diante da fachada do Instituto",
        "facePointX": 0.45,
        "facePointY": 0.25,
        "brightness": 0.50,
    },
    "vivance-seated-close": {
        "file": "data/pack_assets/photos/gui-vivance-sentado-close.png",
        "name": "Vivance — sentado em close",
        "description": "retrato vertical sentado, com a marca completa ao fundo e respiro a direita",
        "facePointX": 0.29,
        "facePointY": 0.34,
        "brightness": 0.48,
    },
    "vivance-crossed-arms-close": {
        "file": "data/pack_assets/photos/gui-vivance-bracos-cruzados-close.png",
        "name": "Vivance — bracos cruzados em close",
        "description": "retrato frontal de bracos cruzados com o simbolo do Instituto ao fundo",
        "facePointX": 0.50,
        "facePointY": 0.25,
        "brightness": 0.51,
    },
    "vivance-office-thoughtful": {
        "file": "data/pack_assets/photos/gui-vivance-escritorio-pensativo.png",
        "name": "Vivance — escritorio pensativo",
        "description": "sentado a mesa com as maos junto ao rosto, notebook e marca iluminada ao fundo",
        "facePointX": 0.48,
        "facePointY": 0.40,
        "brightness": 0.32,
    },
    "vivance-office-standing": {
        "file": "data/pack_assets/photos/gui-vivance-escritorio-em-pe.png",
        "name": "Vivance — em pe no escritorio",
        "description": "retrato vertical em pe no escritorio escuro, com a marca iluminada ao fundo",
        "facePointX": 0.38,
        "facePointY": 0.24,
        "brightness": 0.34,
    },
    "vivance-outdoor-half-body": {
        "file": "data/pack_assets/photos/gui-vivance-externo-meio-corpo.png",
        "name": "Vivance — externo meio corpo",
        "description": "retrato externo em meio corpo, com fachada, plantas e marca parcial ao fundo",
        "facePointX": 0.50,
        "facePointY": 0.24,
        "brightness": 0.55,
    },
    "vivance-seated-portrait": {
        "file": "data/pack_assets/photos/gui-vivance-sentado-retrato.png",
        "name": "Vivance — sentado retrato",
        "description": "retrato vertical sentado diante da marca, adequado para composicao central",
        "facePointX": 0.43,
        "facePointY": 0.28,
        "brightness": 0.55,
    },
    "vivance-seated-close-alt": {
        "file": "data/pack_assets/photos/gui-vivance-sentado-close-alternativo.png",
        "name": "Vivance — sentado em close alternativo",
        "description": "retrato vertical sentado em primeiro plano, com marca e area livre a direita",
        "facePointX": 0.29,
        "facePointY": 0.34,
        "brightness": 0.48,
    },
    "vivance-outdoor-hands-pockets": {
        "file": "data/pack_assets/photos/gui-vivance-externo-maos-bolsos.png",
        "name": "Vivance — externo com maos nos bolsos",
        "description": "retrato externo em pe com as maos nos bolsos e fachada desfocada",
        "facePointX": 0.50,
        "facePointY": 0.25,
        "brightness": 0.55,
    },
    "vivance-crossed-arms-portrait": {
        "file": "data/pack_assets/photos/gui-vivance-bracos-cruzados-retrato.png",
        "name": "Vivance — bracos cruzados retrato",
        "description": "retrato vertical frontal de bracos cruzados, com simbolo do Instituto ao fundo",
        "facePointX": 0.51,
        "facePointY": 0.25,
        "brightness": 0.51,
    },
    "vivance-outdoor-full-body": {
        "file": "data/pack_assets/photos/gui-vivance-externo-corpo-inteiro.png",
        "name": "Vivance — externo corpo inteiro",
        "description": "corpo inteiro em pe diante da fachada, com a marca do Instituto ao fundo",
        "facePointX": 0.50,
        "facePointY": 0.25,
        "brightness": 0.55,
    },
}

EMPTY_ITEM = {"title": "", "text": ""}
FIELD_NAMES = (
    "eyebrow",
    "headline",
    "subheadline",
    "coverNote",
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
    # Os layouts com fotografia tambem funcionam como composicoes graficas.
    # ``photoId`` continua disponivel, mas nunca e obrigatorio: o editor pode
    # remover a imagem sem trocar o texto, o layout ou a etapa educativa.
    "hero_photo": {"required": ("eyebrow", "headline"), "max": {"eyebrow": 22, "headline": 46, "coverNote": 180, "footer": 48}},
    "photo_split": {"required": ("headline", "body"), "max": {"eyebrow": 22, "headline": 52, "body": 160, "footer": 48}},
    "big_statement": {"required": ("headline",), "max": {"headline": 64, "footer": 90}},
    "question": {"required": ("headline",), "max": {"eyebrow": 30, "headline": 52, "body": 110, "footer": 48}},
    # Os dois painéis comportam duas linhas confortáveis. O limite anterior de
    # 38 caracteres obrigava o modelo (ou o reparo local) a cortar a conclusão
    # de fatos clínicos, transformando frases corretas em fragmentos.
    "myth_fact": {"required": ("item1", "item2"), "max": {"body": 90}, "item_max": {"title": 12, "text": 72}},
    "number_stat": {"required": ("statistic", "headline", "caption"), "max": {"eyebrow": 22, "statistic": 6, "headline": 60, "body": 110, "caption": 72}},
    "three_points": {"required": ("headline", "item1", "item2", "item3"), "max": {"headline": 40}, "item_max": {"title": 24, "text": 90}},
    "explainer": {"required": ("headline", "body"), "max": {"eyebrow": 22, "headline": 56, "body": 320, "disclaimer": 90}, "item_max": {"title": 24, "text": 54}},
    "doctor_quote": {"required": ("quote", "caption"), "max": {"quote": 90, "caption": 48}},
    "photo_overlay": {"required": ("eyebrow", "headline"), "max": {"eyebrow": 22, "headline": 60, "coverNote": 180, "footer": 48}},
    "do_dont": {"required": ("item1", "item2"), "max": {"disclaimer": 90}, "item_max": {"title": 34, "text": 34}},
    "cta_photo": {"required": ("headline", "cta", "disclaimer", "footer"), "max": {"headline": 62, "body": 70, "cta": 22, "disclaimer": 220, "footer": 100}},
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
        return _remove_dangling_words(text)
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

_INCOMPLETE_TAIL_WORDS = _DANGLING_WORDS | {
    "ainda",
    "até",
    "este",
    "esta",
    "foi",
    "mas",
    "nem",
    "não",
    "pode",
    "podem",
    "porque",
    "quando",
    "são",
    "seu",
    "seus",
    "ser",
    "sua",
    "suas",
    "vem",
    "é",
}


def _remove_dangling_words(value: str) -> str:
    """Remove conectivos finais que denunciam um corte mecanico de copy."""
    text = _text(value)
    normalized_incomplete_words = {
        "".join(
            char
            for char in unicodedata.normalize("NFKD", word.casefold())
            if not unicodedata.combining(char)
        )
        for word in _INCOMPLETE_TAIL_WORDS
    }
    while text:
        last_word = text.split()[-1].casefold().strip(".,;:!?()[]{}\"'")
        normalized_last_word = "".join(
            char
            for char in unicodedata.normalize("NFKD", last_word)
            if not unicodedata.combining(char)
        )
        if normalized_last_word not in normalized_incomplete_words:
            break
        text = " ".join(text.split()[:-1]).rstrip(" ,;:-–—")
    return text


def _looks_incomplete(value: Any) -> bool:
    """Detecta caudas que denunciam fragmento cortado antes do renderer."""
    text = _text(value)
    if not text:
        return False
    last_word = text.split()[-1].casefold().strip(".,;:!?()[]{}\"'")
    last_word = "".join(
        char
        for char in unicodedata.normalize("NFKD", last_word)
        if not unicodedata.combining(char)
    )
    incomplete_words = {
        "".join(
            char
            for char in unicodedata.normalize("NFKD", word.casefold())
            if not unicodedata.combining(char)
        )
        for word in _INCOMPLETE_TAIL_WORDS
    }
    return last_word in incomplete_words


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


def educational_flow_issues(pack: dict[str, Any]) -> list[str]:
    """Aponta quando a resposta foge da trilha educativa do carrossel.

    A verificacao é propositalmente pequena: ela não tenta reescrever medicina
    de forma determinística, mas impede que a resposta volte ao padrão de
    confronto, frases vagas e explicação tardia visto em versões antigas.
    """
    raw_slides = pack_slides(pack)
    if len(raw_slides) != PACK_SLIDE_COUNT:
        return []
    slides = [
        normalize_slide(slide, index)
        for index, slide in enumerate(raw_slides)
        if isinstance(slide, dict)
    ]
    if len(slides) != PACK_SLIDE_COUNT:
        return []

    issues: list[str] = []
    layouts = [str(slide.get("layoutId") or "") for slide in slides]
    if "explainer" not in layouts[2:4]:
        issues.append("slides 3 ou 4: inclua um explainer para explicar o conceito antes dos dados")
    explanation_count = sum(
        layout in EDUCATIONAL_EXPLANATORY_LAYOUTS for layout in layouts[2:6]
    )
    if explanation_count < 2:
        issues.append("slides 3 a 6: inclua pelo menos dois layouts de explicacao educativa")

    for index, slide in enumerate(slides, start=1):
        fields = slide.get("fields") if isinstance(slide.get("fields"), dict) else {}
        values: list[str] = []
        for value in fields.values():
            if isinstance(value, dict):
                values.extend(_text(part) for part in value.values())
            else:
                values.append(_text(value))
        slide_copy = " ".join(value for value in values if value)
        for pattern, guidance in _EDUCATIONAL_TONE_PATTERNS:
            if pattern.search(slide_copy):
                issues.append(f"slide {index}: {guidance}")
    return list(dict.fromkeys(issues))


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
        "cta": MEDICAL_DEFAULT_SAFE_CTA,
        "footer": "Arraste para o lado",
        "disclaimer": MEDICAL_EDUCATIONAL_DISCLAIMER,
    }
    if layout_id == "cta_photo":
        scalar_fallbacks.update(
            {
                "headline": fields.get("headline") or "Converse com seu medico",
                "body": fields.get("body") or "Use esta informacao para revisar sintomas e duvidas.",
                "cta": safe_editorial_cta(fields.get("cta")),
                "disclaimer": MEDICAL_EDUCATIONAL_DISCLAIMER,
                "footer": MEDICAL_PROFESSIONAL_IDENTIFICATION,
            }
        )
    elif layout_id == "doctor_quote":
        scalar_fallbacks.update(
            {
                "quote": fields.get("quote") or fields.get("headline") or "Acompanhamento individual muda a seguranca do cuidado.",
                "caption": fields.get("caption") or "Dr. Guilherme Martins",
            }
        )
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


# Rotulos em portugues de cada layout. Ficam aqui para que interface, arquivo
# exportado e API falem exatamente a mesma lingua sobre o mesmo componente.
LAYOUT_LABELS: dict[str, str] = {
    "hero_photo": "Abertura com foto",
    "photo_split": "Explicação com foto",
    "big_statement": "Ideia-chave",
    "question": "Dúvida comum",
    "myth_fact": "Mito e fato",
    "number_stat": "Dado explicado",
    "three_points": "Pontos para entender",
    "explainer": "Explicação simples",
    "doctor_quote": "Orientação profissional",
    "photo_overlay": "Tema com foto",
    "do_dont": "Evite e prefira",
    "cta_photo": "Resumo e próximo passo",
}

# Rotulo legivel de cada campo, usado no editor por slide e no texto exportado.
FIELD_LABELS: dict[str, str] = {
    "eyebrow": "Chapéu",
    "headline": "Título",
    "subheadline": "Apoio",
    "coverNote": "Mensagem na capa",
    "body": "Texto",
    "statistic": "Número",
    "item1": "Bloco 1",
    "item2": "Bloco 2",
    "item3": "Bloco 3",
    "quote": "Citação",
    "cta": "Chamada",
    "footer": "Rodapé",
    "caption": "Legenda do slide",
    "disclaimer": "Aviso",
    "photoId": "Foto",
}


def slide_export_text(slide: dict[str, Any]) -> str:
    """Texto completo do slide para o arquivo entregue ao time.

    A versao anterior exportava apenas ``headline`` e ``body``. Slides de
    ``three_points``, ``myth_fact``, ``do_dont``, ``number_stat`` e
    ``doctor_quote`` guardam o conteudo em ``item1..3``, ``statistic`` ou
    ``quote``, entao o arquivo saia praticamente vazio justamente nas telas com
    mais informacao.
    """
    normalized = normalize_slide(slide)
    fields = normalized["fields"]
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        text = _text(value)
        if text:
            lines.append(f"{label}: {text}" if label else text)

    add("", fields.get("eyebrow"))
    add("", fields.get("headline") or fields.get("quote"))
    if _text(fields.get("statistic")):
        add("Número", fields.get("statistic"))
    add("", fields.get("subheadline"))
    add("", fields.get("body"))
    for name in ("item1", "item2", "item3"):
        item = fields.get(name)
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        text = _text(item.get("text"))
        if title and text:
            lines.append(f"- {title}: {text}")
        elif title or text:
            lines.append(f"- {title or text}")
    add("Legenda", fields.get("caption"))
    add("Mensagem na capa", fields.get("coverNote"))
    add("Chamada", fields.get("cta"))
    add("Rodapé", fields.get("footer"))
    add("Aviso", fields.get("disclaimer"))
    return "\n".join(lines)


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value or "").casefold())
        if not unicodedata.combining(char)
    )


_ORDINAL_STEP_MARKERS = (
    (("primeiro", "primeira"), "Primeiro"),
    (("segundo", "segunda"), "Segundo"),
    (("terceiro", "terceira"), "Terceiro"),
)
_ORDINAL_STEP_RE = re.compile(
    r"^(?:o|a|no|na)?\s*(primeir[oa]|segund[oa]|terceir[oa])\b[\s,:–—-]*",
    re.I,
)
_NUMBERED_STEP_RE = re.compile(r"^([1-3])\s*[.)°º-]\s+")


def _sentences(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _capitalize_first(value: str) -> str:
    text = _text(value)
    return text[:1].upper() + text[1:] if text else text


def explainer_steps_from_body(body: Any) -> tuple[str, list[dict[str, str]]]:
    """Separa uma enumeracao ja escrita no body em passos, sem inventar texto.

    O layout ``explainer`` renderiza tres cartoes de etapa. Quando o Claude
    escreve a explicacao como um paragrafo enumerado ("O primeiro... O
    segundo... O terceiro...") e deixa ``item1..item3`` vazios, a grade de
    etapas sai em branco e o slide exportado fica com metade da tela vazia.

    Esta funcao reaproveita exatamente as frases ja aprovadas: nada e criado,
    reescrito ou pedido ao Claude. Se a enumeracao nao existir, devolve o body
    intacto e nenhuma etapa, e o renderer usa o estado de paragrafo.
    """
    sentences = _sentences(body)
    if len(sentences) < 3:
        return _text(body), []

    lead: list[str] = []
    tail: list[str] = []
    steps: list[dict[str, str]] = []
    expected = 0
    for sentence in sentences:
        if len(steps) >= 3:
            tail.append(sentence)
            continue
        title = ""
        remainder = ""
        ordinal = _ORDINAL_STEP_RE.match(sentence)
        if ordinal:
            word = ordinal.group(1).casefold()
            for variants, label in _ORDINAL_STEP_MARKERS:
                if word in variants:
                    title = label
                    break
            remainder = sentence[ordinal.end() :]
        else:
            numbered = _NUMBERED_STEP_RE.match(sentence)
            if numbered:
                title = _ORDINAL_STEP_MARKERS[int(numbered.group(1)) - 1][1]
                remainder = sentence[numbered.end() :]
        if not title or _ORDINAL_STEP_MARKERS[expected][1] != title:
            (tail if steps else lead).append(sentence)
            continue
        remainder = _capitalize_first(remainder)
        if not remainder:
            (tail if steps else lead).append(sentence)
            continue
        steps.append({"title": title, "text": remainder})
        expected += 1

    if len(steps) < 2:
        return _text(body), []
    return _text(" ".join(lead + tail)), steps


def _repair_explainer_steps(fields: dict[str, Any], spec: dict[str, Any]) -> None:
    """Preenche as etapas do explainer a partir de uma enumeracao ja escrita."""
    if any(_has_item_content(fields.get(name)) for name in ("item1", "item2", "item3")):
        return
    remaining_body, steps = explainer_steps_from_body(fields.get("body"))
    if not steps:
        return
    item_limits = spec.get("item_max", {})
    for index, step in enumerate(steps, start=1):
        fields[f"item{index}"] = {
            "title": _fit_copy(step["title"], item_limits.get("title", 24)),
            "text": _fit_copy(step["text"], item_limits.get("text", 54)),
        }
    fields["body"] = _fit_copy(remaining_body, spec.get("max", {}).get("body", 320))


# Sinais locais de clareza. Eles nao chamam o Claude: apenas medem o que ja
# esta salvo, para que o editor veja antes de exportar quando um slide ficou
# denso demais, vazio demais ou com um numero sem explicacao.
_CLARITY_JARGON = (
    "agonista",
    "incretina",
    "farmacocinética",
    "farmacocinetica",
    "hipoglicemiante",
    "termogênese",
    "termogenese",
    "lipólise",
    "lipolise",
    "resistência insulínica",
    "resistencia insulinica",
    "comorbidade",
    "adiposidade",
    "metanálise",
    "metanalise",
    "randomizado",
    "placebo-controlado",
    "biodisponibilidade",
    "receptor gip",
    "glp-1",
)
_NUMERIC_CLAIM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%|\b\d{2,}\b")

# Quantidade de texto que cada layout comporta com leitura confortavel. O
# renderer preenche a tela com esses volumes; muito abaixo disso o PNG sai com
# area vazia, muito acima ele fica denso para leitura em celular.
LAYOUT_COMFORT_RANGE: dict[str, tuple[int, int]] = {
    "hero_photo": (24, 200),
    "photo_split": (90, 260),
    "big_statement": (30, 150),
    "question": (60, 220),
    "myth_fact": (70, 250),
    "number_stat": (60, 220),
    "three_points": (140, 400),
    "explainer": (140, 480),
    "doctor_quote": (50, 170),
    "photo_overlay": (24, 180),
    "do_dont": (60, 220),
    "cta_photo": (60, 200),
}


# Campos que cada layout realmente desenha no PNG. Medir densidade sobre o
# dicionario inteiro contava texto invisivel (por exemplo o ``caption`` do
# cta_photo, que o renderer troca pelo aviso fixo) e acusava slides densos que
# na pratica estavam vazios.
LAYOUT_READER_FIELDS: dict[str, tuple[str, ...]] = {
    "hero_photo": ("eyebrow", "headline", "coverNote", "footer"),
    "photo_split": ("eyebrow", "headline", "body", "footer"),
    "big_statement": ("eyebrow", "headline", "footer"),
    "question": ("eyebrow", "headline", "body", "footer"),
    "myth_fact": ("item1", "item2", "body"),
    "number_stat": ("eyebrow", "statistic", "headline", "body", "caption"),
    "three_points": ("eyebrow", "headline", "item1", "item2", "item3"),
    "explainer": ("eyebrow", "headline", "body", "item1", "item2", "item3"),
    "doctor_quote": ("quote", "caption"),
    "photo_overlay": ("eyebrow", "headline", "coverNote", "footer"),
    "do_dont": ("item1", "item2", "item3"),
    # O disclaimer e o footer do slide final sao textos fixos de compliance:
    # eles ocupam espaco, mas o editor nao os controla, entao ficam fora da
    # medida de densidade editavel.
    "cta_photo": ("headline", "body", "cta"),
}


# Campos que o editor pode alterar em cada layout, na ordem em que aparecem no
# slide. Sao os campos de ``LAYOUT_READER_FIELDS`` mais os textos de apoio que
# o renderer desenha mas nao contam para a densidade de leitura.
LAYOUT_EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "hero_photo": ("eyebrow", "headline", "coverNote", "footer"),
    "photo_split": ("eyebrow", "headline", "body", "footer"),
    "big_statement": ("eyebrow", "headline", "footer"),
    "question": ("eyebrow", "headline", "body", "footer"),
    "myth_fact": ("item1", "item2", "body"),
    "number_stat": ("eyebrow", "statistic", "headline", "body", "caption"),
    "three_points": ("eyebrow", "headline", "item1", "item2", "item3"),
    "explainer": ("eyebrow", "headline", "body", "item1", "item2", "item3", "disclaimer"),
    "doctor_quote": ("quote", "caption"),
    "photo_overlay": ("eyebrow", "headline", "coverNote", "footer"),
    "do_dont": ("item1", "item2", "item3", "disclaimer"),
    # ``disclaimer`` e ``footer`` do slide final sao travados por compliance.
    "cta_photo": ("headline", "body", "cta"),
}


def slide_reader_text(slide: dict[str, Any]) -> str:
    """Somente o texto editavel que a pessoa le no PNG deste layout."""
    fields = slide.get("fields") if isinstance(slide.get("fields"), dict) else {}
    layout_id = str(slide.get("layoutId") or slide.get("layout") or "")
    names = LAYOUT_READER_FIELDS.get(
        layout_id,
        ("eyebrow", "headline", "subheadline", "body", "statistic", "quote", "caption", "cta"),
    )
    parts: list[str] = []
    for name in names:
        value = fields.get(name)
        if isinstance(value, dict):
            parts.extend(part for part in (_text(value.get("title")), _text(value.get("text"))) if part)
        elif _text(value):
            parts.append(_text(value))
    return " ".join(parts)


def slide_clarity(slide: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Mede densidade e clareza de um slide de forma local e deterministica."""
    normalized = normalize_slide(slide, index)
    layout_id = normalized["layoutId"]
    fields = normalized["fields"]
    text = slide_reader_text(normalized)
    characters = len(text)
    words = len([word for word in re.split(r"\s+", text) if word])
    minimum, maximum = LAYOUT_COMFORT_RANGE.get(layout_id, (60, 260))

    if characters < minimum:
        density = "vazio"
    elif characters > maximum:
        density = "denso"
    else:
        density = "equilibrado"

    warnings: list[str] = []
    if density == "vazio":
        warnings.append("pouco texto para o layout; o PNG sai com area vazia")
    if density == "denso":
        warnings.append("texto acima do confortavel para leitura no celular")

    lowered = _strip_accents(text.casefold()) if text else ""
    jargon = sorted(
        {
            term
            for term in _CLARITY_JARGON
            if _strip_accents(term) in lowered
        }
    )
    if jargon:
        warnings.append("termo tecnico presente: confirme se ele foi explicado")

    # Um numero precisa de uma frase que diga o que ele significa. A checagem
    # olha o texto que sobra fora da frase onde o numero aparece: se quase nada
    # sobra, o dado esta isolado na tela.
    sentences = _sentences(text)
    numeric_sentences = [sentence for sentence in sentences if _NUMERIC_CLAIM_RE.search(sentence)]
    if numeric_sentences:
        context = " ".join(sentence for sentence in sentences if sentence not in numeric_sentences)
        if len(context) < 45:
            warnings.append("dado numerico sem explicacao do que ele significa")

    longest_sentence = max((len(sentence.split()) for sentence in _sentences(text)), default=0)
    if longest_sentence > 28:
        warnings.append("frase longa demais para leitura rapida")

    return {
        "slide": index + 1,
        "layoutId": layout_id,
        "characters": characters,
        "words": words,
        "comfortMin": minimum,
        "comfortMax": maximum,
        "density": density,
        "longestSentenceWords": longest_sentence,
        "jargon": jargon,
        "warnings": warnings,
    }


def pack_clarity(pack: dict[str, Any]) -> dict[str, Any]:
    """Relatorio de clareza do carrossel inteiro. Nenhuma chamada de IA."""
    slides = [slide for slide in pack_slides(pack) if isinstance(slide, dict)]
    per_slide = [slide_clarity(slide, index) for index, slide in enumerate(slides)]
    layouts = [entry["layoutId"] for entry in per_slide]
    repeated = sorted(
        {
            layouts[index]
            for index in range(1, len(layouts))
            if layouts[index] == layouts[index - 1]
        }
    )
    return {
        "slides": per_slide,
        "balanced": sum(1 for entry in per_slide if entry["density"] == "equilibrado"),
        "empty": [entry["slide"] for entry in per_slide if entry["density"] == "vazio"],
        "dense": [entry["slide"] for entry in per_slide if entry["density"] == "denso"],
        "repeatedAdjacentLayouts": repeated,
        "distinctLayouts": len(set(layouts)),
        "warnings": sum(len(entry["warnings"]) for entry in per_slide),
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
    repaired["caption"] = ensure_medical_professional_identification(repaired.get("caption"))
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
        if slide["layoutId"] == "explainer":
            # Reaproveita a enumeracao que ja existe no body antes de qualquer
            # fallback: nenhuma chamada de IA e nenhum texto inventado.
            _repair_explainer_steps(fields, spec)
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
    if len(slides) >= PACK_SLIDE_COUNT and isinstance(slides[-1], dict):
        final_slide = slides[-1]
        if final_slide.get("layoutId") == "cta_photo" and isinstance(final_slide.get("fields"), dict):
            # Campos bloqueados: aviso integral e CTA editorial seguro no último slide.
            final_slide["fields"]["cta"] = safe_editorial_cta(
                final_slide["fields"].get("cta")
            )
            final_slide["fields"]["disclaimer"] = MEDICAL_EDUCATIONAL_DISCLAIMER
            final_slide["fields"]["footer"] = MEDICAL_PROFESSIONAL_IDENTIFICATION
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
    elif (
        len(layouts) >= PACK_SLIDE_COUNT
        and _text(normalized[-1]["fields"].get("footer")) != MEDICAL_PROFESSIONAL_IDENTIFICATION
    ):
        errors.append(f"slide {PACK_SLIDE_COUNT}: footer precisa conter a identificacao profissional obrigatoria")
    if len(layouts) >= PACK_SLIDE_COUNT and layouts[-1] == "cta_photo":
        final_fields = normalized[-1]["fields"]
        if _text(final_fields.get("disclaimer")) != MEDICAL_EDUCATIONAL_DISCLAIMER:
            errors.append(f"slide {PACK_SLIDE_COUNT}: disclaimer precisa conter o aviso educativo completo")
        if has_prohibited_editorial_cta(final_fields.get("cta")):
            errors.append(f"slide {PACK_SLIDE_COUNT}: CTA comercial ou de captacao nao e permitido")
    if len(layouts) >= 4 and "explainer" not in layouts[2:5]:
        errors.append("slides 3 a 5 precisam incluir um explainer com contexto da IA")
    if len(set(layouts)) < 4:
        errors.append("use pelo menos 4 tipos de layout para manter ritmo visual")
    slides_with_photo = [
        bool(_text(slide["fields"].get("photoId")))
        for slide in normalized
    ]
    if sum(slides_with_photo) > 3:
        errors.append("o carrossel pode ter no maximo 3 slides com foto")
    for index in range(1, len(layouts)):
        if (
            slides_with_photo[index - 1]
            and slides_with_photo[index]
            and layouts[index - 1] in FULL_BLEED_PHOTO_LAYOUTS
            and layouts[index] in FULL_BLEED_PHOTO_LAYOUTS
        ):
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

        for name in ("headline", "body", "quote"):
            if _looks_incomplete(fields.get(name)):
                errors.append(f"slide {index}: {name} termina em frase incompleta")

        if layout_id == "myth_fact":
            expected_labels = (("item1", "mito"), ("item2", "fato"))
            for item_name, expected_label in expected_labels:
                item = fields.get(item_name) if isinstance(fields.get(item_name), dict) else {}
                if _text(item.get("title")).casefold() != expected_label:
                    errors.append(
                        f"slide {index}: {item_name}.title precisa ser {expected_label.title()}"
                    )
                if _looks_incomplete(item.get("text")):
                    errors.append(f"slide {index}: {item_name}.text termina em frase incompleta")

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
    elif not has_medical_publication_notice(caption):
        errors.append("caption precisa conter o aviso completo e a identificacao profissional")
    if has_prohibited_editorial_cta(caption):
        errors.append("caption nao pode conter CTA comercial ou de captacao")
    if _EMOJI_RE.search(caption):
        errors.append("caption nao pode ter emojis")
    return list(dict.fromkeys(errors))
