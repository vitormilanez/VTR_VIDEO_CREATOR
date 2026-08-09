"""Contrato comum para qualquer entrada que possa criar custo de vídeo.

Este módulo não faz I/O nem chama provedores. Ele valida a versão canônica da
fala e produz fingerprints estáveis para que a camada de persistência possa
reservar um job com segurança antes da chamada externa.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from api.services.script_editor import SCRIPT_EDITOR_CONTRACT_VERSION, hash_text


@dataclass(frozen=True)
class PaidVersionCheck:
    allowed: bool
    code: str | None
    message: str | None
    script_revision: int
    final_speech_hash: str
    contract_version: str


def validate_paid_version(
    *,
    persisted_speech: str,
    script_revision: int,
    persisted_speech_hash: str | None,
    expected_script_revision: int | None,
    expected_final_speech_hash: str | None,
    expected_contract_version: str | None,
) -> PaidVersionCheck:
    """Valida o snapshot do cliente contra a fala recalculada pelo backend.

    Campos esperados ausentes são derivados do estado autoritativo para manter
    clientes legados seguros. Quando presentes, qualquer divergência é
    fail-closed e deve impedir a reserva do job.
    """

    canonical_hash = hash_text(persisted_speech)
    if not persisted_speech.strip():
        return PaidVersionCheck(
            False,
            "SPEECH_EMPTY",
            "A fala final persistida está vazia.",
            script_revision,
            canonical_hash,
            SCRIPT_EDITOR_CONTRACT_VERSION,
        )
    if persisted_speech_hash != canonical_hash:
        return PaidVersionCheck(
            False,
            "SCRIPT_STATE_INCOMPLETE",
            "O estado versionado da fala está incompleto. Recarregue o roteiro.",
            script_revision,
            canonical_hash,
            SCRIPT_EDITOR_CONTRACT_VERSION,
        )
    contract_version = expected_contract_version or SCRIPT_EDITOR_CONTRACT_VERSION
    if contract_version != SCRIPT_EDITOR_CONTRACT_VERSION:
        return PaidVersionCheck(
            False,
            "CONTRACT_VERSION_CONFLICT",
            "O editor foi atualizado. Recarregue a página antes de gerar.",
            script_revision,
            canonical_hash,
            SCRIPT_EDITOR_CONTRACT_VERSION,
        )
    expected_revision = (
        script_revision if expected_script_revision is None else expected_script_revision
    )
    expected_hash = expected_final_speech_hash or canonical_hash
    if expected_revision != script_revision or expected_hash != canonical_hash:
        return PaidVersionCheck(
            False,
            "SCRIPT_VERSION_CONFLICT",
            "A fala foi alterada depois desta tela ser carregada. Recarregue o roteiro.",
            script_revision,
            canonical_hash,
            SCRIPT_EDITOR_CONTRACT_VERSION,
        )
    return PaidVersionCheck(
        True,
        None,
        None,
        script_revision,
        canonical_hash,
        SCRIPT_EDITOR_CONTRACT_VERSION,
    )


def request_fingerprint(payload: dict[str, Any]) -> str:
    """Hash persistente para diferenciar retries de reuso indevido da key."""

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
