from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from api import server
from api.services.medical_identity import (
    MEDICAL_EDITORIAL_PROFILE_VERSION,
    MEDICAL_EDITORIAL_PROMPT,
)


def test_video_provider_prompt_uses_the_canonical_evidence_profile() -> None:
    prompt = server._video_prompt(
        {"hook": "Uma explicação educativa baseada na fonte aprovada."},
        optimize_pronunciation=False,
    )

    assert MEDICAL_EDITORIAL_PROFILE_VERSION == "medical-editorial-profile-v2-evidence"
    assert MEDICAL_EDITORIAL_PROMPT in prompt
    assert "evidências verificáveis" in prompt


def test_short_claude_narration_is_repaired_to_selected_duration() -> None:
    payload = server.GenerateScriptIn(
        idea=server.IdeaForScriptIn(titulo="GLP-1 e escolhas", hook="Uma pergunta importante"),
        durationSeconds=45,
    )
    generated = {
        "textoFalado": "Uma fala curta.",
        "hook": "Uma pergunta importante.",
        "dorConflito": "Muita gente busca uma resposta simples para um tema complexo.",
        "explicacaoSimples": "O tema depende de contexto e não de uma explicação única.",
        "virada": "O ponto central é interpretar o achado com cuidado.",
        "cta": "Converse com seu médico.",
    }

    repaired, applied = server._repair_script_narration(generated, payload)

    assert applied is True
    assert 95 <= len(repaired.split()) <= 101
    assert server._narration_quality_issues(repaired, 45, payload.outro) == []


def test_video_agent_does_not_add_a_second_duration_gate() -> None:
    narration = (
        "O Mounjaro pode causar efeitos colaterais além das náuseas e vômitos. Estudos apontam riscos "
        "como hipoglicemia, pancreatite, desnutrição, reações alérgicas e problemas na vesícula. Cada "
        "organismo responde de uma forma diferente. Se você usa esse medicamento, acompanhe qualquer "
        "sintoma incomum e mantenha seu médico informado. Além dos efeitos comuns, existem riscos mais "
        "sérios que merecem atenção. Muitas pessoas não sabem que o Mounjaro pode causar complicações "
        "graves. Esta é uma notícia importante para quem acompanha o tratamento com regularidade. "
        "Me siga para mais dicas, e obrigado."
    )

    issues = server._video_agent_narration_quality_issues(narration, 45)

    assert not any("Texto longo" in issue for issue in issues)


def test_video_agent_blocks_repeated_narrative_before_paid_submission() -> None:
    narration = (
        "A notícia chama atenção para riscos menos comentados do Mounjaro, como pancreatite e hipoglicemia. "
        "Esses riscos menos comentados do Mounjaro, como pancreatite e hipoglicemia, merecem atenção. "
        "O mais importante é observar sintomas diferentes e conversar com seu médico. "
        "Me siga para mais dicas, e obrigado."
    )

    issues = server._video_agent_narration_quality_issues(narration, 30)

    assert "A fala repete a mesma informacao em mais de uma frase" in issues


def _draft_claude_response(adjusted_script: str, scene_texts: list[str]) -> dict[str, object]:
    return {
        "titulo": "Roteiro revisado",
        "hook": "Uma explicação importante.",
        "dorConflito": "A informação sem contexto pode confundir.",
        "explicacaoSimples": "O contexto ajuda a interpretar a mensagem.",
        "virada": "A evidência precisa ser lida com cuidado.",
        "cta": "Salve para rever",
        "cuidadosMedicos": "Confirmar as fontes antes da aprovação médica.",
        "adjustedScript": adjusted_script,
        "scriptChanges": ["Deixei a fala mais clara e dividi o argumento em duas cenas."],
        "scenes": [
            {"text": text, "lookRole": "primary", "reason": "unidade narrativa"}
            for text in scene_texts
        ],
    }


def test_create_script_from_draft_reviews_persists_and_creates_unbound_scenes() -> None:
    first_scene = " ".join(["conteúdo"] * 32)
    second_scene = " ".join(["contexto"] * 28 + ["Salve", "para", "rever"])
    adjusted_script = f"{first_scene} {second_scene}"
    response = _draft_claude_response(adjusted_script, [first_scene, second_scene])
    create_message = Mock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text=json.dumps(response))])
    )

    class FakeApiStatusError(Exception):
        status_code = 500

    fake_anthropic = SimpleNamespace(
        Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(create=create_message)),
        APIStatusError=FakeApiStatusError,
    )
    saved_plan = {
        "scriptId": "pending",
        "scenes": [
            {"id": "scene-1", "text": first_scene, "lookRole": "primary", "avatarId": ""},
            {"id": "scene-2", "text": second_scene, "lookRole": "primary", "avatarId": ""},
        ],
        "transitionStyle": "hard_cut",
    }

    def persist_script(payload: server.ScriptIn) -> dict[str, object]:
        return {"ok": True, "script": payload.model_dump()}

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.dict(
        sys.modules, {"anthropic": fake_anthropic}
    ), patch.object(server, "_ai_cache_get", return_value=None), patch.object(
        server, "_ai_cache_put"
    ), patch.object(server, "_record_anthropic_usage"), patch.object(
        server, "append_script", side_effect=persist_script
    ) as append_script, patch.object(
        server, "_save_semantic_scene_plan", return_value=saved_plan
    ) as save_plan, patch.object(server, "_save_script_editor_state") as save_editor_state:
        result = server.create_script_from_draft(
            server.CreateScriptFromDraftIn(
                draftText=adjusted_script,
                title="Título enviado",
                familia="educativo",
                editorialTone="neutro",
                durationSeconds=30,
            )
        )

    assert result["provider"] == "claude"
    assert result["script"]["textoFalado"] == adjusted_script
    assert result["script"]["generationFlowVersion"] == "draft-to-scenes-v1"
    assert result["scenePlan"] == saved_plan
    assert len(result["changes"]) == 1
    append_script.assert_called_once()
    save_plan.assert_called_once()
    assert [scene["text"] for scene in save_plan.call_args.args[1]] == [first_scene, second_scene]
    assert save_editor_state.call_args.args[0]["durationSeconds"] == 30
    assert save_editor_state.call_args.args[0]["previousScript"] == adjusted_script
    claude_call = create_message.call_args.kwargs
    assert MEDICAL_EDITORIAL_PROMPT in claude_call["system"]
    assert adjusted_script in claude_call["messages"][0]["content"]


def test_create_script_from_draft_rejects_commercial_cta_before_any_write() -> None:
    first_scene = " ".join(["conteúdo"] * 32)
    second_scene = " ".join(["contexto"] * 26 + ["Me", "siga", "para", "mais", "dicas"])
    adjusted_script = f"{first_scene} {second_scene}"
    response = _draft_claude_response(adjusted_script, [first_scene, second_scene])

    class FakeApiStatusError(Exception):
        status_code = 500

    fake_anthropic = SimpleNamespace(
        Anthropic=lambda: SimpleNamespace(
            messages=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    content=[SimpleNamespace(text=json.dumps(response))]
                )
            )
        ),
        APIStatusError=FakeApiStatusError,
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False), patch.dict(
        sys.modules, {"anthropic": fake_anthropic}
    ), patch.object(server, "_ai_cache_get", return_value=None), patch.object(
        server, "_ai_cache_put"
    ), patch.object(server, "_record_anthropic_usage"), patch.object(
        server, "append_script"
    ) as append_script, patch.object(server, "_save_semantic_scene_plan") as save_plan:
        with pytest.raises(server.HTTPException) as raised:
            server.create_script_from_draft(
                server.CreateScriptFromDraftIn(
                    draftText=adjusted_script,
                    durationSeconds=30,
                )
            )

    assert raised.value.status_code == 502
    assert "CTA comercial ou de captação" in str(raised.value.detail)
    append_script.assert_not_called()
    save_plan.assert_not_called()
