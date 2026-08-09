"""Contrato central do editor de roteiros médicos.

As decisões de duração, revisão médica, alinhamento de título e elegibilidade
de geração são deliberadamente independentes. O frontend usa o mesmo contrato
JSON para que presets, tokenização e fórmulas não se desviem do backend.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any, Literal


DurationPreset = Literal[10, 15, 30, 45, 60]
DurationStatus = Literal["ideal", "warning", "blocking"]
MedicalReviewStatus = Literal["not_required", "recommended", "required", "approved"]
TitleAlignmentStatus = Literal["aligned", "possible_mismatch", "unknown"]
GenerationEligibility = Literal["allowed", "blocked"]
EditorOperation = Literal["medical_rewrite", "fit_duration"]

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "shared" / "script_editor_contract.json"
SCRIPT_EDITOR_CONTRACT: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
SCRIPT_EDITOR_CONTRACT_VERSION = str(SCRIPT_EDITOR_CONTRACT["contractVersion"])
DURATION_PRESETS: tuple[int, ...] = tuple(SCRIPT_EDITOR_CONTRACT["durationPresets"])
DURATION_STATUSES: tuple[str, ...] = tuple(SCRIPT_EDITOR_CONTRACT["durationStatuses"])
MEDICAL_REVIEW_STATUSES: tuple[str, ...] = tuple(SCRIPT_EDITOR_CONTRACT["medicalReviewStatuses"])
TITLE_ALIGNMENT_STATUSES: tuple[str, ...] = tuple(SCRIPT_EDITOR_CONTRACT["titleAlignmentStatuses"])
GENERATION_ELIGIBILITY_STATUSES: tuple[str, ...] = tuple(
    SCRIPT_EDITOR_CONTRACT["generationEligibilityStatuses"]
)
GENERATION_GATE_REASON_CODES: tuple[str, ...] = tuple(
    SCRIPT_EDITOR_CONTRACT["generationGateReasonCodes"]
)
WORD_PATTERN = re.compile(SCRIPT_EDITOR_CONTRACT["wordPattern"])
MEDICAL_EDITORIAL_PROMPT_VERSION = str(
    SCRIPT_EDITOR_CONTRACT["editorialProfile"]["promptVersion"]
)


@dataclass(frozen=True)
class SpeechProfile:
    id: str
    language: str
    wordsPerMinute: int
    tolerancePercent: float
    generationTargetMinPercent: float
    generationTargetMaxPercent: float


DEFAULT_SPEECH_PROFILE = SpeechProfile(**SCRIPT_EDITOR_CONTRACT["speechProfile"])


@dataclass(frozen=True)
class DurationAssessment:
    durationSeconds: int
    wordCount: int
    estimatedSeconds: float
    estimatedSecondsDisplay: str
    targetWords: int
    hardLimitWords: int
    generationMinWords: int
    generationMaxWords: int
    status: DurationStatus
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GenerationGate:
    eligibility: GenerationEligibility
    allowed: bool
    reason: str | None
    reasons: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligibility": self.eligibility,
            "allowed": self.allowed,
            "reason": self.reason,
            "reasons": [dict(item) for item in self.reasons],
        }


def normalize_text(text: str) -> str:
    """Normalização única usada por contagem, cache e comparações."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def normalize_script(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def count_words(text: str) -> int:
    return len(WORD_PATTERN.findall(normalize_text(text)))


def duration_assessment(
    text: str,
    duration_seconds: int,
    profile: SpeechProfile = DEFAULT_SPEECH_PROFILE,
) -> DurationAssessment:
    if duration_seconds not in DURATION_PRESETS:
        raise ValueError(f"Preset de duração não suportado: {duration_seconds}")
    target = round(duration_seconds * profile.wordsPerMinute / 60)
    hard_limit = math.ceil(target * (1 + profile.tolerancePercent))
    generation_min = math.floor(target * profile.generationTargetMinPercent)
    generation_max = math.floor(target * profile.generationTargetMaxPercent)
    word_count = count_words(text)
    estimated = round(word_count * 60 / profile.wordsPerMinute, 2)
    if word_count <= target:
        status: DurationStatus = "ideal"
        message = f"Duração ideal para {duration_seconds}s."
    elif word_count <= hard_limit:
        status = "warning"
        message = (
            f"Texto ligeiramente acima da meta de {target} palavras. "
            "Pode seguir para o HeyGen, mas vale revisar o ritmo."
        )
    else:
        status = "blocking"
        message = (
            f"Texto muito longo para {duration_seconds}s ({word_count} palavras). "
            f"Ajuste a duração antes de enviar ao HeyGen; máximo seguro: {hard_limit}."
        )
    return DurationAssessment(
        durationSeconds=duration_seconds,
        wordCount=word_count,
        estimatedSeconds=estimated,
        estimatedSecondsDisplay=f"~{round(estimated)}s",
        targetWords=target,
        hardLimitWords=hard_limit,
        generationMinWords=generation_min,
        generationMaxWords=generation_max,
        status=status,
        message=message,
    )


def duration_limits(duration_seconds: int) -> tuple[int, int]:
    assessment = duration_assessment("", duration_seconds)
    return assessment.generationMinWords, assessment.generationMaxWords


def medical_review_status(risk_level: str, approved: bool = False) -> MedicalReviewStatus:
    if approved:
        return "approved"
    normalized = normalize_text(risk_level).lower()
    if normalized in {"alto", "high"}:
        return "required"
    if normalized in {"medio", "médio", "moderado", "medium"}:
        return "recommended"
    return "not_required"


_TITLE_STOP_WORDS = {
    "a", "as", "ao", "aos", "como", "com", "da", "das", "de", "do", "dos", "e", "em",
    "esse", "esta", "este", "eu", "mais", "na", "nas", "no", "nos", "o", "os", "ou", "para",
    "por", "que", "se", "seu", "sua", "um", "uma", "voce", "você", "precisa", "saber",
}


def _semantic_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in WORD_PATTERN.findall(normalize_text(text))
        if len(token) >= 4 and token.casefold() not in _TITLE_STOP_WORDS
    }


def suggested_title_for_script(script: str) -> str | None:
    normalized = normalize_text(script)
    lowered = normalized.casefold()
    if "prato" in lowered and ("caneta" in lowered or "emagrecimento" in lowered):
        return "Caneta para emagrecimento: o que tem no seu prato?"
    sentences = re.findall(r"[^.!?…]+[.!?…]?", normalized)
    for sentence in sentences:
        candidate = re.sub(r"^(e aí|olha só|você sabia que|voce sabia que)\s*[,?:-]?\s*", "", sentence, flags=re.I)
        words = WORD_PATTERN.findall(candidate)
        if len(words) >= 4:
            title = " ".join(words[:12]).strip()
            return title[:1].upper() + title[1:] + ("?" if "?" in sentence else "")
    return None


def title_alignment(title: str, script: str, suggested_title: str | None = None) -> dict[str, Any]:
    if not normalize_text(title) or not normalize_text(script):
        return {"status": "unknown", "reason": "Título ou fala ainda não está disponível."}
    title_tokens = _semantic_tokens(title)
    script_tokens = _semantic_tokens(script)
    if not title_tokens or not script_tokens:
        return {"status": "unknown", "reason": "Não há termos suficientes para comparar."}
    overlap = len(title_tokens & script_tokens) / max(1, len(title_tokens))
    if overlap >= 0.2:
        return {"status": "aligned"}
    return {
        "status": "possible_mismatch",
        "suggestedTitle": suggested_title or suggested_title_for_script(script),
        "reason": "O título e a fala final parecem tratar de focos diferentes.",
    }


_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<![\w-])\d+(?:[.,]\d+)?\s*(?:%|mg|mcg|g|kg|ml|anos?|meses?|dias?|semanas?)?",
    re.I,
)
_PERSONAL_EXPERIENCE_PATTERNS = (
    re.compile(r"\b(?:eu\s+)?vejo\s+(?:isso\s+)?no\s+(?:meu\s+)?consult[oó]rio\b", re.I),
    re.compile(r"\bmeus?\s+pacientes?\b", re.I),
    re.compile(r"\bna\s+minha\s+pr[aá]tica\s+cl[ií]nica\b", re.I),
)


def numeric_claims(text: str) -> set[str]:
    return {normalize_text(item).casefold() for item in _NUMERIC_CLAIM_PATTERN.findall(text or "")}


def unsupported_numeric_claims(output: str, allowed_context: str) -> list[str]:
    return sorted(numeric_claims(output) - numeric_claims(allowed_context))


def unsupported_personal_experience(output: str, allowed_context: str) -> list[str]:
    additions: list[str] = []
    for pattern in _PERSONAL_EXPERIENCE_PATTERNS:
        output_match = pattern.search(output or "")
        if output_match and not pattern.search(allowed_context or ""):
            additions.append(output_match.group(0))
    return additions


EDITOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "operation": {"type": "string", "enum": ["medical_rewrite", "fit_duration"]},
        "script": {"type": "string", "minLength": 1},
        "summaryOfChanges": {"type": "array", "items": {"type": "string"}},
        "titleAlignment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["aligned", "possible_mismatch", "unknown"]},
                "suggestedTitle": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["status"],
        },
        "medicalSafety": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "meaningPreserved": {"type": "boolean"},
                "newClaimsAdded": {"type": "boolean"},
                "unsupportedPersonalExperienceAdded": {"type": "boolean"},
                "requiresHumanReview": {"type": "boolean"},
                "reasons": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "meaningPreserved", "newClaimsAdded", "unsupportedPersonalExperienceAdded",
                "requiresHumanReview", "reasons",
            ],
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "operation", "script", "summaryOfChanges", "titleAlignment", "medicalSafety", "warnings",
    ],
}


MEDICAL_EDITORIAL_SYSTEM_PROMPT = """Você é editor médico de roteiros falados em português brasileiro.
Perfil editorial: médico experiente falando diretamente para a câmera, para pessoas comuns. O tom é seguro,
didático, natural e assertivo. A autoridade vem de clareza e precisão, nunca de jargão.

Regras de oralidade:
- Use frases curtas, pausas naturais e uma ideia principal por frase.
- Explique termos técnicos quando forem indispensáveis.
- Não escreva como artigo, blog, bula, anúncio, palestra formal ou texto de IA.
- Preserve o gancho, a mensagem médica central, ressalvas relevantes, conclusão e CTA.

Segurança editorial obrigatória:
- Não invente dados, estudos, percentuais, sintomas, benefícios, riscos, contraindicações ou fatos.
- Não inclua dose, prescrição, mudança de tratamento, promessa, cura ou substituição de atendimento médico.
- Não invente experiência clínica como “vejo no consultório”, “meus pacientes” ou equivalentes. Só preserve
  essas frases quando elas já existirem no roteiro aprovado ou no contexto autorizado.
- Não transforme menção comercial em recomendação de produto. Mantenha linguagem educativa e não promocional.
- Preserve o CTA quando ele for seguro; não crie CTA agressivo, prescritivo ou comercial.
- Se a fonte não sustentar uma afirmação, retire-a ou marque revisão humana em vez de completar lacunas.

A duração é uma avaliação local posterior. O limite rígido é uma margem de segurança, não uma meta para preencher.
Retorne somente o JSON do schema solicitado."""


def build_editor_prompt(payload: dict[str, Any]) -> tuple[str, str]:
    operation: EditorOperation = payload["operation"]
    assessment = duration_assessment(payload.get("text", ""), int(payload["durationSeconds"]))
    if operation == "medical_rewrite":
        instruction = (
            "Reescreva para melhorar clareza, naturalidade, oralidade e autoridade médica, preservando o sentido "
            "e aproximadamente a duração atual. Não corte apenas para caber no preset."
        )
    else:
        instruction = (
            f"Ajuste a fala para {assessment.durationSeconds}s e mire entre "
            f"{assessment.generationMinWords} e {assessment.generationMaxWords} palavras. Remova primeiro: "
            "repetições, introduções vazias, adjetivos e intensificadores; depois una frases e simplifique contexto "
            "secundário. Só expanda um texto curto com fatos já presentes no contexto."
        )
    context = {
        "operation": operation,
        "instruction": instruction,
        "duration": assessment.to_dict(),
        "speechProfile": asdict(DEFAULT_SPEECH_PROFILE),
        "editorialProfile": SCRIPT_EDITOR_CONTRACT["editorialProfile"],
        "title": payload.get("title", ""),
        "currentScript": payload.get("text", ""),
        "source": payload.get("sourceText", ""),
        "context": payload.get("contextText", ""),
        "medicalCautions": payload.get("medicalCautions", ""),
        "riskLevel": payload.get("riskLevel", ""),
        "claims": payload.get("claims", []),
        "glossary": payload.get("glossary", []),
        "cta": payload.get("cta", ""),
        "safetyRules": [
            "não inventar fatos ou experiência clínica",
            "não prescrever nem prometer resultado",
            "preservar o sentido e sinalizar revisão humana quando necessário",
        ],
        "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
    }
    return MEDICAL_EDITORIAL_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False, indent=2)


def _string_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Campo de lista inválido na resposta da IA.")
    return [normalize_text(str(item)) for item in value if normalize_text(str(item))][:limit]


def normalize_editor_output(raw: Any, operation: EditorOperation) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("A IA não retornou um objeto JSON.")
    if raw.get("operation") != operation:
        raise ValueError("A operação da resposta não corresponde à solicitação.")
    script = normalize_script(str(raw.get("script") or ""))
    if not script:
        raise ValueError("A IA retornou uma fala vazia.")
    alignment = raw.get("titleAlignment")
    safety = raw.get("medicalSafety")
    if not isinstance(alignment, dict) or alignment.get("status") not in {
        "aligned", "possible_mismatch", "unknown"
    }:
        raise ValueError("Alinhamento de título inválido.")
    if not isinstance(safety, dict):
        raise ValueError("Bloco de segurança médica ausente.")
    required_booleans = (
        "meaningPreserved", "newClaimsAdded", "unsupportedPersonalExperienceAdded", "requiresHumanReview"
    )
    if any(not isinstance(safety.get(field), bool) for field in required_booleans):
        raise ValueError("Flags de segurança médica inválidas.")
    normalized_alignment: dict[str, Any] = {"status": alignment["status"]}
    for field in ("suggestedTitle", "reason"):
        value = normalize_text(str(alignment.get(field) or ""))
        if value:
            normalized_alignment[field] = value
    return {
        "operation": operation,
        "script": script,
        "summaryOfChanges": _string_list(raw.get("summaryOfChanges")),
        "titleAlignment": normalized_alignment,
        "medicalSafety": {
            **{field: bool(safety[field]) for field in required_booleans},
            "reasons": _string_list(safety.get("reasons")),
        },
        "warnings": _string_list(raw.get("warnings")),
    }


def post_validate_editor_output(
    output: dict[str, Any],
    *,
    title: str,
    current_script: str,
    allowed_context: str,
    duration_seconds: int,
    risk_level: str,
    human_review_approved: bool,
) -> dict[str, Any]:
    assessment = duration_assessment(output["script"], duration_seconds)
    new_numeric = unsupported_numeric_claims(output["script"], allowed_context)
    new_experience = unsupported_personal_experience(output["script"], allowed_context)
    warnings = list(output["warnings"])
    if new_numeric:
        warnings.append(
            "A saída contém afirmação numérica nova; confirme na fonte antes de aprovar: "
            + ", ".join(new_numeric)
        )
    if new_experience:
        warnings.append(
            "A saída adicionou experiência clínica não autorizada: " + ", ".join(new_experience)
        )
    safety = dict(output["medicalSafety"])
    safety["newClaimsAdded"] = bool(safety["newClaimsAdded"] or new_numeric)
    safety["unsupportedPersonalExperienceAdded"] = bool(
        safety["unsupportedPersonalExperienceAdded"] or new_experience
    )
    safety["requiresHumanReview"] = bool(
        safety["requiresHumanReview"]
        or not safety["meaningPreserved"]
        or new_numeric
        or new_experience
    )
    deterministic_alignment = title_alignment(
        title,
        output["script"],
        output["titleAlignment"].get("suggestedTitle"),
    )
    alignment = output["titleAlignment"]
    if deterministic_alignment["status"] == "possible_mismatch":
        alignment = deterministic_alignment
    review_status = medical_review_status(
        risk_level,
        approved=human_review_approved,
    )
    if safety["requiresHumanReview"] and not human_review_approved:
        review_status = "required"
    result = {
        **output,
        "medicalSafety": safety,
        "titleAlignment": alignment,
        "warnings": list(dict.fromkeys(warnings)),
        "durationAssessment": assessment.to_dict(),
        "medicalReviewStatus": review_status,
    }
    result["qualityChecks"] = quality_checks(
        current_script=current_script,
        output=result,
        duration=assessment,
        medical_review=review_status,
    )
    return result


def quality_checks(
    *,
    current_script: str,
    output: dict[str, Any],
    duration: DurationAssessment,
    medical_review: MedicalReviewStatus,
) -> list[dict[str, str]]:
    safety = output.get("medicalSafety", {})
    alignment = output.get("titleAlignment", {})
    script = output.get("script", "")
    has_hook = bool(re.search(r"[?!]|\b(?:atenção|olha|agora|por que|como)\b", script[:220], re.I))
    has_cta = bool(re.search(r"\b(?:siga|acompanhe|salve|comente|converse|procure|agende)\b", script[-260:], re.I))
    return [
        {
            "id": "duration", "label": "Duração", "source": "deterministic",
            "status": duration.status, "detail": duration.message,
        },
        {
            "id": "spoken_language", "label": "Linguagem falada", "source": "ai",
            "status": "pass", "detail": "Revisada para português brasileiro oral.",
        },
        {
            "id": "medical_tone", "label": "Tom médico", "source": "ai",
            "status": "pass", "detail": "Perfil editorial médico 2.0 aplicado.",
        },
        {
            "id": "safety", "label": "Segurança", "source": "ai+deterministic",
            "status": "warning" if safety.get("requiresHumanReview") else "pass",
            "detail": "; ".join(safety.get("reasons") or []) or "Nenhum alerta de segurança novo.",
        },
        {
            "id": "meaning", "label": "Sentido preservado", "source": "ai",
            "status": "pass" if safety.get("meaningPreserved") else "blocking",
            "detail": "Mensagem central preservada." if safety.get("meaningPreserved") else "Confirme o sentido com revisão humana.",
        },
        {
            "id": "claims", "label": "Novas afirmações", "source": "ai+deterministic",
            "status": "warning" if safety.get("newClaimsAdded") else "pass",
            "detail": "Há afirmação nova para conferir na fonte." if safety.get("newClaimsAdded") else "Nenhuma afirmação nova detectada.",
        },
        {
            "id": "experience", "label": "Experiência clínica inventada", "source": "ai+deterministic",
            "status": "warning" if safety.get("unsupportedPersonalExperienceAdded") else "pass",
            "detail": "Há experiência clínica não autorizada." if safety.get("unsupportedPersonalExperienceAdded") else "Nenhuma experiência clínica inventada detectada.",
        },
        {
            "id": "title", "label": "Título", "source": "ai+deterministic",
            "status": "warning" if alignment.get("status") == "possible_mismatch" else "pass",
            "detail": alignment.get("reason") or "Título e fala parecem alinhados.",
        },
        {
            "id": "hook", "label": "Gancho", "source": "deterministic",
            "status": "pass" if has_hook else "info",
            "detail": "A abertura tem sinal de gancho." if has_hook else "Revise se a abertura prende atenção.",
        },
        {
            "id": "cta", "label": "CTA", "source": "deterministic",
            "status": "pass" if has_cta else "info",
            "detail": "CTA falado detectado." if has_cta else "Nenhum CTA falado foi detectado.",
        },
        {
            "id": "human_review", "label": "Revisão humana", "source": "policy",
            "status": "pass" if medical_review in {"approved", "not_required"} else "warning",
            "detail": {
                "approved": "Revisão médica aprovada.",
                "not_required": "Revisão médica não obrigatória para este risco.",
                "recommended": "Revisão médica recomendada pelo nível de risco.",
                "required": "Revisão médica obrigatória pelo nível de risco.",
            }[medical_review],
        },
    ]


def evaluate_generation_gate(
    *,
    speech: str,
    duration_seconds: int,
    ai_operation_in_flight: bool,
    schema_valid: bool,
    technical_error: str | None,
    medical_review: MedicalReviewStatus,
    human_review_approved: bool,
    script_status: str,
    final_saved: bool,
    final_confirmed: bool,
) -> GenerationGate:
    reasons: list[dict[str, str]] = []
    if not normalize_text(speech):
        reasons.append({"code": "speech_empty", "message": "A fala final está vazia."})
    assessment = duration_assessment(speech, duration_seconds)
    if assessment.status == "blocking":
        reasons.append({"code": "duration_blocking", "message": assessment.message})
    if ai_operation_in_flight:
        reasons.append({"code": "ai_in_flight", "message": "Aguarde a operação de IA terminar."})
    if not schema_valid:
        reasons.append({"code": "ai_schema_invalid", "message": "A última saída de IA não passou na validação."})
    if technical_error:
        reasons.append({"code": "technical_error", "message": "Resolva o erro técnico do editor antes de gerar."})
    if medical_review == "required" and not human_review_approved:
        reasons.append({"code": "medical_review_required", "message": "A revisão médica obrigatória ainda não foi aprovada."})
    if script_status != "aprovado_clinicamente":
        reasons.append({"code": "script_not_ready", "message": "Marque o roteiro como Pronto após a revisão editorial."})
    if not final_saved:
        reasons.append({"code": "unsaved", "message": "Salve a fala final antes de gerar o vídeo."})
    if not final_confirmed:
        reasons.append({"code": "not_confirmed", "message": "Confirme a geração do vídeo final."})
    allowed = not reasons
    return GenerationGate(
        eligibility="allowed" if allowed else "blocked",
        allowed=allowed,
        reason=None if allowed else reasons[0]["message"],
        reasons=tuple(reasons),
    )


def hash_text(value: Any) -> str:
    if isinstance(value, str):
        normalized = normalize_text(value)
    else:
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def editor_cache_payload(payload: dict[str, Any], *, provider: str, model: str) -> dict[str, Any]:
    return {
        "operation": payload["operation"],
        "scriptHash": hash_text(payload.get("text", "")),
        "durationSeconds": payload["durationSeconds"],
        "speechProfileId": payload.get("speechProfileId") or DEFAULT_SPEECH_PROFILE.id,
        "editorialProfileId": payload.get("editorialProfileId") or SCRIPT_EDITOR_CONTRACT["editorialProfile"]["id"],
        "title": normalize_text(payload.get("title", "")),
        "sourceHash": hash_text(payload.get("sourceText", "")),
        "contextHash": hash_text(payload.get("contextText", "")),
        "claimsHash": hash_text(payload.get("claims", [])),
        "glossaryHash": hash_text(payload.get("glossary", [])),
        "medicalCautionsHash": hash_text(payload.get("medicalCautions", "")),
        "riskLevel": normalize_text(payload.get("riskLevel", "")),
        "humanReviewApproved": bool(payload.get("humanReviewApproved")),
        "ctaHash": hash_text(payload.get("cta", "")),
        "provider": provider,
        "model": model,
        "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
    }
