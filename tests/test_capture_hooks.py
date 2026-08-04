from api.server import (
    MANDATORY_VIDEO_OUTRO,
    CaptureHooksIn,
    _capture_hooks_fallback,
    _fit_ten_second_text,
    _fit_text_to_duration,
    _narration_quality_issues,
    _normalize_capture_hooks,
    _validate_final_narration,
    _video_prompt,
)


def _payload() -> CaptureHooksIn:
    return CaptureHooksIn(
        trendId="trend-1",
        titulo="Nova conversa sobre saúde metabólica",
        familia="metabolismo",
        prioridade="alta",
    )


def test_fallback_creates_three_distinct_ten_second_hooks() -> None:
    result = _normalize_capture_hooks(_payload(), _capture_hooks_fallback(_payload()))

    assert len(result["variants"]) == 3
    assert len({item["strategy"] for item in result["variants"]}) == 3
    assert len({item["spokenText"] for item in result["variants"]}) == 3
    for item in result["variants"]:
        assert 18 <= item["wordCount"] <= 24
        assert "perfil" not in item["spokenText"].lower()
        assert 1 <= item["stopScore"] <= 10
        assert 1 <= item["profileScore"] <= 10


def test_normalizer_repairs_invalid_length_outro_and_scores() -> None:
    invalid = {
        "analysis": {"capturePotential": 99},
        "variants": [
            {"spokenText": "Curto demais.", "stopScore": 50, "profileScore": -8},
            {},
            {},
        ],
    }

    result = _normalize_capture_hooks(_payload(), invalid)

    assert result["analysis"]["capturePotential"] == 10
    assert len(result["variants"]) == 3
    for item in result["variants"]:
        assert 18 <= item["wordCount"] <= 24
        assert "perfil" not in item["spokenText"].lower()
        assert 1 <= item["stopScore"] <= 10
        assert 1 <= item["profileScore"] <= 10


def test_ten_second_video_removes_saved_final_phrase() -> None:
    narration = (
        "Esse detalhe muda a forma de entender a tendência e faz você perceber algo "
        "que passou despercebido até agora. Me siga para mais dicas, e obrigado."
    )

    final_text = _validate_final_narration({}, narration, 10, "Me siga para mais dicas, e obrigado.")
    prompt = _video_prompt(
        {},
        duration_seconds=10,
        narration_text=narration,
        outro_text="Me siga para mais dicas, e obrigado.",
    )

    assert "Me siga" not in final_text
    assert "Me siga" not in prompt
    assert "closing phrase" in prompt
    assert "single-take talking-head" in prompt
    assert "verbatim" in prompt
    assert "Leverage motion graphics" not in prompt
    assert "Do not create multiple scenes" in prompt
    assert "existing background exactly as-is" in prompt
    assert "Do not add transitions or filler words" in prompt
    assert _narration_quality_issues(final_text, 10, "") == []


def test_long_script_is_reduced_to_a_ten_second_hook() -> None:
    long_text = (
        "Você dorme cinco horas ou menos toda noite? Sabe aquela gordura que se acumula "
        "silenciosamente e você nem vê? Um estudo acompanhou milhares de pessoas durante anos "
        "e encontrou uma associação que precisa ser interpretada com bastante cuidado antes de "
        "qualquer conclusão individual."
    )

    shortened = _fit_ten_second_text(long_text)

    assert 18 <= len(shortened.split()) <= 24
    assert shortened.endswith(("?", ".", "!", "…"))


def test_fallback_creates_three_selectable_fifteen_second_hooks() -> None:
    payload = _payload().model_copy(update={"durationSeconds": 15})

    result = _normalize_capture_hooks(payload, _capture_hooks_fallback(payload))

    assert len(result["variants"]) == 3
    for item in result["variants"]:
        assert 25 <= item["wordCount"] <= 36
        assert item["spokenText"].endswith(MANDATORY_VIDEO_OUTRO)


def test_long_script_is_reduced_to_fifteen_seconds_with_outro() -> None:
    long_text = (
        "Você dorme cinco horas ou menos toda noite? Um estudo acompanhou milhares de pessoas "
        "durante anos e encontrou uma associação importante com gordura no fígado que merece "
        "contexto cuidadoso e avaliação individual antes de qualquer conclusão ou mudança de hábito."
    )

    shortened = _fit_text_to_duration(long_text, 15, MANDATORY_VIDEO_OUTRO)

    assert 25 <= len(shortened.split()) <= 36
    assert shortened.endswith(MANDATORY_VIDEO_OUTRO)
    assert _narration_quality_issues(shortened, 15, MANDATORY_VIDEO_OUTRO) == []
