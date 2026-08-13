#!/usr/bin/env python3
"""Build the first native Fusion Title from the Claude Amycretin reference.

The title is deliberately self-contained: every Background is masked and the
base canvas has alpha 0.  It is therefore safe to layer over a V1 video.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = ROOT / "exports" / "davinci-claude-inserts"
SETTINGS_DIR = EXPORT_ROOT / "settings"
SETTING_NAME = "AI VC - Claude Pilha de Cinco.setting"
PACKAGE_NAME = "AI VC - Claude Pilha de Cinco.drfx"

APP_STORE_FUSION_ROOTS = (
    Path.home()
    / "Library/Containers/com.blackmagic-design.DaVinciResolveLite/Data/Library/Application Support/Fusion",
    Path.home()
    / "Library/Containers/com.blackmagic-design.DaVinciResolveStudio/Data/Library/Application Support/Fusion",
)
STANDARD_FUSION_ROOT = (
    Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion"
)

SOFT_WHITE = (0.9333, 0.9569, 0.9608)
MIDNIGHT_GLASS = (0.0314, 0.0941, 0.1098)
CYAN = (0.4353, 0.8902, 0.8235)
AMBER = (1.0, 0.7216, 0.3020)
MUTED = (0.64, 0.69, 0.70)

ROWS = (
    ("01", "GLP-1 — sinal de saciedade", CYAN, SOFT_WHITE, SOFT_WHITE, 0.14),
    ("02", "Amilina — controle da fome", CYAN, SOFT_WHITE, SOFT_WHITE, 0.14),
    ("03", "Esvaziamento gástrico mais lento", CYAN, SOFT_WHITE, SOFT_WHITE, 0.14),
    ("04", "Oral: ~13% em 12 semanas", MUTED, (0.72, 0.75, 0.76), SOFT_WHITE, 0.14),
    ("05", "Injetável: 24,3% em 36 semanas", AMBER, SOFT_WHITE, AMBER, 0.50),
)


def q(value: str) -> str:
    """Return a Fusion-compatible quoted string."""
    return json.dumps(value, ensure_ascii=False)


def fusion_root() -> Path:
    for candidate in APP_STORE_FUSION_ROOTS:
        if candidate.is_dir():
            return candidate
    return STANDARD_FUSION_ROOT


def rect(name: str, x: float, y: float, width: float, height: float) -> str:
    return f'''{name} = RectangleMask {{
    Inputs = {{
        UseFrameFormatSettings = Input {{ Value = 1 }},
        Center = Input {{ Value = {{ {x:.6f}, {y:.6f} }} }},
        Width = Input {{ Value = {width:.6f} }},
        Height = Input {{ Value = {height:.6f} }},
        CornerRadius = Input {{ Value = 0 }},
        Solid = Input {{ Value = 1 }}
    }}
}},'''


def bg(
    name: str,
    mask: str | None,
    color: tuple[float, float, float],
    alpha: float,
    expression: str | None = None,
) -> str:
    mask_line = (
        f'EffectMask = Input {{ SourceOp = "{mask}", Source = "Mask" }},\n        '
        if mask
        else ""
    )
    alpha_line = (
        f'TopLeftAlpha = Input {{ Value = {alpha:.6f}, Expression = "{expression}" }}'
        if expression
        else f"TopLeftAlpha = Input {{ Value = {alpha:.6f} }}"
    )
    red, green, blue = color
    return f'''{name} = Background {{
    Inputs = {{
        {mask_line}UseFrameFormatSettings = Input {{ Value = 1 }},
        TopLeftRed = Input {{ Value = {red:.6f} }},
        TopLeftGreen = Input {{ Value = {green:.6f} }},
        TopLeftBlue = Input {{ Value = {blue:.6f} }},
        {alpha_line}
    }}
}},'''


def text(
    name: str,
    value: str,
    x: float,
    y: float,
    size: float,
    color: tuple[float, float, float],
    style: str,
) -> str:
    red, green, blue = color
    return f'''{name} = TextPlus {{
    Inputs = {{
        UseFrameFormatSettings = Input {{ Value = 1 }},
        StyledText = Input {{ Value = {q(value)} }},
        Font = Input {{ Value = "Avenir Next" }},
        Style = Input {{ Value = {q(style)} }},
        Size = Input {{ Value = {size:.6f} }},
        Center = Input {{ Value = {{ {x:.6f}, {y:.6f} }} }},
        Red1 = Input {{ Value = {red:.6f} }},
        Green1 = Input {{ Value = {green:.6f} }},
        Blue1 = Input {{ Value = {blue:.6f} }},
        VerticalJustificationNew = Input {{ Value = 3 }},
        HorizontalJustificationNew = Input {{ Value = 3 }}
    }}
}},'''


def merge(name: str, background: str, foreground: str, blend: str = "1") -> str:
    blend_line = (
        f'Input {{ SourceOp = "{blend}", Source = "Value" }}'
        if blend != "1"
        else "Input { Value = 1 }"
    )
    return f'''{name} = Merge {{
    Inputs = {{
        Background = Input {{ SourceOp = "{background}", Source = "Output" }},
        Foreground = Input {{ SourceOp = "{foreground}", Source = "Output" }},
        Blend = {blend_line}
    }}
}},'''


def spline(name: str, start: int, end: int) -> str:
    return f'''{name} = BezierSpline {{
    SplineColor = {{ Red = 111, Green = 227, Blue = 210 }},
    KeyFrames = {{
        [0] = {{ 0 }},
        [{start}] = {{ 0 }},
        [{end}] = {{ 1 }},
        [180] = {{ 1 }}
    }}
}},'''


def row_nodes(index: int, row: tuple[str, str, tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float], y: float) -> tuple[list[str], str]:
    number, label, number_color, body_color, border_color, border_alpha = row
    outer_mask = f"Row{index}OuterMask"
    inner_mask = f"Row{index}InnerMask"
    stripe_mask = f"Row{index}StripeMask"
    outer = f"Row{index}Border"
    fill = f"Row{index}Fill"
    stripe = f"Row{index}Stripe"
    number_text = f"Row{index}Number"
    body_text = f"Row{index}Text"
    reveal = f"Row{index}Reveal"

    # This places a 660 px-wide column 90 px from the right edge in 1080x1920.
    x = 0.611111
    outer_width = 0.611111
    outer_height = 0.067708
    inner_width = 0.604630
    inner_height = 0.064063
    left_edge = x - outer_width / 2
    number_x = left_edge + 0.046
    body_x = left_edge + 0.300

    fill_expression = "Row1Fill.TopLeftAlpha" if index > 1 else None
    stripe_expression = "Row1Stripe.TopLeftAlpha" if index > 1 else None
    nodes = [
        rect(outer_mask, x, y, outer_width, outer_height),
        rect(inner_mask, x + 0.0017, y, inner_width, inner_height),
        rect(stripe_mask, left_edge + 0.0030, y, 0.005556, inner_height),
        bg(outer, outer_mask, border_color, border_alpha),
        bg(fill, inner_mask, MIDNIGHT_GLASS, 0.55, fill_expression),
        bg(stripe, stripe_mask, number_color, 1.0, stripe_expression),
        text(number_text, number, number_x, y, 0.028, number_color, "Bold"),
        text(body_text, label, body_x, y, 0.030, body_color, "Demi Bold"),
        spline(reveal, (index - 1) * 3, 12 + (index - 1) * 3),
        merge(f"Row{index}Merge1", "Transparent", outer),
        merge(f"Row{index}Merge2", f"Row{index}Merge1", fill),
        merge(f"Row{index}Merge3", f"Row{index}Merge2", stripe),
        merge(f"Row{index}Merge4", f"Row{index}Merge3", number_text),
        merge(f"Row{index}Content", f"Row{index}Merge4", body_text),
    ]
    return nodes, reveal


def instance_input(
    key: str,
    source_op: str,
    source: str,
    name: str,
    page: str,
    default: float | str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str:
    lines = [
        f"{key} = InstanceInput {{",
        f'    SourceOp = "{source_op}",',
        f'    Source = "{source}",',
        f"    Name = {q(name)},",
    ]
    if default is not None:
        rendered_default = q(default) if isinstance(default, str) else str(default)
        lines.append(f"    Default = {rendered_default},")
    if minimum is not None:
        lines.append(f"    MinScale = {minimum},")
    if maximum is not None:
        lines.append(f"    MaxScale = {maximum},")
    lines.extend((f"    Page = {q(page)}", "},"))
    return "\n".join(lines)


def build_setting() -> str:
    nodes = [bg("Transparent", None, (0, 0, 0), 0.0)]
    current = "Transparent"
    for index, row in enumerate(ROWS, start=1):
        row_nodes_list, reveal = row_nodes(index, row, 0.255 + (index - 1) * 0.080)
        nodes.extend(row_nodes_list)
        next_merge = f"RowsMerge{index}"
        nodes.append(merge(next_merge, current, f"Row{index}Content", reveal))
        current = next_merge

    nodes.extend(
        (
            '''MasterTransform = Transform {
    Inputs = {
        Center = Input { Value = { 0.5, 0.5 } },
        Size = Input { Value = 1 },
        Input = Input { SourceOp = "RowsMerge5", Source = "Output" }
    }
},''',
            '''MasterOpacity = Merge {
    Inputs = {
        Background = Input { SourceOp = "Transparent", Source = "Output" },
        Foreground = Input { SourceOp = "MasterTransform", Source = "Output" },
        Blend = Input { Value = 1 }
    }
},''',
            '''AnimationSpeed = TimeSpeed {
    Inputs = {
        Speed = Input { Value = 1 },
        Input = Input { SourceOp = "MasterOpacity", Source = "Output" }
    }
},''',
            '''MediaOut1 = MediaOut {
    Inputs = {
        Index = Input { Value = "0" },
        Input = Input { SourceOp = "AnimationSpeed", Source = "Output" }
    }
},''',
        )
    )

    inspector = []
    input_index = 1
    for index, row in enumerate(ROWS, start=1):
        inspector.append(
            instance_input(
                f"Input{input_index}",
                f"Row{index}Number",
                "StyledText",
                f"Número {index}",
                "Content",
                row[0],
            )
        )
        input_index += 1
        inspector.append(
            instance_input(
                f"Input{input_index}",
                f"Row{index}Text",
                "StyledText",
                f"Linha {index}",
                "Content",
                row[1],
            )
        )
        input_index += 1
    inspector.extend(
        (
            instance_input(
                f"Input{input_index}", "MasterTransform", "Center", "Posição", "Layout"
            ),
            instance_input(
                f"Input{input_index + 1}",
                "MasterTransform",
                "Size",
                "Escala",
                "Layout",
                1.0,
                0.5,
                1.5,
            ),
            instance_input(
                f"Input{input_index + 2}",
                "AnimationSpeed",
                "Speed",
                "Velocidade de entrada",
                "Animation",
                1.0,
                0.25,
                2.0,
            ),
            instance_input(
                f"Input{input_index + 3}",
                "Row1Fill",
                "TopLeftAlpha",
                "Opacidade do vidro",
                "Style",
                0.55,
                0.0,
                0.9,
            ),
            instance_input(
                f"Input{input_index + 4}",
                "Row1Stripe",
                "TopLeftAlpha",
                "Intensidade do acento",
                "Style",
                1.0,
                0.0,
                1.0,
            ),
            instance_input(
                f"Input{input_index + 5}",
                "MasterOpacity",
                "Blend",
                "Opacidade geral",
                "Configuração",
                1.0,
                0.0,
                1.0,
            ),
        )
    )

    indented_nodes = "\n".join("                " + line for line in "\n".join(nodes).splitlines())
    indented_inputs = "\n".join("                " + line for line in "\n".join(inspector).splitlines())
    return f'''{{
    Tools = ordered() {{
        AIVC_ClaudeFiveStack = MacroOperator {{
            Inputs = ordered() {{
{indented_inputs}
            }},
            Outputs = {{
                MainOutput1 = InstanceOutput {{
                    SourceOp = "MediaOut1",
                    Source = "Output"
                }}
            }},
            ViewInfo = GroupInfo {{ Pos = {{ 0, 0 }} }},
            Tools = ordered() {{
{indented_nodes}
            }}
        }}
    }},
    ActiveTool = "AIVC_ClaudeFiveStack"
}}
'''


def generate() -> tuple[Path, Path]:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    setting_path = SETTINGS_DIR / SETTING_NAME
    package_path = EXPORT_ROOT / PACKAGE_NAME
    setting_path.write_text(build_setting(), encoding="utf-8")
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(
            setting_path,
            arcname=f"Edit/Titles/AI Video Creator Claude/{SETTING_NAME}",
        )
    return setting_path, package_path


def install(setting_path: Path) -> Path:
    target = fusion_root() / "Templates/Edit/Titles/AI Video Creator Claude"
    target.mkdir(parents=True, exist_ok=True)
    installed = target / SETTING_NAME
    shutil.copy2(setting_path, installed)
    return installed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    setting_path, package_path = generate()
    print(f"Generated {setting_path}")
    print(f"Packaged {package_path}")
    if args.install:
        print(f"Installed {install(setting_path)}")


if __name__ == "__main__":
    main()
