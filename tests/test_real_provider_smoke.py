"""Smokes reais opt-in. A suíte normal sempre pula estes testes pagos."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

import pytest

from api import server


def _enabled(name: str) -> bool:
    return os.getenv(name, "").casefold() == "true"


@pytest.mark.skipif(
    not _enabled("ALLOW_REAL_AI_SMOKE_TESTS"),
    reason="Requer ALLOW_REAL_AI_SMOKE_TESTS=true e orçamento explícito.",
)
def test_real_anthropic_editor_contract_and_cache() -> None:
    max_calls = int(os.getenv("MAX_REAL_AI_CALLS", "0"))
    if not 1 <= max_calls <= 3:
        pytest.fail("MAX_REAL_AI_CALLS deve estar entre 1 e 3.")
    request = server.ScriptEditorAssistIn(
        operation="medical_rewrite",
        text=" ".join(f"conteudo{index}" for index in range(108)),
        title="Roteiro sintético para smoke test",
        sourceText="Conteúdo sintético, sem prontuário ou dado pessoal.",
        contextText="Explique com prudência e linguagem simples.",
        medicalCautions="Não prescrever nem prometer resultado.",
        riskLevel="alto",
        durationSeconds=45,
    )
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with patch.object(
                server,
                "_script_editor_model_call",
                wraps=server._script_editor_model_call,
            ) as model_call:
                first = server.script_editor_assist(request)
                second = server.script_editor_assist(request)
            assert model_call.call_count <= max_calls
        finally:
            server.OPERATIONAL_DB = original_database

    assert first["script"]
    assert first["schemaValid"] is True
    assert second["cacheHit"] is True


@pytest.mark.skipif(
    not _enabled("ALLOW_REAL_HEYGEN_SMOKE_TEST"),
    reason="Requer autorização HeyGen separada e limite de um job.",
)
def test_real_heygen_single_job_is_idempotent() -> None:
    if int(os.getenv("MAX_REAL_HEYGEN_JOBS", "0")) != 1:
        pytest.fail("MAX_REAL_HEYGEN_JOBS deve ser exatamente 1.")
    avatar_id = os.getenv("REAL_HEYGEN_AVATAR_ID", "").strip()
    voice_id = os.getenv("REAL_HEYGEN_VOICE_ID", "").strip()
    if not avatar_id or not voice_id:
        pytest.fail("Defina REAL_HEYGEN_AVATAR_ID e REAL_HEYGEN_VOICE_ID no comando.")
    speech = " ".join(f"conteudo{index}" for index in range(95))
    script = {
        "id": "smoke-heygen-synthetic",
        "titulo": "Smoke sintético",
        "status": "aprovado_clinicamente",
        "risco": "baixo",
        "textoFalado": speech,
    }
    speech_hash = server.hash_text(speech)
    state = {
        "durationSeconds": 45,
        "humanReviewApproved": False,
        "schemaValid": True,
        "technicalError": None,
        "lastResult": None,
        "scriptRevision": 1,
        "finalSpeechHash": speech_hash,
        "contractVersion": server.SCRIPT_EDITOR_CONTRACT_VERSION,
    }
    request = server.VideoCreateIn(
        scriptId=script["id"],
        avatarId=avatar_id,
        voiceId=voice_id,
        durationSeconds=45,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        forceNewVersion=True,
        idempotencyKey=f"real-heygen-smoke-{uuid.uuid4().hex}",
        expectedScriptRevision=1,
        expectedFinalSpeechHash=speech_hash,
        contractVersion=server.SCRIPT_EDITOR_CONTRACT_VERSION,
    )
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        original_jobs = server.VIDEO_JOBS
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        server.VIDEO_JOBS = Path(temporary) / "missing.json"
        try:
            with (
                patch.object(server, "_find_script", return_value=script),
                patch.object(server, "_script_editor_state", return_value=state),
            ):
                first = server.create_video(request)
                second = server.create_video(request)
        finally:
            server.OPERATIONAL_DB = original_database
            server.VIDEO_JOBS = original_jobs

    assert first["job"]["id"] == second["job"]["id"]
    assert second["deduplicated"] is True
