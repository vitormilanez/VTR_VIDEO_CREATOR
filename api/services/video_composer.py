"""Compositor local de cenas, Video Slides, overlays e legendas.

O compositor trabalha somente com arquivos locais. Cada cena é normalizada
para o mesmo canvas e concatenada em ordem com corte seco; portanto, trocar o
Avatar Look só pode acontecer entre dois arquivos de cena.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
import html
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30


@dataclass(frozen=True)
class CompositionScene:
    scene_id: str
    video_path: Path
    slide_path: Path | None = None
    slide_duration_seconds: float = 1.5
    overlay_paths: tuple[Path, ...] = ()
    captions_path: Path | None = None


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def _srt_seconds(value: str) -> float:
    hours, minutes, seconds, milliseconds = re.split(r"[:,]", value.strip())
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def _srt_cues(path: Path) -> list[tuple[float, float, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    cues: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n")):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        text = "\\n".join(lines[2:])
        cues.append((_srt_seconds(start_raw), _srt_seconds(end_raw), text))
    return cues


def _caption_image(text: str, destination: Path) -> None:
    """Cria uma camada PNG transparente sem depender de PIL ou libass."""
    from playwright.sync_api import sync_playwright

    safe_text = html.escape(text).replace("\\n", "<br>")
    document = f"""<!doctype html><html><head><meta charset='utf-8'><style>
    * {{ box-sizing:border-box }} html,body {{ margin:0; width:1080px; height:1920px; background:transparent; overflow:hidden }}
    body {{ display:flex; align-items:flex-end; justify-content:center; padding:0 100px 250px; font-family:Arial,sans-serif }}
    .caption {{ max-width:880px; padding:18px 28px; color:#fff; background:rgba(0,0,0,.68); border-radius:12px; font-size:54px; font-weight:700; line-height:1.12; text-align:center; text-transform:uppercase; }}
    </style></head><body><div class='caption'>{safe_text}</div></body></html>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page = context.new_page()
        try:
            page.set_content(document, wait_until="networkidle")
            page.screenshot(path=str(destination), omit_background=True)
        finally:
            context.close()
            browser.close()


def _run(args: list[str], *, timeout: int = 600) -> None:
    process = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if process.returncode != 0:
        detail = process.stderr or process.stdout or "Falha no FFmpeg."
        raise RuntimeError(detail[-1600:])


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} não encontrado: {path}")


def _normalize_scene(scene: CompositionScene, destination: Path, ffmpeg: str) -> None:
    _require_file(scene.video_path, f"Vídeo da {scene.scene_id}")
    for overlay in scene.overlay_paths:
        _require_file(overlay, f"Overlay da {scene.scene_id}")
    if scene.captions_path:
        _require_file(scene.captions_path, f"Legendas da {scene.scene_id}")

    caption_assets: list[tuple[Path, float, float]] = []
    if scene.captions_path:
        for cue_index, (start, end, text) in enumerate(_srt_cues(scene.captions_path)):
            caption_text = destination.with_suffix(f".caption-{cue_index:02d}.png")
            _caption_image(text, caption_text)
            caption_assets.append((caption_text, start, end))

    input_args: list[str] = [ffmpeg, "-y", "-i", str(scene.video_path)]
    for overlay in scene.overlay_paths:
        input_args.extend(["-loop", "1", "-i", str(overlay)])
    for caption_asset, _start, _end in caption_assets:
        input_args.extend(["-loop", "1", "-i", str(caption_asset)])
    filters = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30[base]"
    ]
    previous = "base"
    for index, _overlay in enumerate(scene.overlay_paths, start=1):
        overlay_label = f"overlay{index}"
        output_label = f"composed{index}"
        filters.append(f"[{index}:v]format=rgba[{overlay_label}]")
        filters.append(f"[{previous}][{overlay_label}]overlay=0:0:shortest=1[{output_label}]")
        previous = output_label
    for cue_index, (_caption_asset, start, end) in enumerate(caption_assets):
        input_index = 1 + len(scene.overlay_paths) + cue_index
        output_label = f"captioned{cue_index}"
        filters.append(f"[{input_index}:v]format=rgba[caption{cue_index}]")
        filters.append(
            f"[{previous}][caption{cue_index}]overlay=0:0:shortest=1:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{output_label}]"
        )
        previous = output_label
    input_args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{previous}]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            str(destination),
        ]
    )
    _run(input_args)


def _render_slide(slide_path: Path, destination: Path, duration: float, ffmpeg: str) -> None:
    _require_file(slide_path, "Video Slide")
    if duration <= 0 or duration > 60:
        raise ValueError("A duração do Video Slide deve estar entre 0 e 60 segundos.")
    _run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(slide_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            str(destination),
        ]
    )


def compose_video(
    scenes: Iterable[CompositionScene],
    output_path: Path,
    *,
    ffmpeg_binary: str | None = None,
) -> dict[str, Any]:
    """Compõe cenas em ordem e retorna um manifesto de cortes secos."""
    scene_list = list(scenes)
    if not scene_list:
        raise ValueError("Informe pelo menos uma cena para compor o vídeo.")
    ffmpeg = ffmpeg_binary or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg não encontrado no ambiente local.")
    if not output_path.parent:
        raise ValueError("output_path inválido.")
    if output_path.suffix.lower() != ".mp4":
        raise ValueError("A saída do compositor deve ser um arquivo .mp4.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_ids: set[str] = set()
    for index, scene in enumerate(scene_list, start=1):
        if not scene.scene_id.strip() or scene.scene_id in seen_ids:
            raise ValueError(f"ID duplicado ou vazio na cena {index}.")
        seen_ids.add(scene.scene_id)

    with tempfile.TemporaryDirectory(prefix="video-composer-") as temporary:
        workdir = Path(temporary)
        segments: list[Path] = []
        manifest: list[dict[str, Any]] = []
        for index, scene in enumerate(scene_list, start=1):
            normalized = workdir / f"scene-{index:02d}.mp4"
            _normalize_scene(scene, normalized, ffmpeg)
            segments.append(normalized)
            manifest.append({"sceneId": scene.scene_id, "kind": "avatar", "cut": "hard"})
            if scene.slide_path:
                slide = workdir / f"scene-{index:02d}-slide.mp4"
                _render_slide(scene.slide_path, slide, scene.slide_duration_seconds, ffmpeg)
                segments.append(slide)
                manifest.append(
                    {
                        "sceneId": scene.scene_id,
                        "kind": "video_slide",
                        "cut": "hard",
                        "durationSeconds": scene.slide_duration_seconds,
                    }
                )
        concat_file = workdir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file {shlex.quote(str(path))}" for path in segments) + "\n",
            encoding="utf-8",
        )
        _run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
    return {
        "outputPath": str(output_path),
        "width": VIDEO_WIDTH,
        "height": VIDEO_HEIGHT,
        "fps": VIDEO_FPS,
        "sceneCount": len(scene_list),
        "segmentCount": len(manifest),
        "cutPolicy": "hard_cut",
        "segments": manifest,
    }
