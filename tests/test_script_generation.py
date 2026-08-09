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
