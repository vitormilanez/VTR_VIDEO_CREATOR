from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
from unittest.mock import patch

import pytest

from api import server
from api.services.story_contract import (
    STORY_CONTRACT_VERSION,
    StoryBrief,
    StoryContractError,
    validate_story_plan,
)


SPEECH = (
    "A obesidade é uma condição complexa e merece cuidado individual com avaliação "
    "de um profissional qualificado sempre."
)
SPEECH_HASH = server.hash_text(SPEECH)


def brief() -> StoryBrief:
    return StoryBrief(
        storyType="historical_explainer",
        educationalGoal="Explicar o tema sem alterar a orientação médica aprovada.",
        period="Europa medieval, século XIII",
        location="Feira e botica",
        historicalAccuracy="inspired",
        durationSeconds=20,
        maxHeyGenJobs=2,
        characterId="doctor-main",
        lookId="look-medieval",
        characterDescription="O mesmo médico já aprovado no roteiro.",
        wardrobeDirection="Túnica escura e capa de lã.",
        referenceAssets=[
            {
                "id": "reference-doctor",
                "kind": "image",
                "sha256": "a" * 64,
                "description": "Referência aprovada do personagem.",
            }
        ],
    )


def valid_plan() -> dict:
    return {
        "contractVersion": STORY_CONTRACT_VERSION,
        "storyBible": {
            "premise": "O médico observa uma feira medieval e conecta o passado ao cuidado atual.",
            "educationalGoal": brief().educationalGoal,
            "narrativeArc": {
                "opening": "Chegada à feira",
                "development": "Observação do cotidiano",
                "turn": "Retorno ao olhar atual",
                "ending": "Conclusão cuidadosa",
            },
            "historicalSetting": {
                "period": brief().period,
                "location": brief().location,
                "accuracyMode": brief().historicalAccuracy,
            },
        },
        "characterBible": {
            "characterId": "doctor-main",
            "lookId": "look-medieval",
            "identityRule": "Preservar rosto, idade aparente, cabelo e barba.",
            "voiceRule": "Preservar somente a voz aprovada.",
            "wardrobe": {
                "base": "Túnica escura",
                "accessories": ["capa de lã"],
                "colors": ["marrom", "grafite"],
            },
            "forbiddenChanges": ["Não alterar o rosto"],
        },
        "visualBible": {
            "palette": "Tons terrosos e madeira",
            "lighting": "Luz natural quente",
            "cameraStyle": "Documentário histórico cinematográfico",
            "texture": "Realista e orgânica",
            "forbiddenAnachronisms": ["plástico", "eletricidade"],
        },
        "medicalAssertions": [],
        "shots": [
            {
                "id": "shot-01",
                "order": 1,
                "narrativePurpose": "Apresentar o contexto visual com cuidado.",
                "shotType": "avatar_anchor",
                "providerStrategy": "video_agent",
                "durationSeconds": 10,
                "speech": {
                    "mode": "avatar_speaks",
                    "startWordIndex": 0,
                    "endWordIndex": 8,
                },
                "character": {
                    "required": True,
                    "characterId": "doctor-main",
                    "lookId": "look-medieval",
                },
                "environment": "Entrada de uma feira medieval movimentada",
                "action": "O médico observa as barracas com movimento discreto",
                "camera": {
                    "framing": "plano médio",
                    "movement": "aproximação suave",
                    "lens": "perspectiva natural",
                },
                "lighting": "Manhã quente e suave",
                "continuityKeys": ["market-v1", "wardrobe-v1"],
                "referenceAssetIds": ["reference-doctor"],
                "negativePrompt": ["objetos modernos", "rosto diferente"],
                "audioPolicy": "preserve_base_narration",
                "estimatedCost": {"heygenJobs": 1, "anthropicCalls": 0},
            },
            {
                "id": "shot-02",
                "order": 2,
                "narrativePurpose": "Concluir com um apoio visual discreto.",
                "shotType": "historical_broll",
                "providerStrategy": "video_agent",
                "durationSeconds": 10,
                "speech": {
                    "mode": "voice_continues_from_base_scene",
                    "startWordIndex": 8,
                    "endWordIndex": 17,
                },
                "character": {
                    "required": False,
                    "characterId": None,
                    "lookId": None,
                },
                "environment": "Interior de uma botica com madeira e ervas",
                "action": "Frascos e tecidos aparecem em movimento natural",
                "camera": {
                    "framing": "plano aberto",
                    "movement": "travelling lento",
                    "lens": "perspectiva documental",
                },
                "lighting": "Luz lateral suave",
                "continuityKeys": ["market-v1", "warm-light-v1"],
                "referenceAssetIds": [],
                "negativePrompt": ["plástico", "aparência de desenho"],
                "audioPolicy": "mute_generated_audio",
                "estimatedCost": {"heygenJobs": 1, "anthropicCalls": 0},
            },
        ],
    }


def source_context() -> dict:
    return {
        "script": {"id": "script-story", "status": "aprovado_clinicamente"},
        "editorState": {"humanReviewApproved": True},
        "speech": SPEECH,
        "scriptRevision": 3,
        "finalSpeechHash": SPEECH_HASH,
        "scriptContractVersion": "script-editor-v1",
    }


def provider_context() -> dict:
    return {
        "capabilities": {"capabilitiesVersion": "heygen-test-v1"},
        "providerCapabilitiesVersion": "heygen-test-v1",
        "providerStrategies": ["local_compositor", "video_agent"],
    }


def request_payload() -> server.StoryPlanCreateIn:
    return server.StoryPlanCreateIn(
        brief=brief(),
        expectedScriptRevision=3,
        expectedFinalSpeechHash=SPEECH_HASH,
        scriptContractVersion="script-editor-v1",
        expectedProviderCapabilitiesVersion="heygen-test-v1",
        confirmed=True,
    )


def message() -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=80,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=30,
        )
    )


def test_contract_covers_every_approved_word_without_speech_text() -> None:
    plan = validate_story_plan(
        valid_plan(),
        brief=brief(),
        approved_speech=SPEECH,
        allowed_provider_strategies=["video_agent", "local_compositor"],
    )

    assert plan["shots"][0]["speech"] == {
        "mode": "avatar_speaks",
        "startWordIndex": 0,
        "endWordIndex": 8,
    }
    assert plan["shots"][-1]["speech"]["endWordIndex"] == 17


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda plan: plan["shots"][1]["speech"].update(startWordIndex=9), "SPEECH_COVERAGE_GAP"),
        (lambda plan: plan["shots"][0]["speech"].update(text="Fala inventada"), "STORY_SCHEMA_INVALID"),
        (lambda plan: plan["shots"][0].update(referenceAssetIds=["asset-inventado"]), "ASSET_ID_UNKNOWN"),
        (lambda plan: plan["shots"][0].update(providerStrategy="direct_video"), "PROVIDER_NOT_ALLOWED"),
        (lambda plan: plan["shots"][0].update(narrativePurpose="Prometer melhora de 42%"), "UNAUTHORIZED_NUMERIC_CLAIM"),
        (lambda plan: plan["shots"][0].update(narrativePurpose="Afirmar que a obesidade cura câncer"), "UNAUTHORIZED_MEDICAL_ASSERTION"),
    ],
)
def test_contract_rejects_gaps_invented_speech_claims_and_ids(mutate, code: str) -> None:
    plan = valid_plan()
    mutate(plan)

    with pytest.raises(StoryContractError) as raised:
        validate_story_plan(
            plan,
            brief=brief(),
            approved_speech=SPEECH,
            allowed_provider_strategies=["video_agent", "local_compositor"],
        )

    assert raised.value.code == code


def test_same_story_input_uses_cache_and_preserves_one_version() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_MODEL": "claude-premium-test",
                    },
                    clear=False,
                ),
                patch.object(server, "_story_source_context", return_value=source_context()),
                patch.object(server, "_story_capability_context", return_value=provider_context()),
                patch.object(
                    server,
                    "_story_director_model_call",
                    return_value=(message(), json.dumps(valid_plan(), ensure_ascii=False)),
                ) as model_call,
                patch.object(server, "_run_heygen_json") as heygen,
            ):
                first = server.create_script_story_plan("script-story", request_payload())
                second = server.create_script_story_plan("script-story", request_payload())

            assert model_call.call_count == 1
            assert heygen.call_count == 0
            assert first["version"]["id"] == second["version"]["id"]
            assert first["cacheHit"] is False
            assert second["cacheHit"] is True
            conn = server._ai_db()
            try:
                assert conn.execute("SELECT COUNT(*) FROM story_versions").fetchone()[0] == 1
                assert conn.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 1
            finally:
                conn.close()
        finally:
            server.OPERATIONAL_DB = original_database


def test_simultaneous_story_requests_are_deduplicated() -> None:
    def delayed_call(**_kwargs):
        time.sleep(0.15)
        return message(), json.dumps(valid_plan(), ensure_ascii=False)

    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_MODEL": "claude-premium-test",
                    },
                    clear=False,
                ),
                patch.object(server, "_story_source_context", return_value=source_context()),
                patch.object(server, "_story_capability_context", return_value=provider_context()),
                patch.object(server, "_story_director_model_call", side_effect=delayed_call) as call,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(
                        executor.map(
                            lambda _index: server.create_script_story_plan(
                                "script-story", request_payload()
                            ),
                            range(2),
                        )
                    )

            assert call.call_count == 1
            assert any(result["deduplicated"] for result in results)
            assert results[0]["version"]["id"] == results[1]["version"]["id"]
        finally:
            server.OPERATIONAL_DB = original_database


def test_invalid_repair_preserves_previous_story_version() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_MODEL": "claude-premium-v1",
                    },
                    clear=False,
                ),
                patch.object(server, "_story_source_context", return_value=source_context()),
                patch.object(server, "_story_capability_context", return_value=provider_context()),
                patch.object(
                    server,
                    "_story_director_model_call",
                    return_value=(message(), json.dumps(valid_plan(), ensure_ascii=False)),
                ),
            ):
                first = server.create_script_story_plan("script-story", request_payload())
            previous_version_id = first["version"]["id"]

            invalid = valid_plan()
            invalid["shots"] = []
            with (
                patch.dict(
                    server.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "test-key",
                        "ANTHROPIC_STORY_MODEL": "claude-premium-v2",
                        "ANTHROPIC_STORY_REPAIR_MODEL": "claude-repair-test",
                    },
                    clear=False,
                ),
                patch.object(server, "_story_source_context", return_value=source_context()),
                patch.object(server, "_story_capability_context", return_value=provider_context()),
                patch.object(
                    server,
                    "_story_director_model_call",
                    return_value=(message(), json.dumps(invalid)),
                ) as call,
            ):
                with pytest.raises(server.HTTPException) as raised:
                    server.create_script_story_plan("script-story", request_payload())

            assert raised.value.status_code == 502
            assert call.call_count == 2
            project = server._story_project("script-story")
            assert project is not None
            assert project["activeStoryVersion"] == previous_version_id
            conn = server._ai_db()
            try:
                assert conn.execute("SELECT COUNT(*) FROM story_versions").fetchone()[0] == 1
            finally:
                conn.close()
        finally:
            server.OPERATIONAL_DB = original_database


def test_speech_change_invalidates_active_plan_without_deleting_its_version() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            project = server._save_story_brief("script-story", brief())
            version = server._save_story_version(
                project_id=project["id"],
                plan=valid_plan(),
                source=source_context(),
                provider_capabilities_version="heygen-test-v1",
                request_fingerprint="b" * 64,
                model="claude-premium-test",
            )

            server._invalidate_story_project(
                "script-story",
                script_revision=4,
                final_speech_hash="c" * 64,
                script_contract_version="script-editor-v1",
            )

            stale = server._story_project("script-story")
            assert stale is not None
            assert stale["status"] == "stale"
            assert stale["activeStoryVersion"] is None
            conn = server._ai_db()
            try:
                saved = conn.execute(
                    "SELECT id FROM story_versions WHERE id = ?", (version["id"],)
                ).fetchone()
                assert saved is not None
            finally:
                conn.close()
        finally:
            server.OPERATIONAL_DB = original_database
