from __future__ import annotations

from api import server


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
    assert 85 <= len(repaired.split()) <= 108
    assert server._narration_quality_issues(repaired, 45, payload.outro) == []
