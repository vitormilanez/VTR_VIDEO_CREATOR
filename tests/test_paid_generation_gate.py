from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from api import server
from api.job_store import JobStore
from api.services.paid_generation import request_fingerprint, validate_paid_version
from api.services.script_editor import (
    DEFAULT_SPEECH_PROFILE,
    DURATION_PRESETS,
    DURATION_STATUSES,
    GENERATION_ELIGIBILITY_STATUSES,
    GENERATION_GATE_REASON_CODES,
    MEDICAL_REVIEW_STATUSES,
    SCRIPT_EDITOR_CONTRACT,
    SCRIPT_EDITOR_CONTRACT_VERSION,
    TITLE_ALIGNMENT_STATUSES,
    duration_assessment,
    hash_text,
)


def words(count: int) -> str:
    return " ".join(f"palavra{index}" for index in range(count))


def editor_state(speech: str, *, approved: bool = False) -> dict[str, object]:
    speech_hash = hash_text(speech)
    return {
        "durationSeconds": 45,
        "humanReviewApproved": approved,
        "schemaValid": True,
        "technicalError": None,
        "lastResult": None,
        "scriptRevision": 1,
        "finalSpeechHash": speech_hash,
        "approvedScriptRevision": 1 if approved else None,
        "approvedFinalSpeechHash": speech_hash if approved else None,
        "contractVersion": SCRIPT_EDITOR_CONTRACT_VERSION,
    }


def test_contract_json_is_the_typed_source_of_truth() -> None:
    contract = json.loads(
        (Path(__file__).parents[1] / "shared" / "script_editor_contract.json").read_text(
            encoding="utf-8"
        )
    )
    typescript = (
        Path(__file__).parents[1] / "web" / "src" / "lib" / "script-editor.ts"
    ).read_text(encoding="utf-8")

    assert contract == SCRIPT_EDITOR_CONTRACT
    assert tuple(contract["durationPresets"]) == DURATION_PRESETS
    assert tuple(contract["durationStatuses"]) == DURATION_STATUSES
    assert tuple(contract["medicalReviewStatuses"]) == MEDICAL_REVIEW_STATUSES
    assert tuple(contract["titleAlignmentStatuses"]) == TITLE_ALIGNMENT_STATUSES
    assert tuple(contract["generationEligibilityStatuses"]) == GENERATION_ELIGIBILITY_STATUSES
    assert tuple(contract["generationGateReasonCodes"]) == GENERATION_GATE_REASON_CODES
    assert contract["contractVersion"] == SCRIPT_EDITOR_CONTRACT_VERSION
    assert contract["speechProfile"]["wordsPerMinute"] == DEFAULT_SPEECH_PROFILE.wordsPerMinute
    assert "SCRIPT_EDITOR_CONTRACT = contractData" in typescript
    assert "SCRIPT_EDITOR_CONTRACT.contractVersion" in typescript


def test_paid_version_hash_normalizes_equivalent_whitespace_only() -> None:
    canonical = "Uma fala clínica.\n\nCom conclusão segura."
    equivalent = "  Uma   fala clínica. Com conclusão segura.  "
    changed = "Uma fala clínica! Com conclusão segura."

    assert hash_text(canonical) == hash_text(equivalent)
    assert hash_text(canonical) != hash_text(changed)


@pytest.mark.parametrize(
    "changed_speech",
    [
        "Uma fala clínica com uma palavra nova.",
        "Uma fala clínica. Nova conclusão.",
        "Uma fala clínica com 42% de resposta.",
        "Uma fala clínica. Agende sua consulta.",
        "Uma fala clínica!",
    ],
)
def test_saved_speech_change_increments_revision_and_reopens_approval(
    changed_speech: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            original = {
                "id": "s-version",
                "status": "aprovado_clinicamente",
                "textoFalado": "Uma fala clínica.",
            }
            first = server._script_editor_state("s-version", original)
            changed = server._script_editor_state(
                "s-version", {**original, "textoFalado": changed_speech}
            )

            assert first["scriptRevision"] == 1
            assert first["humanReviewApproved"] is True
            assert changed["scriptRevision"] == 2
            assert changed["humanReviewApproved"] is False
            assert changed["approvedFinalSpeechHash"] is None
            assert changed["approvalHistory"][-1]["nextStatus"] == "reopened"
        finally:
            server.OPERATIONAL_DB = original_database


def test_whitespace_only_change_keeps_revision_and_approval() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            original = {
                "id": "s-whitespace",
                "status": "aprovado_clinicamente",
                "textoFalado": "Uma fala clínica. Com orientação segura.",
            }
            first = server._script_editor_state("s-whitespace", original)
            equivalent = server._script_editor_state(
                "s-whitespace",
                {**original, "textoFalado": " Uma  fala clínica.\nCom orientação segura. "},
            )

            assert equivalent["scriptRevision"] == first["scriptRevision"]
            assert equivalent["finalSpeechHash"] == first["finalSpeechHash"]
            assert equivalent["humanReviewApproved"] is True
        finally:
            server.OPERATIONAL_DB = original_database


def test_stale_revision_or_contract_is_rejected_before_reservation() -> None:
    speech = words(100)
    current_hash = hash_text(speech)
    stale = validate_paid_version(
        persisted_speech=speech,
        script_revision=2,
        persisted_speech_hash=current_hash,
        expected_script_revision=1,
        expected_final_speech_hash=current_hash,
        expected_contract_version=SCRIPT_EDITOR_CONTRACT_VERSION,
    )
    incompatible = validate_paid_version(
        persisted_speech=speech,
        script_revision=2,
        persisted_speech_hash=current_hash,
        expected_script_revision=2,
        expected_final_speech_hash=current_hash,
        expected_contract_version="1.0.0",
    )

    assert stale.code == "SCRIPT_VERSION_CONFLICT"
    assert incompatible.code == "CONTRACT_VERSION_CONFLICT"


@pytest.mark.parametrize(
    ("duration_seconds", "word_count", "allowed"),
    [
        (10, 26, True),
        (15, 39, True),
        (30, 78, True),
        (45, 109, True),
        (45, 116, True),
        (45, 117, False),
        (60, 155, True),
    ],
)
def test_final_video_boundaries_reach_provider_only_when_allowed(
    duration_seconds: int,
    word_count: int,
    allowed: bool,
) -> None:
    speech = words(word_count)
    script = {
        "id": "s-boundary",
        "status": "aprovado_clinicamente",
        "risco": "baixo",
        "textoFalado": speech,
    }
    payload = server.VideoCreateIn(
        scriptId="s-boundary",
        avatarId="avatar-1",
        voiceId="voice-1",
        durationSeconds=duration_seconds,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        idempotencyKey=f"boundary-{duration_seconds}-{word_count}",
        expectedScriptRevision=1,
        expectedFinalSpeechHash=hash_text(speech),
        contractVersion=SCRIPT_EDITOR_CONTRACT_VERSION,
    )
    store = MagicMock()
    store.list.return_value = []
    reserved = {"id": "v-boundary", "scriptId": "s-boundary", "productionSettings": {}}
    store.reserve_video.return_value = (reserved, "created")

    with (
        patch.object(server, "_find_script", return_value=script),
        patch.object(server, "_script_editor_state", return_value=editor_state(speech)),
        patch.object(server, "_job_store", return_value=store),
        patch.object(
            server,
            "_create_video_job",
            return_value={"ok": True, "job": reserved},
        ) as provider,
    ):
        if allowed:
            assert server.create_video(payload)["ok"] is True
            provider.assert_called_once()
            store.reserve_video.assert_called_once()
        else:
            with pytest.raises(server.HTTPException) as raised:
                server.create_video(payload)
            assert raised.value.detail["code"] == "DURATION_BLOCKING"
            provider.assert_not_called()
            store.reserve_video.assert_not_called()


def test_frontend_approval_flag_cannot_approve_a_required_review() -> None:
    speech = words(100)
    script = {
        "id": "s-medical-client",
        "status": "aprovado_clinicamente",
        "risco": "alto",
        "textoFalado": speech,
    }
    state = editor_state(speech, approved=False)
    payload = server.VideoCreateIn(
        scriptId=script["id"],
        durationSeconds=45,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        humanReviewApproved=True,
        medicalReviewStatus="approved",
    )
    store = MagicMock()

    with (
        patch.object(server, "_find_script", return_value=script),
        patch.object(server, "_script_editor_state", return_value=state),
        patch.object(server, "_job_store", return_value=store),
    ):
        with pytest.raises(server.HTTPException) as raised:
            server.create_video(payload)

    assert raised.value.detail["code"] == "MEDICAL_REVIEW_REQUIRED"
    store.reserve_video.assert_not_called()


def test_job_store_rejects_same_idempotency_key_with_different_payload() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        store = JobStore(Path(temporary) / "operations.db")
        first = {
            "id": "v-one",
            "status": "fila",
            "requestFingerprint": request_fingerprint({"speech": "A"}),
            "criadoEm": "2026-08-09T00:00:00Z",
            "atualizadoEm": "2026-08-09T00:00:00Z",
        }
        second = {
            **first,
            "id": "v-two",
            "requestFingerprint": request_fingerprint({"speech": "B"}),
        }

        _job, first_state = store.reserve("video", first, idempotency_key="same-key-123")
        existing, second_state = store.reserve(
            "video", second, idempotency_key="same-key-123"
        )

        assert first_state == "created"
        assert second_state == "conflict"
        assert existing["id"] == "v-one"
        assert len(store.list("video")) == 1


def test_simultaneous_same_video_request_calls_provider_once() -> None:
    speech = words(100)
    script = {
        "id": "s-concurrent",
        "status": "aprovado_clinicamente",
        "risco": "baixo",
        "textoFalado": speech,
    }
    payload = server.VideoCreateIn(
        scriptId=script["id"],
        durationSeconds=45,
        narrationText=speech,
        displayText=speech,
        spokenText=speech,
        outroText="",
        idempotencyKey="simultaneous-video-request",
    )

    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        original_jobs = server.VIDEO_JOBS
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        server.VIDEO_JOBS = Path(temporary) / "missing.json"
        calls = 0

        def slow_provider(
            _payload: server.VideoCreateIn,
            job: dict[str, object],
            **_kwargs: object,
        ) -> dict[str, object]:
            nonlocal calls
            calls += 1
            time.sleep(0.08)
            job["submissionState"] = "submitted"
            server._job_store().upsert("video", job)
            return {"ok": True, "job": job}

        try:
            with (
                patch.object(server, "_find_script", return_value=script),
                patch.object(server, "_script_editor_state", return_value=editor_state(speech)),
                patch.object(server, "_create_video_job", side_effect=slow_provider),
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(lambda _index: server.create_video(payload), range(2)))

            assert calls == 1
            assert responses[0]["job"]["id"] == responses[1]["job"]["id"]
            assert len(server._job_store().list("video")) == 1
        finally:
            server.OPERATIONAL_DB = original_database
            server.VIDEO_JOBS = original_jobs
