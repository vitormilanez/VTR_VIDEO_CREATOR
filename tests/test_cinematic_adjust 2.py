import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import server


def _candidate(*, word_count: int, duration: int = 30) -> dict:
    return {
        "speech": " ".join(f"conteudo{index}" for index in range(word_count)),
        "durationSeconds": duration,
        "supportingImages": "auto",
        "presenterMode": "intro_outro",
        "mediaTypes": ["motion_graphics", "stock_media"],
        "visualStyle": "documentary",
        "requiredElements": "Show contextual daily routines and the selected presenter.",
        "excludedElements": "Avoid unrelated gym stereotypes and misleading imagery.",
        "criticalOnScreenText": "Energia não é só força de vontade",
        "directionNotes": "Use natural light, restrained pacing, and clean transitions.",
        "rationale": "A ideia foi transformada em uma fala coerente e adequada à duração.",
    }


def _message(candidate: dict) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(candidate, ensure_ascii=False))])


def _payload() -> server.CinematicAdjustIn:
    return server.CinematicAdjustIn(
        sourceText="Uma ideia sobre conforto excessivo, energia e saúde masculina.",
        durationSeconds=45,
        supportingImages="auto",
        presenterMode="anchor",
        mediaTypes=["motion_graphics", "stock_media"],
        visualStyle="editorial",
        requiredElements="Rotina real e o apresentador.",
        excludedElements="Cenas fora do tema.",
        criticalOnScreenText="",
        directionNotes="Ritmo provocativo sem sensacionalismo.",
        avatarName="Gui principal",
        avatarType="digital_twin",
        avatarOrientation="portrait",
    )


_UNSUPPORTED_ANTHROPIC_SCHEMA_CONSTRAINTS = {
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
}


def _assert_anthropic_schema_compatibility(value: object) -> None:
    if isinstance(value, dict):
        assert not (_UNSUPPORTED_ANTHROPIC_SCHEMA_CONSTRAINTS & value.keys())
        for child in value.values():
            _assert_anthropic_schema_compatibility(child)
    elif isinstance(value, list):
        for child in value:
            _assert_anthropic_schema_compatibility(child)


def test_cinematic_adjust_uses_anthropic_compatible_schema_mock(monkeypatch) -> None:
    client = MagicMock()

    def strict_anthropic_create(**kwargs):
        schema = kwargs["output_config"]["format"]["schema"]
        _assert_anthropic_schema_compatibility(schema)
        return _message(_candidate(word_count=65))

    client.messages.create.side_effect = strict_anthropic_create
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("anthropic.Anthropic", lambda: client)
    monkeypatch.setattr(server, "_ai_cache_get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_ai_cache_put", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_record_anthropic_usage", lambda *_args, **_kwargs: None)

    result = server.adjust_cinematic_with_claude(_payload())

    assert result["ok"] is True
    assert result["assessment"]["wordCount"] == 65
    assert result["retryCount"] == 0
    assert client.messages.create.call_count == 1


def test_all_claude_schemas_avoid_unsupported_constraints() -> None:
    _assert_anthropic_schema_compatibility(server._CINEMATIC_ADJUST_SCHEMA)
    _assert_anthropic_schema_compatibility(server._PACK_SCHEMA)
    _assert_anthropic_schema_compatibility(server.EDITOR_OUTPUT_SCHEMA)


def test_strict_anthropic_mock_reproduces_original_max_items_rejection() -> None:
    old_schema = {
        "type": "array",
        "maxItems": 3,
        "items": {"type": "string"},
    }

    with pytest.raises(AssertionError):
        _assert_anthropic_schema_compatibility(old_schema)


def test_cinematic_adjust_retries_until_word_contract_is_valid(monkeypatch) -> None:
    client = MagicMock()
    client.messages.create.side_effect = [
        _message(_candidate(word_count=12)),
        _message(_candidate(word_count=65)),
    ]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_CINEMATIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr("anthropic.Anthropic", lambda: client)
    monkeypatch.setattr(server, "_ai_cache_get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_ai_cache_put", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_record_anthropic_usage", lambda *_args, **_kwargs: None)

    result = server.adjust_cinematic_with_claude(_payload())

    assert result["ok"] is True
    assert result["model"] == "claude-sonnet-4-6"
    assert result["retryCount"] == 1
    assert result["assessment"]["durationSeconds"] == 30
    assert result["assessment"]["wordCount"] == 65
    assert result["assessment"]["status"] == "ideal"
    assert client.messages.create.call_count == 2
    first_call = client.messages.create.call_args_list[0].kwargs
    assert first_call["model"] == "claude-sonnet-4-6"
    assert first_call["output_config"]["format"]["type"] == "json_schema"
    assert "Gui principal" in first_call["messages"][0]["content"]
    repair_prompt = client.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "speech tem 12 palavras" in repair_prompt
    assert "VERSAO REJEITADA" in repair_prompt


def test_cinematic_adjust_normalizes_presenter_only_mode() -> None:
    candidate = _candidate(word_count=65)
    candidate.update(
        {
            "supportingImages": "avatar_only",
            "presenterMode": "intro_outro",
            "mediaTypes": ["stock_media", "ai_generated"],
        }
    )

    adjusted = server._normalize_cinematic_adjustment(candidate)

    assert adjusted["presenterMode"] == "always"
    assert adjusted["mediaTypes"] == []
    assert server._cinematic_adjustment_issues(adjusted) == []


def test_cinematic_prompt_contains_all_current_screen_context() -> None:
    prompt = server._cinematic_adjust_user_prompt(_payload())

    assert "Uma ideia sobre conforto excessivo" in prompt
    assert "Ritmo provocativo sem sensacionalismo" in prompt
    assert "Cenas fora do tema" in prompt
    assert '"15"' in prompt
    assert '"60"' in prompt
    assert "Gui principal" in prompt
