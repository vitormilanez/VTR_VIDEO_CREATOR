"""Perfil editorial canônico e identificação dos materiais de publicação."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


_PROFILE_PATH = Path(__file__).resolve().parents[2] / "shared" / "medical_editorial_profile.json"
MEDICAL_EDITORIAL_PROFILE: dict[str, Any] = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
MEDICAL_EDITORIAL_PROFILE_VERSION = str(MEDICAL_EDITORIAL_PROFILE["schemaVersion"])

_PROFESSIONAL = MEDICAL_EDITORIAL_PROFILE["professional"]
_PUBLICATION = MEDICAL_EDITORIAL_PROFILE["publication"]
_EDITORIAL = MEDICAL_EDITORIAL_PROFILE["editorial"]

MEDICAL_PROFESSIONAL_IDENTIFICATION = str(_PROFESSIONAL["identification"])
MEDICAL_ROLE_AND_REGISTERED_SPECIALTY = (
    f'{_PROFESSIONAL["publicRole"]} | '
    f'{_PROFESSIONAL["registeredSpecialty"]} – {_PROFESSIONAL["rqe"]}'
)
MEDICAL_EDUCATIONAL_DISCLAIMER = str(_PUBLICATION["disclaimer"])
MEDICAL_PUBLICATION_NOTICE = (
    f"{MEDICAL_EDUCATIONAL_DISCLAIMER}\n{MEDICAL_PROFESSIONAL_IDENTIFICATION}"
)
MEDICAL_EDITORIAL_ARCHETYPE = str(_EDITORIAL["archetype"])
MEDICAL_DEFAULT_SAFE_CTA = str(_EDITORIAL["defaultSafeCta"])
MEDICAL_MINIMUM_END_CARD_SECONDS = float(_PUBLICATION["minimumEndCardSeconds"])
MEDICAL_PROHIBITED_CTA_PATTERNS = tuple(
    re.compile(str(pattern), re.I) for pattern in _EDITORIAL["prohibitedCtaPatterns"]
)
MEDICAL_EDITORIAL_PROMPT = "\n".join(
    [
        "PERFIL EDITORIAL CANÔNICO DO DR. GUILHERME:",
        f"- Arquétipo: {MEDICAL_EDITORIAL_ARCHETYPE}",
        *(f"- {rule}" for rule in _EDITORIAL["rules"]),
        "- Aviso final exato: " + MEDICAL_PUBLICATION_NOTICE.replace("\n", " | "),
        (
            "- O sistema aplica e valida o aviso final de forma determinística. Não o transforme "
            "em fala, CTA ou elemento visual gerado, exceto quando o prompt pedir explicitamente "
            "os campos finais de uma publicação."
        ),
    ]
)

_LEGACY_PUBLICATION_NOTICES = (
    "Conteúdo educativo. Não substitui avaliação médica individual.",
    "Conteudo educativo. Nao substitui avaliacao medica individual.",
    "Conteúdo educativo. Não substitui avaliação médica.",
    "Conteudo educativo. Nao substitui avaliacao medica.",
)


def _normalized(value: Any) -> str:
    """Compara o texto sem tornar acentos ou espaços uma fonte de duplicação."""
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def has_medical_professional_identification(value: Any) -> bool:
    return _normalized(MEDICAL_PROFESSIONAL_IDENTIFICATION) in _normalized(value)


def has_medical_publication_notice(value: Any) -> bool:
    return _normalized(MEDICAL_PUBLICATION_NOTICE) in _normalized(value)


def has_prohibited_editorial_cta(value: Any) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in MEDICAL_PROHIBITED_CTA_PATTERNS)


def safe_editorial_cta(value: Any, *, fallback: str = MEDICAL_DEFAULT_SAFE_CTA) -> str:
    """Preserva CTAs educativos e troca captação/venda pelo fallback canônico."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or has_prohibited_editorial_cta(text):
        return fallback
    return text


def strip_prohibited_editorial_ctas(value: Any) -> str:
    """Remove chamadas proibidas sem descartar o restante da copy publicável."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    clean_blocks: list[str] = []
    for block in re.split(r"\n{2,}", text):
        clean_lines: list[str] = []
        for line in block.splitlines():
            sentences = re.split(r"(?<=[.!?])\s+", line.strip())
            clean_line = " ".join(
                sentence.strip()
                for sentence in sentences
                if sentence.strip() and not has_prohibited_editorial_cta(sentence)
            )
            if clean_line:
                clean_lines.append(clean_line)
        if clean_lines:
            clean_blocks.append("\n".join(clean_lines))
    return "\n\n".join(clean_blocks).strip()


def _without_existing_publication_notice(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(re.escape(MEDICAL_PUBLICATION_NOTICE), "", text, flags=re.I)
    text = re.sub(re.escape(MEDICAL_EDUCATIONAL_DISCLAIMER), "", text, flags=re.I)
    text = re.sub(re.escape(MEDICAL_PROFESSIONAL_IDENTIFICATION), "", text, flags=re.I)
    for notice in _LEGACY_PUBLICATION_NOTICES:
        text = re.sub(re.escape(notice), "", text, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", strip_prohibited_editorial_ctas(text)).strip()


def ensure_medical_publication_notice(value: Any) -> str:
    """Acrescenta o aviso completo uma única vez, depois da copy editorial."""
    sanitized = strip_prohibited_editorial_ctas(value)
    if has_medical_publication_notice(sanitized):
        text = sanitized.replace("\r\n", "\n").replace("\r", "\n").strip()
        return re.sub(r"\n{3,}", "\n\n", text)
    text = _without_existing_publication_notice(sanitized)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return f"{text}\n\n{MEDICAL_PUBLICATION_NOTICE}" if text else MEDICAL_PUBLICATION_NOTICE


def ensure_medical_professional_identification(value: Any) -> str:
    """Compatibilidade: materiais publicáveis agora recebem o aviso completo."""
    return ensure_medical_publication_notice(value)
