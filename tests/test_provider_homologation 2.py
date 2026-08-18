from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from api import server
from api.services.script_editor import MEDICAL_EDITORIAL_PROMPT_VERSION, normalize_editor_output


def words(count: int) -> str:
    return " ".join(f"palavra{index}" for index in range(count))


def payload(operation: str = "medical_rewrite", *, text: str | None = None) -> server.ScriptEditorAssistIn:
    return server.ScriptEditorAssistIn(
        operation=operation,
        scriptId="smoke-script",
        text=text or words(108),
        title="Roteiro sintético de homologação",
        sourceText="Fonte sintética sem dados pessoais.",
        contextText="Contexto editorial sintético.",
        medicalCautions="Não prescrever nem prometer resultados.",
        riskLevel="alto",
        claims=[],
        glossary=["GLP-1"],
        cta="Converse com um profissional de saúde.",
        durationSeconds=45,
        humanReviewApproved=False,
    )


def valid_output(operation: str, script: str) -> dict[str, object]:
    return {
        "operation": operation,
        "script": script,
        "summaryOfChanges": ["Ajuste sintético."],
        "titleAlignment": {"status": "aligned"},
        "medicalSafety": {
            "meaningPreserved": True,
            "newClaimsAdded": False,
            "unsupportedPersonalExperienceAdded": False,
            "requiresHumanReview": False,
            "reasons": [],
        },
        "warnings": [],
    }


class ProviderStatusError(RuntimeError):
    def __init__(self, status_code: int, secret: str) -> None:
        super().__init__(secret)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (TimeoutError("SEGREDO_TIMEOUT"), "tempo limite"),
        (ProviderStatusError(429, "SEGREDO_429"), "limite temporário"),
        (ProviderStatusError(500, "SEGREDO_500"), "indisponível"),
        (ConnectionError("SEGREDO_CONEXAO"), "conexão"),
    ],
)
def test_provider_failures_retry_once_and_preserve_previous_text(
    failure: Exception,
    expected_reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = payload()
    fake_anthropic = type(
        "AnthropicModule",
        (),
        {"Anthropic": staticmethod(lambda: object())},
    )()
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "configured-for-mock"}),
        patch.object(server, "_script_editor_model_call", side_effect=[failure, failure]) as call,
        patch.dict("sys.modules", {"anthropic": fake_anthropic}),
    ):
        response = server._run_script_editor_assist(
            request,
            provider="anthropic",
            model="mock-model",
        )

    assert response["ok"] is False
    assert response["schemaValid"] is False
    assert response["script"] == request.text
    assert response["previousScript"] == request.text
    assert response["retryCount"] == 1
    assert expected_reason in response["technicalError"].casefold()
    assert response["medicalReviewStatus"] == "required"
    assert call.call_count == 2
    assert "SEGREDO" not in caplog.text


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"operation": "medical_rewrite"},
        valid_output("medical_rewrite", ""),
    ],
)
def test_malformed_or_empty_output_stops_after_one_repair(invalid: dict[str, object]) -> None:
    request = payload()
    fake_anthropic = type(
        "AnthropicModule",
        (),
        {"Anthropic": staticmethod(lambda: object())},
    )()
    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "configured-for-mock"}),
        patch.object(
            server,
            "_script_editor_model_call",
            side_effect=[(object(), invalid), (object(), invalid)],
        ) as call,
        patch.object(server, "_record_anthropic_usage"),
        patch.dict("sys.modules", {"anthropic": fake_anthropic}),
    ):
        response = server._run_script_editor_assist(
            request,
            provider="anthropic",
            model="mock-model",
        )

    assert response["schemaValid"] is False
    assert response["script"] == request.text
    assert response["retryCount"] == 1
    assert call.call_count == 2


def test_warning_is_accepted_and_blocking_fit_is_rejected_after_one_repair() -> None:
    warning_request = payload(text=words(108))
    blocking_request = payload("fit_duration", text=words(150))
    fake_anthropic = type(
        "AnthropicModule",
        (),
        {"Anthropic": staticmethod(lambda: object())},
    )()
    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "configured-for-mock"}),
        patch.object(server, "_record_anthropic_usage"),
        patch.dict("sys.modules", {"anthropic": fake_anthropic}),
    ):
        with patch.object(
            server,
            "_script_editor_model_call",
            return_value=(object(), valid_output("medical_rewrite", words(109))),
        ):
            warning = server._run_script_editor_assist(
                warning_request,
                provider="anthropic",
                model="mock-model",
            )
        with patch.object(
            server,
            "_script_editor_model_call",
            return_value=(object(), valid_output("fit_duration", words(117))),
        ) as blocking_call:
            blocking = server._run_script_editor_assist(
                blocking_request,
                provider="anthropic",
                model="mock-model",
            )

    assert warning["schemaValid"] is True
    assert warning["durationAssessment"]["status"] == "warning"
    assert blocking["schemaValid"] is False
    assert blocking["script"] == blocking_request.text
    assert blocking["durationAssessment"]["status"] == "blocking"
    assert blocking_call.call_count == 2


@pytest.mark.parametrize(
    "addition",
    ["42%", "5 mg", "em 30 dias", "600 participantes", "3 consultas"],
)
def test_new_numeric_claims_require_human_review_without_calling_them_false(
    addition: str,
) -> None:
    request = payload()
    normalized = normalize_editor_output(
        valid_output("medical_rewrite", f"Informação sintética com {addition}."),
        "medical_rewrite",
    )
    result = server.post_validate_editor_output(
        normalized,
        title=request.title,
        current_script=request.text,
        allowed_context=request.text,
        duration_seconds=request.durationSeconds,
        risk_level=request.riskLevel,
        human_review_approved=False,
    )

    assert result["medicalSafety"]["newClaimsAdded"] is True
    assert result["medicalSafety"]["requiresHumanReview"] is True
    assert result["medicalReviewStatus"] == "required"
    assert any("confirme na fonte" in warning for warning in result["warnings"])
    assert all("falso" not in warning.casefold() for warning in result["warnings"])


def test_invented_clinical_experience_requires_human_review() -> None:
    request = payload()
    normalized = normalize_editor_output(
        valid_output(
            "medical_rewrite",
            "Na minha prática clínica, meus pacientes sempre respondem bem.",
        ),
        "medical_rewrite",
    )
    result = server.post_validate_editor_output(
        normalized,
        title=request.title,
        current_script=request.text,
        allowed_context=request.text,
        duration_seconds=request.durationSeconds,
        risk_level="baixo",
        human_review_approved=False,
    )

    assert result["medicalSafety"]["unsupportedPersonalExperienceAdded"] is True
    assert result["medicalSafety"]["requiresHumanReview"] is True
    assert result["medicalReviewStatus"] == "required"


def test_repeated_request_hits_cache_without_a_second_provider_call() -> None:
    request = payload()
    response = {
        "ok": True,
        "operation": request.operation,
        "script": request.text,
        "summaryOfChanges": [],
        "titleAlignment": {"status": "aligned"},
        "medicalSafety": {
            "meaningPreserved": True,
            "newClaimsAdded": False,
            "unsupportedPersonalExperienceAdded": False,
            "requiresHumanReview": True,
            "reasons": [],
        },
        "warnings": [],
        "durationAssessment": server.duration_assessment(request.text, 45).to_dict(),
        "medicalReviewStatus": "required",
        "qualityChecks": [],
        "generationGate": {"allowed": False, "status": "blocked", "reasons": []},
        "provider": "anthropic",
        "model": "mock-model",
        "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
        "cacheHit": False,
        "retryCount": 0,
        "schemaValid": True,
        "previousScript": request.text,
    }
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with patch.object(server, "_run_script_editor_assist", return_value=response) as call:
                first = server.script_editor_assist(request)
                second = server.script_editor_assist(request)
        finally:
            server.OPERATIONAL_DB = original_database

    assert first["cacheHit"] is False
    assert second["cacheHit"] is True
    assert call.call_count == 1


def test_logs_never_include_full_script_source_or_secret(caplog: pytest.LogCaptureFixture) -> None:
    secret_script = "SEGREDO-DA-FALA " + words(97)
    request = payload("fit_duration", text=secret_script)
    request.sourceText = "DOCUMENTO-INTEGRAL-SECRETO"
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = server.script_editor_assist(request)

    assert response["noOp"] is True
    assert "SEGREDO-DA-FALA" not in caplog.text
    assert "DOCUMENTO-INTEGRAL-SECRETO" not in caplog.text
    assert "ANTHROPIC_API_KEY" not in caplog.text
    assert "input_words=" in caplog.text


def test_failure_after_reservation_returns_and_persists_failed_safe_job() -> None:
    speech = words(100)
    script = {
        "id": "s-provider-failure",
        "status": "aprovado_clinicamente",
        "risco": "baixo",
        "textoFalado": speech,
    }
    request = server.VideoCreateIn(
        scriptId=script["id"],
        durationSeconds=45,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        idempotencyKey="provider-failure-after-reservation",
    )
    state = {
        "durationSeconds": 45,
        "humanReviewApproved": False,
        "schemaValid": True,
        "technicalError": None,
        "lastResult": None,
        "scriptRevision": 1,
        "finalSpeechHash": server.hash_text(speech),
        "contractVersion": server.SCRIPT_EDITOR_CONTRACT_VERSION,
    }
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        original_jobs = server.VIDEO_JOBS
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        server.VIDEO_JOBS = Path(temporary) / "missing.json"
        try:
            with (
                patch.object(server, "_find_script", return_value=script),
                patch.object(server, "_script_editor_state", return_value=state),
                patch.object(
                    server,
                    "_create_video_job",
                    side_effect=ConnectionError("SEGREDO-DA-FALA"),
                ),
            ):
                result = server.create_video(request)
            saved = server._job_store().list("video")
        finally:
            server.OPERATIONAL_DB = original_database
            server.VIDEO_JOBS = original_jobs

    assert result["ok"] is False
    assert result["submissionFailed"] is True
    assert len(saved) == 1
    assert result["job"]["id"] == saved[0]["id"]
    assert saved[0]["status"] == "erro"
    assert saved[0]["submissionState"] == "failed_safe"
    assert saved[0]["retrySafe"] is True
    assert "SEGREDO" not in saved[0]["erro"]
    assert "SEGREDO" not in result["warning"]


def test_reconciliation_distinguishes_safe_reservation_from_uncertain_submission() -> None:
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        original_jobs = server.VIDEO_JOBS
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        server.VIDEO_JOBS = Path(temporary) / "missing.json"
        try:
            store = server._job_store()
            for job_id, state in (("v-reserved", "reserved"), ("v-submitting", "submitting")):
                store.upsert(
                    "video",
                    {
                        "id": job_id,
                        "scriptId": "smoke-script",
                        "status": "fila",
                        "submissionState": state,
                        "criadoEm": stale.isoformat(),
                        "atualizadoEm": stale.isoformat(),
                    },
                )
            result = server._reconcile_incomplete_video_jobs(
                now=datetime.now(timezone.utc),
                stale_after_seconds=60,
            )
            jobs = {job["id"]: job for job in server._job_store().list("video")}
        finally:
            server.OPERATIONAL_DB = original_database
            server.VIDEO_JOBS = original_jobs

    assert result == {"failedSafe": 1, "submissionUncertain": 1}
    assert jobs["v-reserved"]["submissionState"] == "failed_safe"
    assert jobs["v-reserved"]["retrySafe"] is True
    assert jobs["v-submitting"]["submissionState"] == "submission_uncertain"
    assert jobs["v-submitting"]["retrySafe"] is False
