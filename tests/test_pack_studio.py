"""Estúdio de Pack: edição local, clareza e custo zero de tokens.

Estes testes protegem a regra central do produto: só a criação de conteúdo
textual pode chamar o Claude. Trocar família, tema, foto, layout, editar o
texto de um slide ou restaurar uma versão são operações locais e
determinísticas — se alguma delas voltar a instanciar um cliente Anthropic, o
teste falha.
"""
from __future__ import annotations

import sys
import types
from copy import deepcopy

import pytest

from api.pack_design import (
    LAYOUT_EDITABLE_FIELDS,
    LAYOUT_LABELS,
    PACK_LAYOUTS,
    explainer_steps_from_body,
    pack_clarity,
    repair_pack_copy,
    slide_clarity,
    slide_export_text,
    validate_pack_contract,
)
from api.services.medical_identity import (
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
    ensure_medical_publication_notice,
)
from api.slides import slide_html
from tests.test_pack_design import sample_pack


class _ClaudeCalled(AssertionError):
    """Levantado se qualquer caminho local tentar falar com o Claude."""


@pytest.fixture()
def no_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitui o módulo ``anthropic`` por um que explode ao ser usado."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise _ClaudeCalled("esta operacao nao pode chamar o Claude")

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _explode  # type: ignore[attr-defined]
    fake.APIStatusError = type("APIStatusError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)


@pytest.fixture()
def stored_pack(monkeypatch: pytest.MonkeyPatch):
    """Pack salvo em memória, com a mesma superfície usada pelos endpoints."""
    from api import server

    state = {"pack": repair_pack_copy(sample_pack())}
    state["pack"]["sourceAvatarId"] = "avatar-teste"
    versions: list[dict[str, object]] = []

    monkeypatch.setattr(server, "_find_script", lambda _script_id: {"id": _script_id})
    monkeypatch.setattr(server, "_get_visual_pack", lambda _script_id: deepcopy(state["pack"]))

    def _save(_script_id: str, pack: dict) -> dict:
        state["pack"] = deepcopy(pack)
        return state["pack"]

    def _snapshot(_script_id: str, origin: str) -> int:
        versions.insert(0, {"id": len(versions) + 1, "origin": origin, "pack": deepcopy(state["pack"])})
        return len(versions)

    monkeypatch.setattr(server, "_save_visual_pack", _save)
    monkeypatch.setattr(server, "_snapshot_visual_pack", _snapshot)
    monkeypatch.setattr(
        server,
        "_list_visual_pack_versions",
        lambda _script_id: [
            {"id": item["id"], "origin": item["origin"], "summary": "", "createdAt": ""}
            for item in versions
        ],
    )
    monkeypatch.setattr(
        server,
        "_get_visual_pack_version",
        lambda _script_id, version_id: next(
            (deepcopy(item["pack"]) for item in versions if item["id"] == version_id), None
        ),
    )
    return state, versions


# --------------------------------------------------------------------------
# Conteúdo: reparos determinísticos, sem IA
# --------------------------------------------------------------------------


def test_explainer_steps_reuse_an_enumeration_already_written_in_the_body() -> None:
    body = (
        "O remedio age em tres caminhos hormonais. O primeiro reduz a fome no cerebro. "
        "O segundo melhora como o corpo usa energia. O terceiro aumenta o gasto em repouso. "
        "Essa acao tripla e o que o diferencia."
    )

    remaining, steps = explainer_steps_from_body(body)

    assert [step["title"] for step in steps] == ["Primeiro", "Segundo", "Terceiro"]
    assert steps[0]["text"].startswith("Reduz a fome")
    # As frases usadas viram etapas e saem do parágrafo; nada é inventado.
    assert "O primeiro reduz" not in remaining
    assert "Essa acao tripla" in remaining


def test_explainer_steps_ignore_prose_without_a_real_enumeration() -> None:
    body = (
        "A obesidade e uma condicao multifatorial. Genetica, ambiente e comportamento "
        "se combinam de formas diferentes em cada pessoa."
    )

    remaining, steps = explainer_steps_from_body(body)

    assert steps == []
    assert remaining == body


def test_repair_fills_explainer_steps_without_calling_the_model(no_claude: None) -> None:
    pack = sample_pack()
    explainer = pack["carousel"][3]
    explainer["fields"]["body"] = (
        "O corpo reage em tres frentes. O primeiro sinal e mais fome. "
        "O segundo e menos gasto de energia. O terceiro e a rotina que aperta."
    )
    for name in ("item1", "item2", "item3"):
        explainer["fields"][name] = {"title": "", "text": ""}

    repaired = repair_pack_copy(pack)
    fields = repaired["carousel"][3]["fields"]

    assert fields["item1"]["title"] == "Primeiro"
    assert fields["item3"]["text"]
    assert validate_pack_contract(repaired) == []


def test_explainer_without_steps_renders_a_prose_block_instead_of_an_empty_grid() -> None:
    slide = deepcopy(sample_pack()["carousel"][3])
    for name in ("item1", "item2", "item3"):
        slide["fields"][name] = {"title": "", "text": ""}

    html = slide_html(slide, index=4, total=7)

    assert "explainer-prose" in html
    # Sem etapas, a grade de cartões nem chega a ser desenhada.
    assert '<div class="steps">' not in html


def test_question_footer_does_not_promise_an_answer_that_never_comes() -> None:
    slide = deepcopy(sample_pack()["carousel"][1])
    slide["fields"]["footer"] = ""

    middle = slide_html(slide, index=2, total=7)
    last_content = slide_html(slide, index=6, total=7)

    # Slide com resposta na própria tela não pode mandar esperar o próximo card.
    assert "Resposta no próximo card" not in middle
    assert "Continua no próximo card" in middle
    assert "Continua no próximo card" not in last_content


def test_caption_drops_the_separator_left_by_removing_the_publication_notice() -> None:
    raw = (
        "Entenda o que muda no tratamento. | "
        + MEDICAL_EDUCATIONAL_DISCLAIMER
        + "\n"
        + MEDICAL_PROFESSIONAL_IDENTIFICATION
    )

    caption = ensure_medical_publication_notice(raw)

    assert "tratamento. |" not in caption
    assert caption.startswith("Entenda o que muda no tratamento.")
    assert MEDICAL_PROFESSIONAL_IDENTIFICATION in caption


def test_caption_already_clean_is_not_rewritten() -> None:
    clean = ensure_medical_publication_notice("Texto editorial.")
    assert ensure_medical_publication_notice(clean) == clean


def test_thumbnail_endpoint_renders_the_seven_slides_once_and_invalidates_cache(
    no_claude: None,
    stored_pack,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from api import server, slides

    state, _versions = stored_pack
    state["pack"]["updatedAt"] = "2026-08-18T10:00:00Z"
    state["pack"]["family"] = "didatico"
    state["pack"]["themeId"] = "soft-sage"
    renders: list[tuple[str, str, bool]] = []

    def _render(
        output_dir,
        carousel,
        *,
        family: str,
        theme_id: str,
        grayscale_photos: bool,
    ):
        rows = list(carousel)
        renders.append((family, theme_id, grayscale_photos))
        output_dir.mkdir(parents=True, exist_ok=True)
        for index in range(1, len(rows) + 1):
            (output_dir / f"slide-{index:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"images": len(rows), "width": 270, "height": 338}

    monkeypatch.setattr(server, "PACK_PREVIEWS", tmp_path / "pack_previews")
    monkeypatch.setattr(slides, "render_pack_thumbnails", _render)

    first = server.get_pack_slide_thumbnail("s-test", 0)
    seventh = server.get_pack_slide_thumbnail("s-test", 6)

    assert renders == [("didatico", "soft-sage", True)]
    assert first.path != seventh.path
    assert first.headers["cache-control"] == "public, max-age=31536000, immutable"

    state["pack"]["updatedAt"] = "2026-08-18T10:01:00Z"
    after_copy = server.get_pack_slide_thumbnail("s-test", 0)
    state["pack"]["family"] = "editorial"
    after_family = server.get_pack_slide_thumbnail("s-test", 0)
    state["pack"]["themeId"] = "soft-rose"
    after_theme = server.get_pack_slide_thumbnail("s-test", 0)
    state["pack"]["grayscalePhotos"] = False
    after_photo_treatment = server.get_pack_slide_thumbnail("s-test", 0)

    assert len(renders) == 5
    assert len(
        {first.path, after_copy.path, after_family.path, after_theme.path, after_photo_treatment.path}
    ) == 5
    assert renders[-1] == ("editorial", "soft-rose", False)


# --------------------------------------------------------------------------
# Export: o arquivo de texto precisa conter o conteúdo real do slide
# --------------------------------------------------------------------------


def test_exported_text_includes_items_statistic_and_quote() -> None:
    pack = repair_pack_copy(sample_pack())

    three_points = slide_export_text(pack["carousel"][4])
    quote = slide_export_text(pack["carousel"][5])

    assert "Sono" in three_points and "Comida" in three_points and "Cuidado" in three_points
    assert "O melhor plano" in quote


# --------------------------------------------------------------------------
# Clareza: sinais locais, sem tokens
# --------------------------------------------------------------------------


def test_clarity_flags_a_number_without_any_explanation() -> None:
    slide = {
        "layoutId": "big_statement",
        "variant": "light",
        "fields": {"headline": "Estudos mostram: 24,2% a 28,3% de perda"},
    }

    warnings = slide_clarity(slide)["warnings"]

    assert any("numerico" in warning for warning in warnings)


def test_clarity_accepts_the_explainer_prose_fallback_without_a_false_warning() -> None:
    slide = deepcopy(sample_pack()["carousel"][3])
    for name in ("item1", "item2", "item3"):
        slide["fields"][name] = {"title": "", "text": ""}

    warnings = slide_clarity(slide)["warnings"]

    assert not any("etapas" in warning for warning in warnings)


def test_clarity_report_covers_every_slide_of_a_valid_pack() -> None:
    report = pack_clarity(repair_pack_copy(sample_pack()))

    assert len(report["slides"]) == 7
    assert report["distinctLayouts"] >= 4
    assert report["empty"] == []


def test_every_layout_declares_editable_fields_and_a_label() -> None:
    for layout_id in PACK_LAYOUTS:
        assert LAYOUT_EDITABLE_FIELDS.get(layout_id), layout_id
        assert LAYOUT_LABELS.get(layout_id), layout_id


def test_every_declared_editable_field_is_accepted_by_the_endpoint_contract() -> None:
    from api import server

    declared = {
        field
        for editable_fields in LAYOUT_EDITABLE_FIELDS.values()
        for field in editable_fields
    }

    assert declared <= set(server.PackSlideFieldsIn.model_fields)


# --------------------------------------------------------------------------
# Custo: nenhuma operação local pode chamar o Claude
# --------------------------------------------------------------------------


def test_changing_family_and_theme_never_calls_claude(no_claude: None, stored_pack) -> None:
    from api import server

    state, _versions = stored_pack
    original = deepcopy(state["pack"]["carousel"])

    response = server.update_pack_presentation(
        "s-test", server.PackPresentationIn(family="manifesto", themeId="soft-rose")
    )

    assert response["pack"]["family"] == "manifesto"
    assert response["pack"]["themeId"] == "soft-rose"
    # A troca é puramente de apresentação: a copy não pode mudar.
    assert [slide["fields"] for slide in response["pack"]["carousel"]] == [
        slide["fields"] for slide in original
    ]
    assert response["clarity"]["slides"]


def test_changing_layout_never_calls_claude(no_claude: None, stored_pack) -> None:
    from api import server

    state, _versions = stored_pack
    headline_before = state["pack"]["carousel"][1]["fields"]["headline"]

    response = server.update_pack_carousel_layout(
        "s-test", 1, server.PackSlideLayoutIn(layout="big_statement")
    )

    assert response["pack"]["carousel"][1]["layoutId"] == "big_statement"
    assert response["pack"]["carousel"][1]["fields"]["headline"] == headline_before


def test_editing_slide_text_never_calls_claude(no_claude: None, stored_pack) -> None:
    from api import server

    state, versions = stored_pack

    response = server.update_pack_carousel_fields(
        "s-test",
        1,
        server.PackSlideFieldsIn(headline="Fome ou habito: como notar a diferenca?"),
    )

    assert response["pack"]["carousel"][1]["fields"]["headline"].startswith("Fome ou habito")
    # Os outros slides continuam exatamente como estavam.
    assert response["pack"]["carousel"][0]["fields"] == state["pack"]["carousel"][0]["fields"]
    # A primeira edição guarda uma versão de segurança...
    assert [item["origin"] for item in versions] == ["edicao-manual"]

    server.update_pack_carousel_fields(
        "s-test", 1, server.PackSlideFieldsIn(headline="Fome ou habito: como perceber?")
    )
    # ...e as edições seguintes não criam uma versão a cada salvamento.
    assert [item["origin"] for item in versions] == ["edicao-manual"]


def test_editing_cover_note_is_persisted_without_claude(no_claude: None, stored_pack) -> None:
    from api import server

    response = server.update_pack_carousel_fields(
        "s-test",
        0,
        server.PackSlideFieldsIn(coverNote="Uma observação curta e educativa na capa."),
    )

    assert response["pack"]["carousel"][0]["fields"]["coverNote"] == (
        "Uma observação curta e educativa na capa."
    )


def test_editing_cover_note_reports_the_layout_limit(no_claude: None, stored_pack) -> None:
    from api import server
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        server.update_pack_carousel_fields(
            "s-test", 0, server.PackSlideFieldsIn(coverNote="x" * 181)
        )

    assert error.value.status_code == 422
    assert "Mensagem na capa tem 181 caracteres" in str(error.value.detail)
    assert "Abertura com foto comporta 180" in str(error.value.detail)


def test_editing_rejects_text_that_does_not_fit_the_layout(no_claude: None, stored_pack) -> None:
    from api import server
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        server.update_pack_carousel_fields(
            "s-test", 1, server.PackSlideFieldsIn(headline="palavra " * 40)
        )

    assert error.value.status_code == 422
    assert "caracteres" in str(error.value.detail)


def test_editing_allows_an_existing_explicit_negation_of_a_cure_claim(
    no_claude: None, stored_pack
) -> None:
    from api import server

    state, _versions = stored_pack
    state["pack"]["carousel"][4]["fields"]["body"] = (
        "Redução de gordura no fígado não cura fibrose."
    )

    response = server.update_pack_carousel_fields(
        "s-test", 1, server.PackSlideFieldsIn(headline="Uma correção editorial local")
    )

    assert response["pack"]["carousel"][1]["fields"]["headline"] == (
        "Uma correção editorial local"
    )


def test_editing_still_blocks_a_positive_cure_claim(no_claude: None, stored_pack) -> None:
    from api import server
    from fastapi import HTTPException

    state, _versions = stored_pack
    state["pack"]["carousel"][4]["fields"]["body"] = "Esta abordagem cura fibrose."

    with pytest.raises(HTTPException) as error:
        server.update_pack_carousel_fields(
            "s-test", 1, server.PackSlideFieldsIn(headline="Uma correção editorial local")
        )

    assert error.value.status_code == 422
    assert "Palavra ou promessa proibida: cura" in str(error.value.detail)


def test_editing_allows_medication_names_and_formulations_without_a_false_block(
    no_claude: None, stored_pack
) -> None:
    from api import server

    state, _versions = stored_pack
    state["pack"]["carousel"][0]["fields"]["headline"] = "Novo comprimido aprovado"
    state["pack"]["carousel"][2]["fields"]["body"] = "O comprimido exige revisão médica."

    response = server.update_pack_carousel_fields(
        "s-test", 0, server.PackSlideFieldsIn(headline="Nova forma oral aprovada")
    )

    assert response["pack"]["carousel"][0]["fields"]["headline"] == "Nova forma oral aprovada"
    assert response["compliance"]["blocked"] is False
    assert response["compliance"]["issues"] == []


def test_pack_compliance_still_blocks_a_specific_numeric_dose() -> None:
    from api import server

    response = server._pack_compliance(
        {"text": "A apresentação estudada usou 2,4 mg por semana."}
    )

    assert response["blocked"] is True
    assert response["issues"] == ["Possível menção de dose específica"]


def test_claude_pack_prompts_require_lay_positive_copy_and_responsible_hype() -> None:
    from api import server

    for prompt in (
        server._PACK_SYSTEM,
        server._TRANSCRIPT_PACK_SYSTEM,
        server._PACK_SLIDE_SYSTEM,
    ):
        assert "pessoas leigas" in prompt
        assert "positiv" in prompt
        assert "hype editorial respons" in prompt


def test_compliance_fields_of_the_last_slide_cannot_be_edited(no_claude: None, stored_pack) -> None:
    from api import server
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        server.update_pack_carousel_fields(
            "s-test", 6, server.PackSlideFieldsIn(footer="Agende sua consulta")
        )

    assert error.value.status_code == 422


def test_editing_rejects_a_commercial_call_to_action(no_claude: None, stored_pack) -> None:
    from api import server
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        server.update_pack_carousel_fields(
            "s-test", 6, server.PackSlideFieldsIn(cta="Agende agora")
        )

    assert error.value.status_code == 422


def test_restoring_a_version_never_calls_claude(no_claude: None, stored_pack) -> None:
    from api import server

    state, _versions = stored_pack
    original_headline = state["pack"]["carousel"][1]["fields"]["headline"]

    server.update_pack_carousel_fields(
        "s-test", 1, server.PackSlideFieldsIn(headline="Texto trocado pelo editor")
    )
    assert state["pack"]["carousel"][1]["fields"]["headline"] == "Texto trocado pelo editor"

    response = server.restore_pack_version("s-test", 1)

    assert response["pack"]["carousel"][1]["fields"]["headline"] == original_headline
    assert response["clarity"]["slides"]


def test_changing_photo_never_calls_claude_and_never_exports(no_claude: None, stored_pack, monkeypatch) -> None:
    from api import server

    monkeypatch.setattr(
        server,
        "_pack_photo_asset",
        lambda _asset_id: {
            "id": "wide-office",
            "name": "Consultório amplo",
            "cachedAssetPath": "data/pack_assets/photos/vine8178.jpg",
            "facePointX": 0.5,
            "facePointY": 0.4,
            "brightness": 1.0,
        },
    )

    def _fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("trocar a foto nao pode disparar a exportacao de PNGs")

    monkeypatch.setattr("api.slides.render_pack_images", _fail_render)

    response = server.update_pack_carousel_photo(
        "s-test", 0, server.PackSlidePhotoIn(photoAssetId="wide-office")
    )

    assert response["pack"]["carousel"][0]["fields"]["photoId"] == "wide-office"
    assert response["pack"]["slides"] == response["pack"]["carousel"]


def test_removing_photo_preserves_layout_and_copy(no_claude: None, stored_pack) -> None:
    from api import server

    before = stored_pack[0]["pack"]["carousel"][0]
    headline = before["fields"]["headline"]
    layout = before["layoutId"]

    response = server.update_pack_carousel_photo(
        "s-test", 0, server.PackSlidePhotoIn(photoAssetId=None)
    )
    slide = response["pack"]["carousel"][0]

    assert slide["layoutId"] == layout
    assert slide["fields"]["headline"] == headline
    assert slide["fields"]["photoId"] == ""
    assert slide.get("photoAsset") is None


def test_design_system_exposes_real_limits_for_every_layout(no_claude: None) -> None:
    from api import server

    payload = server.get_pack_design_system()
    layouts = {layout["id"]: layout for layout in payload["layouts"]}

    assert set(layouts) == set(PACK_LAYOUTS)
    assert layouts["myth_fact"]["itemMaxChars"]["text"] > 0
    assert layouts["explainer"]["editableFields"][0] == "eyebrow"
    assert layouts["hero_photo"]["photoOptional"] is True
    assert "photoId" not in layouts["hero_photo"]["required"]
    assert payload["photoOptional"] is True
    assert payload["grayscalePhotosDefault"] is True
    assert payload["fieldLabels"]["headline"]
