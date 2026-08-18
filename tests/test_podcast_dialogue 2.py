from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from api import server
from api.services.podcast_dialogue import (
    PODCAST_DIALOGUE_PROMPT_VERSION,
    build_podcast_dialogue_prompt,
    normalize_podcast_dialogue,
)


def generated_dialogue() -> dict:
    return {
        "title": "O que o estudo realmente mostra",
        "turns": [
            {"speakerId": "a", "text": "O que precisamos entender primeiro?"},
            {"speakerId": "b", "text": "Que o resultado ainda precisa de contexto."},
            {"speakerId": "a", "text": "Isso já permite uma conclusão?"},
            {"speakerId": "b", "text": "Não. O material descreve um estudo em andamento."},
            {"speakerId": "a", "text": "Qual é o cuidado prático?"},
            {"speakerId": "b", "text": "Usar opções aprovadas e acompanhamento médico."},
        ],
    }


def test_normalizes_an_alternating_educational_dialogue() -> None:
    result = normalize_podcast_dialogue(generated_dialogue(), duration_seconds=45)

    assert result["title"] == "O que o estudo realmente mostra"
    assert [turn["speakerId"] for turn in result["turns"]] == ["a", "b", "a", "b", "a", "b"]


def test_rejects_a_dialogue_that_breaks_host_guest_alternation() -> None:
    dialogue = generated_dialogue()
    dialogue["turns"][2]["speakerId"] = "b"

    with pytest.raises(ValueError, match="fala 3 deveria ser do HOST"):
        normalize_podcast_dialogue(dialogue, duration_seconds=45)


def test_prompt_assigns_clear_roles_and_uses_only_the_source() -> None:
    system, user = build_podcast_dialogue_prompt(
        source={"titulo": "Pesquisa clínica", "falaBase": "O produto ainda está em estudo."},
        host_name="Munjaríto",
        guest_name="Doutor Guilherme",
        duration_seconds=60,
        direction="Priorize limitações e cuidados.",
    )

    assert "Munjaríto" in system
    assert "Doutor Guilherme" in system
    assert "Nunca invente estudo" in system
    assert "alterne rigorosamente" in system
    assert "Priorize limitações e cuidados." in user


def test_generate_endpoint_returns_a_draft_without_saving() -> None:
    raw_response = generated_dialogue()

    def strict_create(**kwargs: object) -> SimpleNamespace:
        schema = kwargs["output_config"]["format"]["schema"]  # type: ignore[index]

        def assert_compatible(value: object) -> None:
            if isinstance(value, dict):
                assert "minItems" not in value
                assert "maxItems" not in value
                for child in value.values():
                    assert_compatible(child)
            elif isinstance(value, list):
                for child in value:
                    assert_compatible(child)

        assert_compatible(schema)
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(raw_response))])

    create = Mock(side_effect=strict_create)
    fake_anthropic = SimpleNamespace(
        Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
        APIStatusError=RuntimeError,
    )
    payload = server.PodcastDialogueGenerateIn(
        sourceText="O material descreve um estudo em andamento e recomenda opções aprovadas com acompanhamento médico.",
        hostName="Munjaríto",
        guestName="Doutor Guilherme",
        durationSeconds=45,
    )

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.dict(
        sys.modules, {"anthropic": fake_anthropic}
    ), patch.object(
        server,
        "_find_script",
        return_value={
            "id": "script-podcast",
            "titulo": "Pesquisa clínica",
            "hook": "O que já sabemos?",
            "explicacaoSimples": "O estudo segue em andamento.",
            "virada": "Promissor não significa aprovado.",
            "cuidadosMedicos": "Acompanhamento médico.",
        },
    ), patch.object(server, "_ai_cache_get", return_value=None), patch.object(
        server, "_ai_cache_put"
    ) as cache_put, patch.object(server, "_record_anthropic_usage") as usage, patch.object(
        server, "_save_podcast_plan"
    ) as save_plan:
        response = server.generate_podcast_dialogue("script-podcast", payload)

    assert response["provider"] == "claude"
    assert response["promptVersion"] == PODCAST_DIALOGUE_PROMPT_VERSION
    assert response["turnCount"] == 6
    assert response["turns"] == raw_response["turns"]
    save_plan.assert_not_called()
    usage.assert_called_once()
    cache_put.assert_called_once()
    assert create.call_args.kwargs["model"] == "claude-haiku-4-5"


def test_generate_endpoint_requires_claude_configuration() -> None:
    payload = server.PodcastDialogueGenerateIn(
        sourceText="Material educativo suficiente para iniciar uma conversa segura.",
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False), patch.object(
        server, "_find_script", return_value={"id": "script-podcast"}
    ):
        with pytest.raises(server.HTTPException) as raised:
            server.generate_podcast_dialogue("script-podcast", payload)

    assert raised.value.status_code == 503
    assert "Nenhuma conversa foi salva" in str(raised.value.detail)
