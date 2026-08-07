from __future__ import annotations

from api.pack_design import (
    PACK_LAYOUTS,
    PACK_SCHEMA_VERSION,
    empty_fields,
    normalize_slide,
    validate_pack_contract,
)
from api.slides import slide_html


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
                footer="Entenda em seis telas",
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
                item1={"title": "Mito", "text": "Voltar a engordar e falta de disciplina"},
                item2={"title": "Fato", "text": "O corpo tenta recuperar o peso perdido"},
                body="Biologia e ambiente tambem influenciam o resultado.",
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
                cta="Salve para rever",
                disclaimer="Conteudo educativo. Nao substitui avaliacao medica.",
                photoId="seated-lean",
            ),
        },
    ]
    return {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "caption": "Peso nao depende de uma unica escolha. Observe o contexto e procure cuidado individual.",
        "hashtags": ["#saudemetabolica", "#educacaoemsaude"],
        "slides": slides,
        "carousel": slides,
    }


def test_sample_pack_follows_closed_contract() -> None:
    assert validate_pack_contract(sample_pack()) == []


def test_contract_rejects_extra_slide_and_long_headline() -> None:
    pack = sample_pack()
    pack["slides"] = [*pack["slides"], pack["slides"][-1]]
    pack["slides"][0]["fields"]["headline"] = "Uma manchete longa demais para caber com leitura simples no primeiro slide"

    errors = validate_pack_contract(pack)

    assert any("7 itens" in error for error in errors)
    assert any("headline" in error for error in errors)


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


def test_slide_html_embeds_brand_fonts_and_copy() -> None:
    slide = sample_pack()["slides"][0]

    html = slide_html(slide, index=1, total=6)

    assert "@font-face" in html
    assert "Instrument Serif" in html
    assert "Instituto" in html
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
