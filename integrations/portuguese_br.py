"""Pequenas correções de português do Brasil para textos gerados pelo projeto."""

from __future__ import annotations

import re


WORD_REPLACEMENTS = {
    "Voce": "Você",
    "voce": "você",
    "Nao": "Não",
    "nao": "não",
    "remedio": "remédio",
    "remedios": "remédios",
    "medico": "médico",
    "medicos": "médicos",
    "medica": "médica",
    "medicas": "médicas",
    "medicacao": "medicação",
    "indicacao": "indicação",
    "avaliacao": "avaliação",
    "informacao": "informação",
    "prescricao": "prescrição",
    "prescrever": "prescrever",
    "seguranca": "segurança",
    "saude": "saúde",
    "metabolica": "metabólica",
    "clinico": "clínico",
    "clinica": "clínica",
    "duvida": "dúvida",
    "Duvida": "Dúvida",
    "alimentacao": "alimentação",
    "Cansaco": "Cansaço",
    "cansaco": "cansaço",
    "so": "só",
    "forca": "força",
    "cronica": "crônica",
    "doenca": "doença",
    "solucao": "solução",
    "facil": "fácil",
    "noticia": "notícia",
    "tendencia": "tendência",
    "explicacao": "explicação",
    "avaliar": "avaliar",
    "Reforcar": "Reforçar",
    "reforcar": "reforçar",
}


PHRASE_REPLACEMENTS = {
    "GLP-1 sem transformar em prescrição": "GLP-1 sem transformar em prescrição",
    "Você acha que o remedio": "Você acha que o remédio",
    "Não prescrever medicamento, não citar dose e não prometer resultado.": (
        "Não prescrever medicamento, não citar dose e não prometer resultado."
    ),
}


def apply_portuguese_br_accents(text: str) -> str:
    """Corrige palavras frequentes que aparecem sem acento nos roteiros."""
    if not text:
        return text

    corrected = text
    for source, target in PHRASE_REPLACEMENTS.items():
        corrected = corrected.replace(source, target)

    for source, target in WORD_REPLACEMENTS.items():
        corrected = re.sub(rf"\b{re.escape(source)}\b", target, corrected)

    return corrected


VOICE_PHRASE_REPLACEMENTS = {
    "GLP-1": "G L P um",
    "glp-1": "G L P um",
    "Mounjaro": "Maundjáro",
    "mounjaro": "Maundjáro",
    "Ozempic": "Ozêmpic",
    "ozempic": "Ozêmpic",
    "Wegovy": "Uegóvi",
    "wegovy": "Uegóvi",
    "Rybelsus": "Ribélsus",
    "rybelsus": "Ribélsus",
    "Semaglutida": "Semaglutida",
    "semaglutida": "semaglutida",
    "Tirzepatida": "Tirzepatida",
    "tirzepatida": "tirzepatida",
}


def prepare_script_for_heygen_voice(text: str) -> str:
    """Prepara texto para a voz do HeyGen sem depender de interpretação livre."""
    if not text:
        return text

    voice_text = apply_portuguese_br_accents(text)
    for source, target in VOICE_PHRASE_REPLACEMENTS.items():
        voice_text = re.sub(rf"\b{re.escape(source)}\b", target, voice_text)

    voice_text = re.sub(r"\b30s\b", "trinta segundos", voice_text)
    voice_text = re.sub(r"\b(\d+)\s*%", r"\1 por cento", voice_text)
    voice_text = re.sub(r"\s+", " ", voice_text).strip()
    voice_text = re.sub(r"([.!?])\s+", r"\1\n", voice_text)

    return voice_text
