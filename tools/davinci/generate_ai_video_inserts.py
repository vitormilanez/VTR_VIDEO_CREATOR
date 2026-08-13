#!/usr/bin/env python3
"""Generate native Fusion title templates for AI Video Creator."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "exports" / "davinci-inserts" / "settings"
DRFX_PATH = OUTPUT_DIR.parent / "AI Video Creator Inserts.drfx"
STANDARD_FUSION_DIR = (
    Path.home()
    / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion"
)
APP_STORE_FUSION_DIRS = (
    Path.home()
    / "Library/Containers/com.blackmagic-design.DaVinciResolveLite/Data/Library/Application Support/Fusion",
    Path.home()
    / "Library/Containers/com.blackmagic-design.DaVinciResolveStudio/Data/Library/Application Support/Fusion",
)


def fusion_user_dir() -> Path:
    """Return Fusion's active user-data root, including App Store sandboxes."""
    for candidate in APP_STORE_FUSION_DIRS:
        if candidate.is_dir():
            return candidate
    return STANDARD_FUSION_DIR


def is_app_store_fusion_dir(path: Path) -> bool:
    return path in APP_STORE_FUSION_DIRS


def install_dir() -> Path:
    return fusion_user_dir() / "Templates/Edit/Titles/AI Video Creator Inserts"


@dataclass(frozen=True)
class Insert:
    filename: str
    macro: str
    kind: str
    title: str
    subtitle: str = ""
    badge: str = ""
    footnote: str = ""
    value: str = ""
    duration: int = 120
    position: tuple[float, float] = (0.22, 0.50)


INSERTS = (
    Insert(
        "AI VC - Headline.setting",
        "AIVC_Headline",
        "headline",
        "A próxima geração do tratamento da obesidade?",
        duration=90,
        position=(0.22, 0.45),
    ),
    Insert(
        "AI VC - Dual Mechanism.setting",
        "AIVC_DualMechanism",
        "dual",
        "AMYCRETIN",
        "GLP-1",
        "AMILINA",
        "Mecanismo dual",
        duration=120,
        position=(0.50, 0.82),
    ),
    Insert(
        "AI VC - Biological Effects.setting",
        "AIVC_BiologicalEffects",
        "effects",
        "FOME ↓",
        "SACIEDADE ↑",
        "ESVAZIAMENTO GÁSTRICO ↓",
        duration=105,
        position=(0.77, 0.48),
    ),
    Insert(
        "AI VC - Big Number Oral.setting",
        "AIVC_BigNumberOral",
        "number",
        "Redução de peso",
        "12 semanas",
        "FORMULAÇÃO ORAL",
        "Estudo clínico inicial",
        "≈13%",
        duration=120,
        position=(0.22, 0.52),
    ),
    Insert(
        "AI VC - Big Number Injectable.setting",
        "AIVC_BigNumberInjectable",
        "number",
        "Redução de peso",
        "36 semanas",
        "FORMULAÇÃO INJETÁVEL",
        "Estudo clínico inicial",
        "24,3%",
        duration=120,
        position=(0.78, 0.52),
    ),
    Insert(
        "AI VC - Clinical Status.setting",
        "AIVC_ClinicalStatus",
        "status",
        "AMYCRETIN",
        "EM DESENVOLVIMENTO CLÍNICO",
        "STATUS",
        "Ainda não disponível comercialmente",
        duration=120,
        position=(0.50, 0.82),
    ),
    Insert(
        "AI VC - Newspaper Sidebar.setting",
        "AIVC_NewspaperSidebar",
        "newspaper",
        "A nova era dos tratamentos",
        "O que muda para pacientes e profissionais de saúde.",
        "SAÚDE • EDIÇÃO ESPECIAL",
        "Atualize título, seção e data no Inspector",
        duration=150,
        position=(0.20, 0.52),
    ),
    Insert(
        "AI VC - Kinetic Text.setting",
        "AIVC_KineticText",
        "kinetic",
        "Uma mensagem que prende a atenção",
        "Use uma frase curta para completar a ideia.",
        "EM DESTAQUE",
        "Texto, cor e posição editáveis",
        duration=135,
        position=(0.50, 0.78),
    ),
    Insert(
        "AI VC - 5 Info Lines.setting",
        "AIVC_FiveInfoLines",
        "lines",
        "INFORMAÇÃO 01",
        "INFORMAÇÃO 02",
        "INFORMAÇÃO 03",
        "INFORMAÇÃO 04",
        "INFORMAÇÃO 05",
        duration=150,
        position=(0.77, 0.50),
    ),
)


def q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def text_node(
    name: str,
    value: str,
    size: float,
    center: tuple[float, float],
    color: tuple[float, float, float, float] = (0.96, 0.98, 1.0, 1.0),
    style: str = "Demi Bold",
    font: str = "Avenir Next",
) -> str:
    x, y = center
    rgba = ", ".join(str(part) for part in color)
    return f'''{name} = TextPlus {{
    Inputs = {{
        Width = Input {{ Value = 1920 }},
        Height = Input {{ Value = 1080 }},
        UseFrameFormatSettings = Input {{ Value = 1 }},
        StyledText = Input {{ Value = {q(value)} }},
        Font = Input {{ Value = {q(font)} }},
        Style = Input {{ Value = {q(style)} }},
        Size = Input {{ Value = {size} }},
        Center = Input {{ Value = {{ {x}, {y} }} }},
        FontColor = Input {{ Value = {{ {rgba} }} }},
        VerticalJustificationNew = Input {{ Value = 3 }},
        HorizontalJustificationNew = Input {{ Value = 3 }}
    }}
}},'''


def rectangle(name: str, center: tuple[float, float], width: float, height: float, radius: float) -> str:
    x, y = center
    return f'''{name} = RectangleMask {{
    Inputs = {{
        UseFrameFormatSettings = Input {{ Value = 1 }},
        Center = Input {{ Value = {{ {x}, {y} }} }},
        Width = Input {{ Value = {width} }},
        Height = Input {{ Value = {height} }},
        CornerRadius = Input {{ Value = {radius} }},
        Solid = Input {{ Value = 1 }}
    }}
}},'''


def background(
    name: str,
    mask: str | None,
    color: tuple[float, float, float, float],
    alpha: float,
    alpha_expression: str | None = None,
) -> str:
    red, green, blue, _color_alpha = color
    mask_input = (
        f'EffectMask = Input {{ SourceOp = "{mask}", Source = "Mask" }},\n        '
        if mask
        else ""
    )
    alpha_input = (
        f'TopLeftAlpha = Input {{ Value = {alpha}, Expression = "{alpha_expression}" }}'
        if alpha_expression
        else f"TopLeftAlpha = Input {{ Value = {alpha} }}"
    )
    return f'''{name} = Background {{
    Inputs = {{
        {mask_input}Width = Input {{ Value = 1920 }},
        Height = Input {{ Value = 1080 }},
        UseFrameFormatSettings = Input {{ Value = 1 }},
        TopLeftRed = Input {{ Value = {red} }},
        TopLeftGreen = Input {{ Value = {green} }},
        TopLeftBlue = Input {{ Value = {blue} }},
        {alpha_input}
    }}
}},'''


def merge(name: str, base: str, foreground: str, blend: str = "1") -> str:
    blend_input = (
        f'Input {{ SourceOp = "{blend}", Source = "Value" }}'
        if blend != "1"
        else "Input { Value = 1 }"
    )
    return f'''{name} = Merge {{
    Inputs = {{
        Background = Input {{ SourceOp = "{base}", Source = "Output" }},
        Foreground = Input {{ SourceOp = "{foreground}", Source = "Output" }},
        Blend = {blend_input}
    }}
}},'''


def spline(name: str, keyframes: tuple[tuple[int, float], ...]) -> str:
    keys = ",\n        ".join(f"[{frame}] = {{ {value} }}" for frame, value in keyframes)
    return f'''{name} = BezierSpline {{
    SplineColor = {{ Red = 47, Green = 194, Blue = 192 }},
    KeyFrames = {{
        {keys}
    }}
}},'''


def chain(nodes: list[tuple[str, str]], start: str = "Transparent") -> tuple[str, str]:
    chunks: list[str] = []
    current = start
    for index, (node, blend) in enumerate(nodes, start=1):
        merge_name = f"LayerMerge{index}"
        chunks.append(merge(merge_name, current, node, blend))
        current = merge_name
    return "\n".join(chunks), current


def transparent() -> str:
    return background("Transparent", None, (0, 0, 0, 0), 0)


def common_finish(insert: Insert, content: str, slide_start: float = 0.5) -> str:
    fade_out = max(45, insert.duration - 15)
    x, y = insert.position
    return "\n".join(
        (
            spline("MasterFade", ((0, 0), (12, 1), (fade_out, 1), (insert.duration, 0))),
            spline("SlideX", ((0, slide_start), (16, 0.5), (insert.duration, 0.5))),
            merge("AnimationMerge", "Transparent", content, "MasterFade"),
            '''OpacityMerge = Merge {
    Inputs = {
        Background = Input { SourceOp = "Transparent", Source = "Output" },
        Foreground = Input { SourceOp = "AnimationMerge", Source = "Output" },
        Blend = Input { Value = 1 }
    }
},''',
            '''SlideTransform = Transform {
    Inputs = {
        Center = Input { Expression = "Point(SlideX.Value, 0.5)" },
        Input = Input { SourceOp = "OpacityMerge", Source = "Output" }
    }
},''',
            f'''MasterTransform = Transform {{
    Inputs = {{
        Center = Input {{ Value = {{ {x}, {y} }} }},
        Size = Input {{ Value = 1 }},
        Input = Input {{ SourceOp = "SlideTransform", Source = "Output" }}
    }}
}},''',
            '''AnimationSpeed = TimeSpeed {
    Inputs = {
        Speed = Input { Value = 1 },
        Input = Input { SourceOp = "MasterTransform", Source = "Output" }
    }
},''',
        )
    )


def headline_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    panel = rectangle("PanelMask", (0.5, 0.5), 0.42, 0.28, 0.04)
    accent = rectangle("AccentMask", (0.30, 0.5), 0.012, 0.18, 0.006)
    chunks = [
        transparent(),
        panel,
        background("PanelBG", "PanelMask", (0.035, 0.08, 0.13, 1), 0.88),
        accent,
        background("AccentBG", "AccentMask", (0.18, 0.78, 0.74, 1), 1),
        text_node("TitleText", insert.title, 0.065, (0.52, 0.46)),
        text_node("SubtitleText", insert.subtitle, 0.031, (0.52, 0.60), (0.36, 0.83, 0.91, 1), "Medium"),
        text_node("BadgeText", insert.badge, 0.024, (0.52, 0.67), (0.96, 0.68, 0.30, 1), "Demi Bold"),
        text_node("FootnoteText", insert.footnote, 0.021, (0.52, 0.73), (0.72, 0.80, 0.84, 1), "Medium"),
    ]
    layers, content = chain(
        [("PanelBG", "1"), ("AccentBG", "1"), ("TitleText", "1"), ("SubtitleText", "1"), ("BadgeText", "1"), ("FootnoteText", "1")]
    )
    chunks.extend((layers, common_finish(insert, content, 0.39)))
    fields = {"title": "TitleText", "subtitle": "SubtitleText", "badge": "BadgeText", "footnote": "FootnoteText"}
    return "\n".join(chunks), "AnimationSpeed", fields, "PanelBG", "AccentBG"


def dual_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    chunks = [
        transparent(),
        rectangle("LeftMask", (0.23, 0.50), 0.24, 0.15, 0.04),
        rectangle("CenterMask", (0.50, 0.50), 0.30, 0.18, 0.05),
        rectangle("RightMask", (0.77, 0.50), 0.24, 0.15, 0.04),
        background(
            "LeftBG",
            "LeftMask",
            (0.035, 0.08, 0.13, 1),
            0.88,
            "CenterBG.TopLeftAlpha",
        ),
        background("CenterBG", "CenterMask", (0.06, 0.20, 0.25, 1), 0.92),
        background(
            "RightBG",
            "RightMask",
            (0.035, 0.08, 0.13, 1),
            0.88,
            "CenterBG.TopLeftAlpha",
        ),
        rectangle("AccentMask", (0.50, 0.39), 0.18, 0.008, 0.004),
        background("AccentBG", "AccentMask", (0.18, 0.78, 0.74, 1), 1),
        text_node("TitleText", insert.title, 0.052, (0.50, 0.50), style="Bold"),
        text_node("CenterHalo", insert.title, 0.058, (0.50, 0.50), (0.18, 0.78, 0.74, 1), "Bold"),
        text_node("SubtitleText", insert.subtitle, 0.038, (0.23, 0.50)),
        text_node("BadgeText", insert.badge, 0.036, (0.77, 0.50)),
        text_node("ArrowLeft", "→", 0.054, (0.365, 0.50), (0.18, 0.78, 0.74, 1)),
        text_node("ArrowRight", "←", 0.054, (0.635, 0.50), (0.18, 0.78, 0.74, 1)),
        text_node("FootnoteText", insert.footnote, 0.025, (0.50, 0.67), (0.36, 0.83, 0.91, 1), "Medium"),
        spline("CenterIn", ((0, 0), (8, 1), (insert.duration, 1))),
        spline("LeftIn", ((0, 0), (14, 0), (27, 1), (insert.duration, 1))),
        spline("RightIn", ((0, 0), (22, 0), (35, 1), (insert.duration, 1))),
        spline("ArrowIn", ((0, 0), (34, 0), (48, 1), (insert.duration, 1))),
        spline("Pulse", ((0, 0), (9, 0), (15, 0.30), (24, 0), (insert.duration, 0))),
    ]
    layers, content = chain(
        [
            ("LeftBG", "LeftIn"),
            ("RightBG", "RightIn"),
            ("CenterBG", "CenterIn"),
            ("CenterHalo", "Pulse"),
            ("TitleText", "CenterIn"),
            ("SubtitleText", "LeftIn"),
            ("BadgeText", "RightIn"),
            ("ArrowLeft", "ArrowIn"),
            ("ArrowRight", "ArrowIn"),
            ("AccentBG", "ArrowIn"),
            ("FootnoteText", "ArrowIn"),
        ]
    )
    chunks.extend((layers, common_finish(insert, content)))
    fields = {"title": "TitleText", "subtitle": "SubtitleText", "badge": "BadgeText", "footnote": "FootnoteText"}
    return "\n".join(chunks), "AnimationSpeed", fields, "CenterBG", "AccentBG"


def effects_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    chunks = [transparent()]
    positions = (0.30, 0.50, 0.70)
    names = ("TitleText", "SubtitleText", "BadgeText")
    values = (insert.title, insert.subtitle, insert.badge)
    for index, (y, name, value) in enumerate(zip(positions, names, values), start=1):
        panel_alpha_expression = "CardBG1.TopLeftAlpha" if index > 1 else None
        accent_alpha_expression = "AccentBG1.TopLeftAlpha" if index > 1 else None
        chunks.extend(
            (
                rectangle(f"CardMask{index}", (0.50, y), 0.34, 0.145, 0.04),
                background(
                    f"CardBG{index}",
                    f"CardMask{index}",
                    (0.035, 0.08, 0.13, 1),
                    0.88,
                    panel_alpha_expression,
                ),
                rectangle(f"AccentMask{index}", (0.34, y), 0.010, 0.08, 0.004),
                background(
                    f"AccentBG{index}",
                    f"AccentMask{index}",
                    (0.18, 0.78, 0.74, 1),
                    1,
                    accent_alpha_expression,
                ),
                text_node(name, value, 0.030 if index < 3 else 0.022, (0.51, y)),
                spline(f"ItemIn{index}", ((0, 0), (index * 10, 0), (index * 10 + 12, 1), (insert.duration, 1))),
            )
        )
    chunks.append(text_node("FootnoteText", insert.footnote, 0.020, (0.50, 0.81), (0.72, 0.80, 0.84, 1), "Medium"))
    layers, content = chain(
        [
            ("CardBG1", "ItemIn1"), ("AccentBG1", "ItemIn1"), ("TitleText", "ItemIn1"),
            ("CardBG2", "ItemIn2"), ("AccentBG2", "ItemIn2"), ("SubtitleText", "ItemIn2"),
            ("CardBG3", "ItemIn3"), ("AccentBG3", "ItemIn3"), ("BadgeText", "ItemIn3"),
            ("FootnoteText", "ItemIn3"),
        ]
    )
    chunks.extend((layers, common_finish(insert, content)))
    fields = {"title": "TitleText", "subtitle": "SubtitleText", "badge": "BadgeText", "footnote": "FootnoteText"}
    return "\n".join(chunks), "AnimationSpeed", fields, "CardBG1", "AccentBG1"


def number_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    chunks = [
        transparent(),
        rectangle("PanelMask", (0.50, 0.50), 0.40, 0.56, 0.05),
        background("PanelBG", "PanelMask", (0.035, 0.08, 0.13, 1), 0.90),
        rectangle("AccentMask", (0.31, 0.40), 0.010, 0.28, 0.004),
        background("AccentBG", "AccentMask", (0.18, 0.78, 0.74, 1), 1),
        text_node("ValueText", insert.value, 0.145, (0.50, 0.35), (0.18, 0.78, 0.74, 1), "Bold"),
        text_node("TitleText", insert.title, 0.047, (0.50, 0.56)),
        text_node("SubtitleText", insert.subtitle, 0.031, (0.50, 0.66), (0.36, 0.83, 0.91, 1), "Medium"),
        text_node("BadgeText", insert.badge, 0.022, (0.50, 0.75), (0.96, 0.68, 0.30, 1), "Bold"),
        text_node("FootnoteText", insert.footnote, 0.019, (0.50, 0.83), (0.72, 0.80, 0.84, 1), "Medium"),
        spline("NumberIn", ((0, 0), (8, 0), (24, 1), (insert.duration, 1))),
    ]
    layers, content = chain(
        [
            ("PanelBG", "1"), ("AccentBG", "1"), ("ValueText", "NumberIn"),
            ("TitleText", "1"), ("SubtitleText", "1"), ("BadgeText", "1"), ("FootnoteText", "1"),
        ]
    )
    chunks.extend((layers, common_finish(insert, content)))
    fields = {
        "title": "TitleText", "subtitle": "SubtitleText", "badge": "BadgeText",
        "footnote": "FootnoteText", "value": "ValueText",
    }
    return "\n".join(chunks), "AnimationSpeed", fields, "PanelBG", "AccentBG"


def status_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    chunks = [
        transparent(),
        rectangle("PanelMask", (0.50, 0.50), 0.76, 0.34, 0.05),
        background("PanelBG", "PanelMask", (0.035, 0.08, 0.13, 1), 0.90),
        rectangle("AccentMask", (0.17, 0.50), 0.012, 0.22, 0.005),
        background("AccentBG", "AccentMask", (0.96, 0.68, 0.30, 1), 1),
        text_node("TitleText", insert.title, 0.077, (0.50, 0.38), style="Bold"),
        text_node("SubtitleText", insert.subtitle, 0.030, (0.50, 0.55), (0.36, 0.83, 0.91, 1)),
        text_node("BadgeText", insert.badge, 0.022, (0.50, 0.67), (0.96, 0.68, 0.30, 1), "Bold"),
        text_node("FootnoteText", insert.footnote, 0.020, (0.50, 0.76), (0.72, 0.80, 0.84, 1), "Medium"),
    ]
    layers, content = chain(
        [("PanelBG", "1"), ("AccentBG", "1"), ("TitleText", "1"), ("SubtitleText", "1"), ("BadgeText", "1"), ("FootnoteText", "1")]
    )
    chunks.extend((layers, common_finish(insert, content)))
    fields = {"title": "TitleText", "subtitle": "SubtitleText", "badge": "BadgeText", "footnote": "FootnoteText"}
    return "\n".join(chunks), "AnimationSpeed", fields, "PanelBG", "AccentBG"


def newspaper_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    """An editorial, newspaper-like card intended to sit beside an avatar."""
    chunks = [
        transparent(),
        rectangle("PaperMask", (0.50, 0.50), 0.54, 0.72, 0.012),
        background("PaperBG", "PaperMask", (0.96, 0.94, 0.88, 1), 0.96),
        rectangle("TopRuleMask", (0.50, 0.18), 0.44, 0.008, 0.001),
        background("TopRuleBG", "TopRuleMask", (0.06, 0.08, 0.10, 1), 1),
        rectangle("AccentRuleMask", (0.27, 0.50), 0.012, 0.52, 0.002),
        background("AccentRuleBG", "AccentRuleMask", (0.05, 0.45, 0.52, 1), 1),
        rectangle("BottomRuleMask", (0.50, 0.82), 0.44, 0.004, 0.001),
        background("BottomRuleBG", "BottomRuleMask", (0.06, 0.08, 0.10, 1), 0.70),
        text_node(
            "MastheadText",
            "AI VIDEO JOURNAL",
            0.024,
            (0.50, 0.135),
            (0.05, 0.07, 0.09, 1),
            "Bold",
        ),
        text_node("BadgeText", insert.badge, 0.018, (0.52, 0.235), (0.05, 0.35, 0.42, 1), "Bold"),
        text_node(
            "TitleText",
            insert.title,
            0.050,
            (0.52, 0.405),
            (0.05, 0.06, 0.08, 1),
            "Bold",
            "Georgia",
        ),
        text_node(
            "SubtitleText",
            insert.subtitle,
            0.025,
            (0.52, 0.575),
            (0.17, 0.20, 0.23, 1),
            "Medium",
            "Georgia",
        ),
        text_node("FootnoteText", insert.footnote, 0.017, (0.52, 0.745), (0.23, 0.28, 0.30, 1), "Medium"),
        spline("PaperIn", ((0, 0), (8, 0), (20, 1), (insert.duration, 1))),
        spline("HeadlineIn", ((0, 0), (16, 0), (30, 1), (insert.duration, 1))),
        spline("CopyIn", ((0, 0), (28, 0), (42, 1), (insert.duration, 1))),
    ]
    layers, content = chain(
        [
            ("PaperBG", "PaperIn"),
            ("TopRuleBG", "PaperIn"),
            ("AccentRuleBG", "PaperIn"),
            ("BottomRuleBG", "PaperIn"),
            ("MastheadText", "PaperIn"),
            ("BadgeText", "HeadlineIn"),
            ("TitleText", "HeadlineIn"),
            ("SubtitleText", "CopyIn"),
            ("FootnoteText", "CopyIn"),
        ]
    )
    chunks.extend((layers, common_finish(insert, content, 0.34)))
    fields = {
        "title": "TitleText",
        "subtitle": "SubtitleText",
        "badge": "BadgeText",
        "footnote": "FootnoteText",
    }
    return "\n".join(chunks), "AnimationSpeed", fields, "PaperBG", "AccentRuleBG"


def kinetic_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    """A compact kinetic typography card with independently animated text layers."""
    chunks = [
        transparent(),
        rectangle("PanelMask", (0.50, 0.50), 0.76, 0.34, 0.050),
        background("PanelBG", "PanelMask", (0.025, 0.055, 0.085, 1), 0.82),
        rectangle("TagMask", (0.26, 0.315), 0.25, 0.090, 0.028),
        background("AccentBG", "TagMask", (0.05, 0.58, 0.68, 1), 1),
        rectangle("PulseMask", (0.50, 0.650), 0.54, 0.012, 0.006),
        background("PulseBG", "PulseMask", (0.14, 0.88, 0.83, 1), 1),
        text_node("BadgeText", insert.badge, 0.022, (0.26, 0.315), (0.98, 1, 1, 1), "Bold"),
        text_node("TitleText", insert.title, 0.060, (0.50, 0.465), style="Bold"),
        text_node("SubtitleText", insert.subtitle, 0.026, (0.50, 0.565), (0.66, 0.89, 0.92, 1), "Medium"),
        text_node("FootnoteText", insert.footnote, 0.019, (0.50, 0.735), (0.75, 0.83, 0.87, 1), "Medium"),
        spline("TagIn", ((0, 0), (4, 0), (12, 1), (insert.duration, 1))),
        spline("TitleIn", ((0, 0), (10, 0), (24, 1), (insert.duration, 1))),
        spline("CopyIn", ((0, 0), (22, 0), (34, 1), (insert.duration, 1))),
        spline("PulseIn", ((0, 0), (16, 0), (27, 1), (insert.duration - 20, 1), (insert.duration, 0))),
    ]
    layers, content = chain(
        [
            ("PanelBG", "TagIn"),
            ("AccentBG", "TagIn"),
            ("BadgeText", "TagIn"),
            ("TitleText", "TitleIn"),
            ("SubtitleText", "CopyIn"),
            ("PulseBG", "PulseIn"),
            ("FootnoteText", "CopyIn"),
        ]
    )
    chunks.extend((layers, common_finish(insert, content, 0.64)))
    fields = {
        "title": "TitleText",
        "subtitle": "SubtitleText",
        "badge": "BadgeText",
        "footnote": "FootnoteText",
    }
    return "\n".join(chunks), "AnimationSpeed", fields, "PanelBG", "AccentBG"


def five_info_lines_nodes(insert: Insert) -> tuple[str, str, dict[str, str], str, str]:
    """Five compact, transparent-canvas information rows for a portrait video edge."""
    chunks = [transparent()]
    values = (insert.title, insert.subtitle, insert.badge, insert.footnote, insert.value)
    fields = {
        "title": "Line1Text",
        "subtitle": "Line2Text",
        "badge": "Line3Text",
        "footnote": "Line4Text",
        "value": "Line5Text",
    }
    line_nodes: list[tuple[str, str]] = []
    for index, (y, value) in enumerate(zip((0.18, 0.34, 0.50, 0.66, 0.82), values), start=1):
        background_alpha = "LineBG1.TopLeftAlpha" if index > 1 else None
        accent_alpha = "LineAccentBG1.TopLeftAlpha" if index > 1 else None
        chunks.extend(
            (
                rectangle(f"LineMask{index}", (0.52, y), 0.76, 0.115, 0.030),
                background(
                    f"LineBG{index}",
                    f"LineMask{index}",
                    (0.025, 0.065, 0.095, 1),
                    0.86,
                    background_alpha,
                ),
                rectangle(f"LineAccentMask{index}", (0.165, y), 0.016, 0.068, 0.006),
                background(
                    f"LineAccentBG{index}",
                    f"LineAccentMask{index}",
                    (0.10, 0.80, 0.76, 1),
                    1,
                    accent_alpha,
                ),
                text_node(
                    f"LineNumber{index}",
                    f"0{index}",
                    0.021,
                    (0.235, y),
                    (0.20, 0.86, 0.82, 1),
                    "Bold",
                ),
                text_node(f"Line{index}Text", value, 0.030, (0.565, y), style="Demi Bold"),
                spline(
                    f"LineIn{index}",
                    ((0, 0), (index * 8, 0), (index * 8 + 12, 1), (insert.duration, 1)),
                ),
            )
        )
        line_nodes.extend(
            (
                (f"LineBG{index}", f"LineIn{index}"),
                (f"LineAccentBG{index}", f"LineIn{index}"),
                (f"LineNumber{index}", f"LineIn{index}"),
                (f"Line{index}Text", f"LineIn{index}"),
            )
        )
    layers, content = chain(line_nodes)
    chunks.extend((layers, common_finish(insert, content, 0.62)))
    return "\n".join(chunks), "AnimationSpeed", fields, "LineBG1", "LineAccentBG1"


def instance_input(index: int, source_op: str, source: str, name: str, default: str | float, page: str, minimum: float | None = None, maximum: float | None = None) -> str:
    default_value = q(default) if isinstance(default, str) else str(default)
    scales = ""
    if minimum is not None:
        scales += f"\n        MinScale = {minimum},"
    if maximum is not None:
        scales += f"\n        MaxScale = {maximum},"
    return f'''Input{index} = InstanceInput {{
        SourceOp = "{source_op}",
        Source = "{source}",
        Name = {q(name)},
        Default = {default_value},{scales}
        Page = {q(page)}
    }},'''


def build_setting(insert: Insert) -> str:
    builders = {
        "headline": headline_nodes,
        "dual": dual_nodes,
        "effects": effects_nodes,
        "number": number_nodes,
        "status": status_nodes,
        "newspaper": newspaper_nodes,
        "kinetic": kinetic_nodes,
        "lines": five_info_lines_nodes,
    }
    nodes, output, fields, panel, accent = builders[insert.kind](insert)
    content_labels = {
        "newspaper": {
            "title": "Headline",
            "subtitle": "Deck",
            "badge": "Section",
            "footnote": "Dateline",
        },
        "kinetic": {
            "title": "Main text",
            "subtitle": "Supporting text",
            "badge": "Highlight label",
            "footnote": "Caption",
        },
        "lines": {
            "title": "Line 1",
            "subtitle": "Line 2",
            "badge": "Line 3",
            "footnote": "Line 4",
            "value": "Line 5",
        },
    }.get(
        insert.kind,
        {
            "title": "Title",
            "subtitle": "Subtitle",
            "badge": "Badge",
            "footnote": "Footnote",
            "value": "Value",
        },
    )
    inputs = [
        instance_input(1, fields["title"], "StyledText", content_labels["title"], insert.title, "Content"),
        instance_input(2, fields["subtitle"], "StyledText", content_labels["subtitle"], insert.subtitle, "Content"),
        instance_input(3, fields["badge"], "StyledText", content_labels["badge"], insert.badge, "Content"),
        instance_input(4, fields["footnote"], "StyledText", content_labels["footnote"], insert.footnote, "Content"),
    ]
    next_index = 5
    if "value" in fields:
        inputs.append(
            instance_input(
                next_index,
                fields["value"],
                "StyledText",
                content_labels["value"],
                insert.value,
                "Content",
            )
        )
        next_index += 1
    inputs.extend(
        (
            instance_input(next_index, "MasterTransform", "Center", "Position", "", "Layout"),
            instance_input(next_index + 1, "MasterTransform", "Size", "Scale", 1, "Layout", 0.5, 1.5),
            instance_input(next_index + 2, "OpacityMerge", "Blend", "Opacity", 1, "Layout", 0, 1),
            instance_input(next_index + 3, "AnimationSpeed", "Speed", "Animation Speed", 1, "Animation", 0.25, 2),
            instance_input(
                next_index + 4,
                accent,
                "TopLeftAlpha",
                "Accent intensity",
                1,
                "Style",
                0,
                1.5,
            ),
            instance_input(
                next_index + 5,
                panel,
                "TopLeftAlpha",
                "Background opacity",
                0.88,
                "Style",
                0,
                1,
            ),
        )
    )
    # A point control takes its default from the source tool; an empty string
    # would otherwise be serialized as a text default.
    inputs[-6] = f'''Input{next_index} = InstanceInput {{
        SourceOp = "MasterTransform",
        Source = "Center",
        Name = "Position",
        Page = "Layout"
    }},'''
    inputs_text = "\n".join(inputs)
    indented_nodes = "\n".join("                " + line for line in nodes.splitlines())
    indented_inputs = "\n".join("                " + line for line in inputs_text.splitlines())
    return f'''{{
    Tools = ordered() {{
        {insert.macro} = MacroOperator {{
            Inputs = ordered() {{
{indented_inputs}
            }},
            Outputs = {{
                MainOutput1 = InstanceOutput {{
                    SourceOp = "{output}",
                    Source = "Output"
                }}
            }},
            ViewInfo = GroupInfo {{ Pos = {{ 0, 0 }} }},
            Tools = ordered() {{
{indented_nodes}
            }}
        }}
    }},
    ActiveTool = "{insert.macro}"
}}
'''


def generate() -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for insert in INSERTS:
        path = OUTPUT_DIR / insert.filename
        path.write_text(build_setting(insert), encoding="utf-8")
        paths.append(path)
    manifest = OUTPUT_DIR.parent / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": "ai-video-creator-fusion-inserts-v1",
                "format": "Fusion .setting title templates",
                "target": "1080x1920 portrait",
                "templates": [
                    {
                        "file": item.filename,
                        "type": item.kind,
                        "durationFramesAt30fps": item.duration,
                        "defaultPosition": list(item.position),
                    }
                    for item in INSERTS
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(DRFX_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(
                path,
                arcname=f"Edit/Titles/AI Video Creator Inserts/{path.name}",
            )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    paths = generate()
    if args.install:
        fusion_root = fusion_user_dir()
        if is_app_store_fusion_dir(fusion_root):
            template_root = fusion_root / "Templates"
            template_root.mkdir(parents=True, exist_ok=True)
            unpacked_target = install_dir()
            if unpacked_target.is_dir():
                shutil.rmtree(unpacked_target)
            installed_package = template_root / DRFX_PATH.name
            shutil.copy2(DRFX_PATH, installed_package)
            print(f"Installed {len(paths)} titles in {installed_package}")
        else:
            target = install_dir()
            target.mkdir(parents=True, exist_ok=True)
            for path in paths:
                shutil.copy2(path, target / path.name)
            print(f"Installed {len(paths)} titles in {target}")
    else:
        print(f"Generated {len(paths)} titles in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
