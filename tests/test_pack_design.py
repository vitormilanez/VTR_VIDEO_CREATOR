from __future__ import annotations

from copy import deepcopy

from api.pack_design import (
    LAYOUT_SPECS,
    PACK_LAYOUTS,
    PACK_SCHEMA_VERSION,
    PHOTO_LIBRARY,
    empty_fields,
    normalize_slide,
    pack_slides,
    repair_pack_copy,
    validate_pack_contract,
)
from api.services.medical_identity import (
    MEDICAL_DEFAULT_SAFE_CTA,
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
    MEDICAL_PUBLICATION_NOTICE,
    MEDICAL_ROLE_AND_REGISTERED_SPECIALTY,
)
from api.slides import slide_html


EXPECTED_ADDED_PACK_PHOTOS = {
    "institute-reading-front": "gui-instituto-leitura-frente.png",
    "institute-reading-side": "gui-instituto-leitura-lateral.png",
    "vivance-horizontal-portrait": "gui-vivance-retrato-horizontal.png",
    "vivance-seated-sign": "gui-vivance-sentado-placa.png",
    "vivance-seated-full-body": "gui-vivance-sentado-corpo-inteiro.png",
    "vivance-standing-crossed-arms": "gui-vivance-em-pe-bracos-cruzados.png",
    "vivance-seated-close": "gui-vivance-sentado-close.png",
    "vivance-crossed-arms-close": "gui-vivance-bracos-cruzados-close.png",
    "vivance-office-thoughtful": "gui-vivance-escritorio-pensativo.png",
    "vivance-office-standing": "gui-vivance-escritorio-em-pe.png",
    "vivance-outdoor-half-body": "gui-vivance-externo-meio-corpo.png",
    "vivance-seated-portrait": "gui-vivance-sentado-retrato.png",
    "vivance-seated-close-alt": "gui-vivance-sentado-close-alternativo.png",
    "vivance-outdoor-hands-pockets": "gui-vivance-externo-maos-bolsos.png",
    "vivance-crossed-arms-portrait": "gui-vivance-bracos-cruzados-retrato.png",
    "vivance-outdoor-full-body": "gui-vivance-externo-corpo-inteiro.png",
}


def _fields(**values: object) -> dict[str, object]:
    fields = empty_fields()
    fields.update(values)
    return fields


def sample_pack() -> dict[str, object]:
    slides = [
        {
            "layoutId": "hero_photo",
            "variant": "dark",
            "fields": _fields(
                eyebrow="Metabolismo",
                headline="Por que o peso volta depois da dieta",
                footer="Entenda em sete telas",
                photoId="seated-front",
            ),
        },
        {
            "layoutId": "question",
            "variant": "light",
            "fields": _fields(
                eyebrow="Observe o padrao",
                headline="Fome ou habito: como perceber a diferenca?",
                body="A resposta costuma aparecer quando voce observa horario, emocao e saciedade.",
            ),
        },
        {
            "layoutId": "myth_fact",
            "variant": "light",
            "fields": _fields(
                item1={"title": "Mito", "text": "Voltar a engordar e falta disciplina"},
                item2={"title": "Fato", "text": "O corpo tenta recuperar o peso perdido"},
                body="Biologia e ambiente tambem influenciam o resultado.",
            ),
        },
        {
            "layoutId": "explainer",
            "variant": "light",
            "fields": _fields(
                eyebrow="Contexto",
                headline="Por que isso acontece",
                body="Depois de emagrecer, o corpo pode aumentar fome e reduzir gasto de energia. Isso nao e falha moral: e uma resposta biologica que precisa de plano sustentavel.",
                item1={"title": "Fome", "text": "Sinais internos mudam."},
                item2={"title": "Energia", "text": "O gasto pode cair."},
                item3={"title": "Rotina", "text": "O plano precisa caber na vida."},
            ),
        },
        {
            "layoutId": "three_points",
            "variant": "dark",
            "fields": _fields(
                headline="O que sustenta o resultado",
                item1={"title": "Sono", "text": "Rotina previsivel ajuda a regular fome e energia."},
                item2={"title": "Comida", "text": "Escolhas possiveis funcionam melhor que restricao extrema."},
                item3={"title": "Cuidado", "text": "Acompanhamento ajusta a estrategia ao longo do tempo."},
            ),
        },
        {
            "layoutId": "doctor_quote",
            "variant": "warm",
            "fields": _fields(
                quote="O melhor plano e aquele que cabe na vida e pode ser ajustado.",
                caption="Dr. Guilherme Martins",
                photoId="portrait-closeup",
            ),
        },
        {
            "layoutId": "cta_photo",
            "variant": "dark",
            "fields": _fields(
                headline="Troque culpa por uma avaliacao individual",
                body="Entender a causa e o primeiro passo para escolher um cuidado possivel.",
                cta=MEDICAL_DEFAULT_SAFE_CTA,
                disclaimer=MEDICAL_EDUCATIONAL_DISCLAIMER,
                footer=MEDICAL_PROFESSIONAL_IDENTIFICATION,
                photoId="seated-lean",
            ),
        },
    ]
    return {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "caption": (
            "Peso nao depende de uma unica escolha. Observe o contexto e procure cuidado individual.\n\n"
            + MEDICAL_PUBLICATION_NOTICE
        ),
        "hashtags": ["#saudemetabolica", "#educacaoemsaude"],
        "slides": slides,
        "carousel": slides,
    }


def test_sample_pack_follows_closed_contract() -> None:
    assert validate_pack_contract(sample_pack()) == []


def test_doctor_quote_uses_the_registered_medical_identification() -> None:
    html = slide_html(sample_pack()["slides"][5], index=6, total=7)

    assert MEDICAL_ROLE_AND_REGISTERED_SPECIALTY in html
    assert "Endocrinologia e Metabologia" not in html


def test_photo_library_ids_point_to_their_visual_content() -> None:
    assert PHOTO_LIBRARY["wide-office"]["file"].endswith("vine8178.jpg")
    assert PHOTO_LIBRARY["seated-side"]["file"].endswith("vine8172.jpg")
    assert PHOTO_LIBRARY["seated-lean"]["file"].endswith("vine8163.jpg")
    assert PHOTO_LIBRARY["seated-arm"]["file"].endswith("vine8150.jpg")
    assert PHOTO_LIBRARY["seated-front"]["file"].endswith("vine8142.jpg")
    assert PHOTO_LIBRARY["portrait-closeup"]["file"].endswith("vine8121.jpg")
    assert PHOTO_LIBRARY["institute-desk-pose"]["file"].endswith(
        "gui-instituto-escritorio-pose.png"
    )
    assert PHOTO_LIBRARY["institute-reading-front"]["file"].endswith(
        "gui-instituto-leitura-frente.png"
    )
    assert PHOTO_LIBRARY["institute-reading-side"]["file"].endswith(
        "gui-instituto-leitura-lateral.png"
    )
    assert PHOTO_LIBRARY["white-polo-portrait"]["file"].endswith(
        "gui-polo-retrato-escuro.jpeg"
    )
    for photo_id, filename in EXPECTED_ADDED_PACK_PHOTOS.items():
        assert PHOTO_LIBRARY[photo_id]["file"].endswith(filename)


def test_added_pack_photos_exist_and_have_complete_metadata() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for photo_id in EXPECTED_ADDED_PACK_PHOTOS:
        photo = PHOTO_LIBRARY[photo_id]
        assert (root / photo["file"]).is_file()
        assert photo["name"]
        assert photo["description"]
        assert 0 <= photo["facePointX"] <= 1
        assert 0 <= photo["facePointY"] <= 1
        assert 0 <= photo["brightness"] <= 1


def test_normalize_slide_refreshes_stale_photo_path_from_canonical_library() -> None:
    normalized = normalize_slide(
        {
            "layoutId": "hero_photo",
            "fields": _fields(headline="Capa", photoId="wide-office"),
            "photoAsset": {
                "id": "wide-office",
                "cachedAssetPath": "data/pack_assets/photos/vine8121.jpg",
            },
        },
        0,
    )

    assert normalized["photoAsset"]["cachedAssetPath"].endswith("vine8178.jpg")


def test_pack_slides_prefers_edited_carousel_over_legacy_alias() -> None:
    current = [{"fields": {"photoId": "wide-office"}}]
    legacy = [{"fields": {"photoId": "seated-front"}}]

    assert pack_slides({"carousel": current, "slides": legacy}) is current


def test_photo_update_synchronizes_carousel_and_legacy_alias(monkeypatch) -> None:
    from api import server

    pack = sample_pack()
    pack["carousel"] = deepcopy(pack["carousel"])
    pack["slides"] = deepcopy(pack["slides"])
    asset = {
        "id": "wide-office",
        "name": "Consultório amplo",
        "cachedAssetPath": "data/pack_assets/photos/vine8178.jpg",
        "facePointX": 0.5,
        "facePointY": 0.4,
        "brightness": 1.0,
    }
    monkeypatch.setattr(server, "_find_script", lambda _script_id: {})
    monkeypatch.setattr(server, "_get_visual_pack", lambda _script_id: pack)
    monkeypatch.setattr(server, "_pack_photo_asset", lambda _asset_id: asset)
    monkeypatch.setattr(server, "_save_visual_pack", lambda _script_id, value: value)

    response = server.update_pack_carousel_photo(
        "s-test",
        0,
        server.PackSlidePhotoIn(photoAssetId="wide-office"),
    )

    assert response["pack"]["carousel"][0]["fields"]["photoId"] == "wide-office"
    assert response["pack"]["slides"] == response["pack"]["carousel"]


def test_cover_note_update_is_saved_on_slide_one_without_regenerating_pack(monkeypatch) -> None:
    from api import server

    pack = sample_pack()
    pack["carousel"] = deepcopy(pack["carousel"])
    pack["slides"] = deepcopy(pack["slides"])
    saved: dict[str, object] = {}
    monkeypatch.setattr(server, "_find_script", lambda _script_id: {})
    monkeypatch.setattr(server, "_get_visual_pack", lambda _script_id: pack)
    monkeypatch.setattr(
        server,
        "_save_visual_pack",
        lambda _script_id, value: saved.setdefault("pack", value) or value,
    )

    response = server.update_pack_cover_note(
        "s-test",
        server.PackCoverNoteIn(text="Atendimento individual, com escuta e estratégia."),
    )

    assert response["pack"]["carousel"][0]["fields"]["coverNote"] == (
        "Atendimento individual, com escuta e estratégia."
    )
    assert response["pack"]["slides"] == response["pack"]["carousel"]
    assert saved["pack"] == response["pack"]


def test_cover_note_is_limited_by_contract_and_rendered_with_auto_fit_box() -> None:
    pack = sample_pack()
    cover_note = "Uma mensagem de capa mais longa para confirmar que a tipografia será ajustada " * 3
    pack["slides"][0]["fields"]["coverNote"] = cover_note

    repaired = repair_pack_copy(pack)
    html = slide_html(repaired["slides"][0], index=1, total=7)

    assert len(repaired["slides"][0]["fields"]["coverNote"]) <= 180
    assert len(repaired["slides"][0]["fields"]["coverNote"]) < len(cover_note.strip())
    assert validate_pack_contract(repaired) == []
    assert "cover-note-text auto-fit" in html
    assert 'data-min-font-size="24"' in html
    assert "document.fonts.ready.then(fit)" in html


def test_contract_rejects_extra_slide_and_long_headline() -> None:
    pack = sample_pack()
    pack["carousel"] = [*pack["carousel"], pack["carousel"][-1]]
    pack["carousel"][0]["fields"]["headline"] = "Uma manchete longa demais para caber com leitura simples no primeiro slide"

    errors = validate_pack_contract(pack)

    assert any("8 itens" in error for error in errors)
    assert any("headline" in error for error in errors)


def test_contract_rejects_broken_myth_fact_fragments_before_truncation() -> None:
    pack = sample_pack()
    pack["slides"][2]["fields"]["item1"] = {
        "title": "Se meu pai",
        "text": "Predisposicao aumenta risco, mas nao",
    }
    pack["slides"][2]["fields"]["item2"] = {
        "title": "Genes",
        "text": "Setenta e nove por cento da influencia vem",
    }

    errors = validate_pack_contract(pack)

    assert any("item1.title precisa ser Mito" in error for error in errors)
    assert any("item1.text termina em frase incompleta" in error for error in errors)
    assert any("item2.title precisa ser Fato" in error for error in errors)
    assert any("item2.text termina em frase incompleta" in error for error in errors)


def test_legacy_slide_keeps_saved_copy() -> None:
    normalized = normalize_slide(
        {
            "layout": "minimal_explainer",
            "title": "Titulo antigo",
            "body": "Texto antigo preservado.",
            "fields": empty_fields(),
        },
        2,
    )

    assert normalized["layoutId"] == "explainer"
    assert normalized["fields"]["headline"] == "Titulo antigo"
    assert normalized["fields"]["body"] == "Texto antigo preservado."


def test_repair_pack_copy_fits_layout_limits_before_validation() -> None:
    pack = sample_pack()
    pack["slides"][0]["fields"]["eyebrow"] = "Um eyebrow editorial acima do limite"
    pack["slides"][2]["fields"]["item1"]["text"] = "Este texto do fato passou do limite editorial permitido"
    pack["slides"][6]["fields"]["body"] = "Um texto de apoio muito maior do que o espaco reservado para leitura confortavel"

    repaired = repair_pack_copy(pack)

    assert validate_pack_contract(repaired) == []


def test_repair_pack_copy_removes_incomplete_tail_left_by_provider() -> None:
    pack = sample_pack()
    pack["slides"][1]["fields"]["body"] = "O contexto depende do ambiente, mas não"
    pack["slides"][5]["fields"]["quote"] = "A melhor decisão para cada pessoa pode"

    repaired = repair_pack_copy(pack)

    assert repaired["slides"][1]["fields"]["body"] == "O contexto depende do ambiente"
    assert repaired["slides"][5]["fields"]["quote"] == "A melhor decisão para cada pessoa"
    assert validate_pack_contract(repaired) == []


def test_repair_pack_copy_fills_missing_required_scalar_fields() -> None:
    pack = sample_pack()
    pack["slides"][6]["fields"]["cta"] = ""
    pack["slides"][6]["fields"]["disclaimer"] = ""
    pack["slides"][5]["fields"]["caption"] = ""

    repaired = repair_pack_copy(pack)

    assert repaired["slides"][6]["fields"]["cta"] == MEDICAL_DEFAULT_SAFE_CTA
    assert repaired["slides"][6]["fields"]["disclaimer"] == MEDICAL_EDUCATIONAL_DISCLAIMER
    assert repaired["slides"][5]["fields"]["caption"] == "Dr. Guilherme Martins"
    assert validate_pack_contract(repaired) == []
    assert len(repaired["slides"][0]["fields"]["eyebrow"]) <= 22
    assert len(repaired["slides"][2]["fields"]["item1"]["text"]) <= LAYOUT_SPECS["myth_fact"]["item_max"]["text"]
    assert len(repaired["slides"][6]["fields"]["body"]) <= 70


def test_repair_pack_copy_locks_professional_identification_in_caption_and_last_slide() -> None:
    pack = sample_pack()
    pack["caption"] = "Copy editorial para publicação."
    pack["slides"][6]["fields"]["footer"] = "Outro rodape"

    repaired = repair_pack_copy(pack)
    final_slide = repaired["slides"][6]
    final_html = slide_html(final_slide, index=7, total=7)

    assert repaired["caption"].endswith(MEDICAL_PUBLICATION_NOTICE)
    assert final_slide["fields"]["footer"] == MEDICAL_PROFESSIONAL_IDENTIFICATION
    assert MEDICAL_EDUCATIONAL_DISCLAIMER in final_html
    assert MEDICAL_PROFESSIONAL_IDENTIFICATION in final_html
    assert validate_pack_contract(repaired) == []


def test_repair_pack_copy_migrates_legacy_six_slide_pack_without_ai() -> None:
    pack = sample_pack()
    pack["slides"] = [
        pack["slides"][0],
        pack["slides"][1],
        pack["slides"][4],
        pack["slides"][3],
        pack["slides"][5],
        pack["slides"][6],
    ]
    pack["carousel"] = pack["slides"]
    pack["schemaVersion"] = "institute-carousel-v1"

    repaired = repair_pack_copy(pack)

    assert len(repaired["slides"]) == 7
    assert repaired["schemaVersion"] == PACK_SCHEMA_VERSION
    assert repaired["slides"][3]["layoutId"] == "explainer"
    assert repaired["slides"][4]["layoutId"] == "explainer"
    assert repaired["slides"][6]["layoutId"] == "cta_photo"
    assert validate_pack_contract(repaired) == []
    assert pack_slides({"slides": [], "carousel": repaired["carousel"]}) == repaired["carousel"]


def test_repair_pack_copy_recovers_already_migrated_pack_without_explainer() -> None:
    pack = sample_pack()
    pack["slides"][3]["layoutId"] = "big_statement"
    pack["slides"][3]["layout"] = "big_statement"
    pack["carousel"] = pack["slides"]

    repaired = repair_pack_copy(pack)

    assert repaired["slides"][3]["layoutId"] == "explainer"
    assert repaired["slides"][3]["fields"]["body"]
    assert validate_pack_contract(repaired) == []


def test_repair_pack_copy_fills_missing_myth_fact_items() -> None:
    pack = sample_pack()
    pack["slides"][2]["layoutId"] = "do_dont"
    pack["slides"][4]["layoutId"] = "myth_fact"
    pack["slides"][4]["fields"]["item1"] = {"title": "", "text": ""}
    pack["slides"][4]["fields"]["item2"] = {"title": "", "text": ""}
    pack["slides"][4]["fields"]["body"] = "Cada indicação precisa de estudo e avaliação individual."

    repaired = repair_pack_copy(pack)

    assert validate_pack_contract(repaired) == []
    assert repaired["slides"][4]["fields"]["item1"]["title"] == "Mito"
    assert repaired["slides"][4]["fields"]["item2"]["title"] == "Fato"
    assert len(repaired["slides"][4]["fields"]["item2"]["text"]) <= LAYOUT_SPECS["myth_fact"]["item_max"]["text"]


def test_slide_html_embeds_brand_fonts_and_copy() -> None:
    slide = sample_pack()["slides"][0]

    html = slide_html(slide, index=1, total=6)

    assert "@font-face" in html
    assert "Instrument Serif" in html
    assert "Instituto" in html
    assert "Por que o peso volta depois da dieta" in html


def test_slide_html_applies_modernist_theme_without_changing_copy() -> None:
    slide = sample_pack()["slides"][0]

    html = slide_html(
        slide,
        index=1,
        total=7,
        family="storytelling",
        theme_id="modernist-red",
    )

    assert "data-family='storytelling'" in html
    assert "data-theme='modernist-red'" in html
    assert "#C8392B" in html
    assert "#12B2A6" not in html
    assert "Por que o peso volta depois da dieta" in html


def test_every_closed_layout_has_a_renderer() -> None:
    fields = _fields(
        eyebrow="Tema",
        headline="Mensagem simples",
        body="Uma explicacao curta.",
        statistic="3",
        item1={"title": "Um", "text": "Primeiro ponto"},
        item2={"title": "Dois", "text": "Segundo ponto"},
        item3={"title": "Tres", "text": "Terceiro ponto"},
        quote="Uma orientacao clara.",
        cta="Salve este guia",
        footer="Continue lendo",
        caption="Endocrinologia e Metabologia",
        disclaimer="Conteudo educativo.",
        photoId="seated-front",
    )

    rendered = [
        slide_html({"layoutId": layout, "variant": "light", "fields": fields}, index=1, total=6)
        for layout in PACK_LAYOUTS
    ]

    assert len(rendered) == 12
    assert all(layout.replace("_", "-") in html for layout, html in zip(PACK_LAYOUTS, rendered))


def test_contract_requires_explainer_context_in_middle() -> None:
    pack = sample_pack()
    pack["slides"][3]["layoutId"] = "big_statement"

    errors = validate_pack_contract(pack)

    assert any("explainer" in error for error in errors)
