from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from api import server
from api.services.script_editor import (
    DEFAULT_SPEECH_PROFILE,
    MEDICAL_EDITORIAL_PROMPT_VERSION,
    build_editor_prompt,
    count_words,
    duration_assessment,
    editor_cache_payload,
    evaluate_generation_gate,
    medical_review_status,
    normalize_editor_output,
    post_validate_editor_output,
    title_alignment,
)


def words(amount: int) -> str:
    return " ".join(f"palavra{index}" for index in range(amount))


@pytest.mark.parametrize(
    ("duration", "target", "hard_limit", "generation_min", "generation_max"),
    [
        (10, 24, 26, 21, 22),
        (15, 36, 39, 31, 33),
        (30, 72, 78, 63, 67),
        (45, 108, 116, 95, 101),
        (60, 144, 155, 126, 135),
    ],
)
def test_duration_matrix(
    duration: int,
    target: int,
    hard_limit: int,
    generation_min: int,
    generation_max: int,
) -> None:
    assessment = duration_assessment(words(target), duration)

    assert assessment.targetWords == target
    assert assessment.hardLimitWords == hard_limit
    assert assessment.generationMinWords == generation_min
    assert assessment.generationMaxWords == generation_max
    assert assessment.status == "ideal"
    assert duration_assessment(words(target + 1), duration).status == "warning"
    assert duration_assessment(words(hard_limit), duration).status == "warning"
    assert duration_assessment(words(hard_limit + 1), duration).status == "blocking"


@pytest.mark.parametrize(
    ("word_count", "status"),
    [(108, "ideal"), (109, "warning"), (116, "warning"), (117, "blocking")],
)
def test_mandatory_45_second_boundaries(word_count: int, status: str) -> None:
    assert duration_assessment(words(word_count), 45).status == status


def test_portuguese_word_count_normalizes_punctuation_accents_and_glp1() -> None:
    text = "  Saúde,\nGLP-1 e médico-paciente; d'água...  "

    assert count_words(text) == 5
    assessment = duration_assessment(text, 10)
    assert assessment.wordCount == 5
    assert assessment.estimatedSeconds == round(5 * 60 / DEFAULT_SPEECH_PROFILE.wordsPerMinute, 2)


def test_duration_and_medical_review_are_independent() -> None:
    duration = duration_assessment(words(108), 45)

    assert duration.status == "ideal"
    assert medical_review_status("alto") == "required"
    assert medical_review_status("alto", approved=True) == "approved"


def test_title_mismatch_suggests_the_current_spoken_topic() -> None:
    result = title_alignment(
        "Efeitos colaterais graves do Mounjaro: o que você precisa saber",
        "E aí, o que tem no seu prato? Você está usando as chamadas canetas para emagrecimento.",
    )

    assert result["status"] == "possible_mismatch"
    assert result["suggestedTitle"] == "Caneta para emagrecimento: o que tem no seu prato?"


def test_generation_gate_allows_warning_but_blocks_hard_limit() -> None:
    common = {
        "ai_operation_in_flight": False,
        "schema_valid": True,
        "technical_error": None,
        "medical_review": "recommended",
        "human_review_approved": False,
        "script_status": "aprovado_clinicamente",
        "final_saved": True,
        "final_confirmed": True,
    }

    warning = evaluate_generation_gate(speech=words(109), duration_seconds=45, **common)
    blocking = evaluate_generation_gate(speech=words(117), duration_seconds=45, **common)

    assert warning.allowed is True
    assert blocking.allowed is False
    assert blocking.reasons[0]["code"] == "duration_blocking"


def editor_payload(operation: str = "medical_rewrite", *, text: str | None = None) -> dict:
    return {
        "operation": operation,
        "text": text or words(108),
        "title": "Efeitos colaterais graves do Mounjaro",
        "sourceText": "A fonte aprovada informa apenas contexto educativo.",
        "contextText": "Canetas para emagrecimento e alimentação precisam de avaliação individual.",
        "medicalCautions": "Não prescrever ou prometer resultados.",
        "riskLevel": "alto",
        "claims": ["Nenhum dado numérico aprovado."],
        "glossary": ["GLP-1"],
        "cta": "Converse com seu médico.",
        "durationSeconds": 45,
        "humanReviewApproved": False,
    }


def valid_ai_output(operation: str, script: str) -> dict:
    return {
        "operation": operation,
        "script": script,
        "summaryOfChanges": ["Frases encurtadas e redundâncias removidas."],
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


def validated_response(payload: server.ScriptEditorAssistIn, script: str | None = None) -> dict:
    normalized = normalize_editor_output(
        valid_ai_output(payload.operation, script or payload.text),
        payload.operation,
    )
    validated = post_validate_editor_output(
        normalized,
        title=payload.title,
        current_script=payload.text,
        allowed_context="\n".join([payload.text, payload.sourceText, payload.contextText]),
        duration_seconds=payload.durationSeconds,
        risk_level=payload.riskLevel,
        human_review_approved=payload.humanReviewApproved,
    )
    return {
        "ok": True,
        **validated,
        "provider": "anthropic",
        "model": "mock-model",
        "promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION,
        "cacheHit": False,
        "retryCount": 0,
        "schemaValid": True,
        "previousScript": payload.text,
    }


def test_prompts_keep_medical_rewrite_and_fit_duration_separate() -> None:
    rewrite_system, rewrite_user = build_editor_prompt(editor_payload("medical_rewrite"))
    fit_system, fit_user = build_editor_prompt(editor_payload("fit_duration"))

    assert "aproximadamente a duração atual" in rewrite_user
    assert "Não corte apenas" in rewrite_user
    assert "mire entre 95 e 101 palavras" in fit_user
    assert "introduções vazias" in fit_user
    assert "vejo no consultório" in rewrite_system
    assert "Não invente dados" in rewrite_system
    assert '"source"' in fit_user
    assert '"context"' in fit_user
    assert MEDICAL_EDITORIAL_PROMPT_VERSION in fit_user


def test_structured_output_requires_operation_schema_and_nonempty_script() -> None:
    with pytest.raises(ValueError):
        normalize_editor_output({"operation": "medical_rewrite"}, "medical_rewrite")
    with pytest.raises(ValueError):
        normalize_editor_output(valid_ai_output("fit_duration", words(100)), "medical_rewrite")


def test_post_validation_warns_about_new_numbers_and_invented_experience() -> None:
    output = normalize_editor_output(
        valid_ai_output(
            "medical_rewrite",
            "Vejo no meu consultório que 42% das pessoas melhoram. Converse com seu médico.",
        ),
        "medical_rewrite",
    )
    result = post_validate_editor_output(
        output,
        title="Efeitos colaterais graves do Mounjaro",
        current_script="Canetas para emagrecimento exigem cuidado.",
        allowed_context="Canetas para emagrecimento exigem cuidado.",
        duration_seconds=45,
        risk_level="medio",
        human_review_approved=False,
    )

    assert result["medicalSafety"]["newClaimsAdded"] is True
    assert result["medicalSafety"]["unsupportedPersonalExperienceAdded"] is True
    assert result["medicalSafety"]["requiresHumanReview"] is True
    assert result["medicalReviewStatus"] == "required"
    assert result["titleAlignment"]["status"] == "possible_mismatch"
    assert any("afirmação numérica nova" in warning for warning in result["warnings"])


def test_fit_duration_no_op_makes_no_ai_call() -> None:
    payload = server.ScriptEditorAssistIn(**editor_payload("fit_duration", text=words(98)))
    with patch.object(server, "_run_script_editor_assist") as ai_call:
        response = server.script_editor_assist(payload)

    assert response["noOp"] is True
    assert response["provider"] == "local"
    assert "já está adequado" in response["message"]
    ai_call.assert_not_called()


def test_fit_duration_uses_at_most_one_correction() -> None:
    payload = server.ScriptEditorAssistIn(**editor_payload("fit_duration", text=words(150)))
    first = valid_ai_output("fit_duration", words(117))
    second = valid_ai_output("fit_duration", words(100))
    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}),
        patch.object(server, "_script_editor_model_call", side_effect=[(object(), first), (object(), second)]) as call,
        patch.object(server, "_record_anthropic_usage"),
        patch.dict("sys.modules", {"anthropic": type("AnthropicModule", (), {"Anthropic": staticmethod(lambda: object())})()}),
    ):
        response = server._run_script_editor_assist(
            payload,
            provider="anthropic",
            model="mock-model",
        )

    assert response["schemaValid"] is True
    assert response["retryCount"] == 1
    assert response["durationAssessment"]["status"] == "ideal"
    assert call.call_count == 2


def test_invalid_schema_twice_keeps_previous_text_and_stops() -> None:
    payload = server.ScriptEditorAssistIn(**editor_payload("medical_rewrite"))
    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}),
        patch.object(server, "_script_editor_model_call", side_effect=[(object(), {}), (object(), {})]) as call,
        patch.object(server, "_record_anthropic_usage"),
        patch.dict("sys.modules", {"anthropic": type("AnthropicModule", (), {"Anthropic": staticmethod(lambda: object())})()}),
    ):
        response = server._run_script_editor_assist(
            payload,
            provider="anthropic",
            model="mock-model",
        )

    assert response["schemaValid"] is False
    assert response["script"] == payload.text
    assert response["retryCount"] == 1
    assert call.call_count == 2


def test_editor_cache_key_changes_for_relevant_context() -> None:
    base = editor_payload()
    first = editor_cache_payload(base, provider="anthropic", model="mock")
    changed_title = editor_cache_payload({**base, "title": "Outro título"}, provider="anthropic", model="mock")
    changed_context = editor_cache_payload({**base, "contextText": "Outro contexto"}, provider="anthropic", model="mock")

    assert first != changed_title
    assert first != changed_context
    assert first["promptVersion"] == MEDICAL_EDITORIAL_PROMPT_VERSION
    assert "sourceHash" in first and "contextHash" in first and "glossaryHash" in first


def test_identical_inflight_editor_requests_are_deduplicated() -> None:
    payload = server.ScriptEditorAssistIn(**editor_payload("medical_rewrite"))
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            response = validated_response(payload)

            def slow_response(*_args: object, **_kwargs: object) -> dict:
                time.sleep(0.08)
                return response

            with patch.object(server, "_run_script_editor_assist", side_effect=slow_response) as ai_call:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _: server.script_editor_assist(payload), range(2)))

            assert ai_call.call_count == 1
            assert any(result.get("deduplicated") for result in results)
        finally:
            server.OPERATIONAL_DB = original_database


def test_backend_narration_validation_allows_warning_and_blocks_hard_limit() -> None:
    warning = server._validate_final_narration(
        {"id": "s-warning", "status": "aprovado_clinicamente"},
        words(109),
        45,
        "",
    )
    assert count_words(warning) == 109

    with pytest.raises(server.HTTPException) as raised:
        server._validate_final_narration(
            {"id": "s-blocking", "status": "aprovado_clinicamente"},
            words(117),
            45,
            "",
        )
    assert raised.value.status_code == 422
    assert "máximo seguro: 116" in raised.value.detail


def test_editor_state_persists_duration_review_history_and_safe_defaults() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            legacy = server._script_editor_state(
                "s-legacy",
                {"id": "s-legacy", "status": "aprovado_clinicamente"},
            )
            assert legacy["durationSeconds"] == 45
            assert legacy["humanReviewApproved"] is True
            assert legacy["legacyFallback"] is True

            saved = server._save_script_editor_state(
                {
                    "scriptId": "s-legacy",
                    "durationSeconds": 60,
                    "humanReviewApproved": False,
                    "titleChoice": "suggested",
                    "suggestedTitle": "Título sugerido",
                    "schemaValid": True,
                    "technicalError": None,
                    "previousScript": "Versão anterior",
                    "lastResult": {"promptVersion": MEDICAL_EDITORIAL_PROMPT_VERSION},
                }
            )
            loaded = server._script_editor_state("s-legacy")

            assert saved["durationSeconds"] == 60
            assert loaded["humanReviewApproved"] is False
            assert loaded["titleChoice"] == "suggested"
            assert loaded["previousScript"] == "Versão anterior"
            assert loaded["lastResult"]["promptVersion"] == MEDICAL_EDITORIAL_PROMPT_VERSION
            assert loaded["legacyFallback"] is False
        finally:
            server.OPERATIONAL_DB = original_database


def test_required_medical_review_blocks_ideal_duration_without_title_side_effects() -> None:
    gate = evaluate_generation_gate(
        speech=words(108),
        duration_seconds=45,
        ai_operation_in_flight=False,
        schema_valid=True,
        technical_error=None,
        medical_review="required",
        human_review_approved=False,
        script_status="aprovado_clinicamente",
        final_saved=True,
        final_confirmed=True,
    )

    assert gate.allowed is False
    assert gate.reasons[0]["code"] == "medical_review_required"
    assert all(reason["code"] != "duration_blocking" for reason in gate.reasons)


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"speech": ""}, "speech_empty"),
        ({"ai_operation_in_flight": True}, "ai_in_flight"),
        ({"schema_valid": False}, "ai_schema_invalid"),
        ({"technical_error": "Falha de rede"}, "technical_error"),
        ({"script_status": "em_revisao"}, "script_not_ready"),
        ({"final_saved": False}, "unsaved"),
        ({"final_confirmed": False}, "not_confirmed"),
    ],
)
def test_generation_gate_reports_each_independent_blocker(
    override: dict[str, object],
    expected_code: str,
) -> None:
    common: dict[str, object] = {
        "speech": words(108),
        "duration_seconds": 45,
        "ai_operation_in_flight": False,
        "schema_valid": True,
        "technical_error": None,
        "medical_review": "recommended",
        "human_review_approved": False,
        "script_status": "aprovado_clinicamente",
        "final_saved": True,
        "final_confirmed": True,
    }

    gate = evaluate_generation_gate(**{**common, **override})

    assert gate.allowed is False
    assert gate.reasons[0]["code"] == expected_code


def test_persisted_ai_medical_alert_cannot_be_downgraded_by_request() -> None:
    script = {"id": "s-medical", "risco": "baixo", "status": "aprovado_clinicamente"}
    state = {
        "humanReviewApproved": False,
        "lastResult": {
            "medicalReviewStatus": "required",
            "medicalSafety": {"requiresHumanReview": True},
        },
    }

    assert server._resolved_medical_review_status(script, state, "recommended") == "required"
    assert (
        server._resolved_medical_review_status(
            script,
            {**state, "humanReviewApproved": True},
            "required",
        )
        == "approved"
    )


@pytest.mark.parametrize(("word_count", "allowed"), [(109, True), (117, False)])
def test_video_endpoint_uses_central_duration_gate_before_provider(
    word_count: int,
    allowed: bool,
) -> None:
    speech = words(word_count)
    script = {
        "id": "s-video-gate",
        "status": "aprovado_clinicamente",
        "risco": "baixo",
        "textoFalado": speech,
    }
    state = {
        "humanReviewApproved": False,
        "schemaValid": True,
        "technicalError": None,
        "lastResult": None,
    }
    payload = server.VideoCreateIn(
        scriptId=script["id"],
        avatarId="avatar-1",
        voiceId="voice-1",
        durationSeconds=45,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        finalConfirmed=True,
    )
    store = MagicMock()
    reserved = {"id": "v-gate", "scriptId": script["id"], "productionSettings": {}}
    store.reserve_video.return_value = (reserved, "created")

    with (
        patch.object(server, "_find_script", return_value=script),
        patch.object(server, "_script_editor_state", return_value=state),
        patch.object(server, "_job_store", return_value=store),
        patch.object(
            server,
            "_create_video_job",
            return_value={"ok": True, "job": reserved},
        ) as provider,
    ):
        if allowed:
            response = server.create_video(payload)
            assert response["ok"] is True
            provider.assert_called_once()
            store.reserve_video.assert_called_once()
        else:
            with pytest.raises(server.HTTPException) as raised:
                server.create_video(payload)
            assert raised.value.status_code == 422
            provider.assert_not_called()
            store.reserve_video.assert_not_called()
