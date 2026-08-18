from pathlib import Path
import tempfile
from unittest.mock import patch

from api import server


def _prescriptive_speech() -> str:
    words = ["Comece", "hoje", "uma", "rotina", "mais", "ativa"]
    words.extend(f"contexto{index}" for index in range(59))
    return " ".join(words) + "."


def _payload() -> server.VideoCreateIn:
    speech = _prescriptive_speech()
    return server.VideoCreateIn(
        scriptId="s-cinematic-warning",
        avatarId="avatar-gui",
        voiceId="voice-gui",
        orientation="portrait",
        durationSeconds=30,
        generationMode="cinematic",
        narrationText=speech,
        displayText=speech,
        cinematicPrompt="Use the selected presenter with contextually relevant support visuals.",
        outroText="",
        finalConfirmed=True,
    )


def _authorization() -> dict:
    speech = _prescriptive_speech()
    return {
        "script": {
            "id": "s-cinematic-warning",
            "status": "aprovado_clinicamente",
            "textoFalado": speech,
        },
        "speech": speech,
        "scriptRevision": 1,
        "finalSpeechHash": server.hash_text(speech),
        "contractVersion": server.SCRIPT_EDITOR_CONTRACT_VERSION,
        "medicalReviewStatus": "approved",
    }


def _temporary_job_store():
    temporary = tempfile.TemporaryDirectory()
    original_database = server.OPERATIONAL_DB
    original_jobs = server.VIDEO_JOBS
    server.OPERATIONAL_DB = Path(temporary.name) / "operations.db"
    server.VIDEO_JOBS = Path(temporary.name) / "missing-video-jobs.json"
    return temporary, original_database, original_jobs


def _restore_job_store(temporary, original_database, original_jobs) -> None:
    server.OPERATIONAL_DB = original_database
    server.VIDEO_JOBS = original_jobs
    temporary.cleanup()


def test_confirmed_cinematic_turns_prescriptive_compliance_into_job_warning() -> None:
    temporary, original_database, original_jobs = _temporary_job_store()

    def successful_submission(_payload, job, **_kwargs):
        job["submissionState"] = "submitted"
        job["remoteSessionId"] = "session-warning"
        server._job_store().upsert("video", job)
        return {"ok": True, "job": job}

    try:
        with (
            patch.object(server, "_find_script", return_value=_authorization()["script"]),
            patch.object(server, "_authorize_paid_generation", return_value=_authorization()),
            patch.object(
                server,
                "_heygen_capabilities",
                return_value={"capabilitiesVersion": "mock-v1", "checkedAt": "now"},
            ),
            patch.object(server, "validate_video_agent_options"),
            patch.object(server, "_create_video_job", side_effect=successful_submission),
        ):
            result = server.create_video(_payload())

        assert result["ok"] is True
        assert result["job"]["id"].startswith("v-")
        assert "Possível linguagem prescritiva" in result["job"]["warnings"]
        assert result["job"]["productionSettings"]["complianceWarnings"] == result["job"]["warnings"]
    finally:
        _restore_job_store(temporary, original_database, original_jobs)


def test_provider_failure_returns_and_persists_reserved_local_job_id() -> None:
    temporary, original_database, original_jobs = _temporary_job_store()
    try:
        with (
            patch.object(server, "_find_script", return_value=_authorization()["script"]),
            patch.object(server, "_authorize_paid_generation", return_value=_authorization()),
            patch.object(
                server,
                "_heygen_capabilities",
                return_value={"capabilitiesVersion": "mock-v1", "checkedAt": "now"},
            ),
            patch.object(server, "validate_video_agent_options"),
            patch.object(server, "_create_video_job", side_effect=RuntimeError("provider down")),
        ):
            result = server.create_video(_payload())

        assert result["ok"] is False
        assert result["submissionFailed"] is True
        assert result["job"]["id"].startswith("v-")
        assert result["job"]["status"] == "erro"
        stored = server._job_store().get("video", result["job"]["id"])
        assert stored is not None
        assert stored["id"] == result["job"]["id"]
        assert stored["status"] == "erro"
    finally:
        _restore_job_store(temporary, original_database, original_jobs)

