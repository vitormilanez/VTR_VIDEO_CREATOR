"""Compositor local de cenas, transições, Video Slides, overlays e legendas.

O compositor trabalha somente com arquivos locais. Cada cena é normalizada
para o mesmo canvas e unida em ordem; portanto, trocar o Avatar Look só pode
acontecer entre dois arquivos de cena.
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
TRANSITION_STYLES = frozenset({"hard_cut", "smooth", "dip_to_black"})


@dataclass(frozen=True)
class TimedOverlay:
    path: Path
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class TimedVideoOverlay:
    """Vídeo visual em tela cheia; o áudio sempre continua vindo da cena-base."""

    path: Path
    start_seconds: float
    end_seconds: float
    shot_id: str = ""
    strategy: str = "cinematic_broll"


@dataclass(frozen=True)
class CompositionScene:
    scene_id: str
    video_path: Path
    slide_path: Path | None = None
    slide_mode: str = "between"
    visual_start_seconds: float = 0.45
    slide_duration_seconds: float = 1.5
    visual_animation: str = "fade"
    overlay_paths: tuple[Path, ...] = ()
    timed_overlays: tuple[TimedOverlay, ...] = ()
    timed_video_overlays: tuple[TimedVideoOverlay, ...] = ()
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
    .caption {{ max-width:860px; padding:15px 26px; color:#fff; background:rgba(3,23,37,.76); border:1px solid rgba(255,255,255,.12); border-radius:18px; box-shadow:0 12px 34px rgba(0,0,0,.22); font-size:46px; font-weight:700; line-height:1.14; text-align:center; }}
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


def _probe_duration(path: Path) -> float:
    """Retorna a duração de um arquivo de mídia sem alterar o original."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe não encontrado no ambiente local.")
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "Não foi possível ler a duração do vídeo.")
    try:
        return max(0.0, float(process.stdout.strip()))
    except ValueError as exc:
        raise RuntimeError("Duração inválida retornada pelo FFprobe.") from exc


def _mix_background_music(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    *,
    volume: float,
    ffmpeg: str,
) -> float:
    """Mistura música baixa no MP4 final, preservando integralmente a voz.

    A trilha é loopada e limitada à duração da narrativa. Ela não substitui
    nem desloca o áudio original das cenas; fica apenas como uma camada de fundo.
    """
    _require_file(music_path, "Trilha de fundo")
    duration = _probe_duration(video_path)
    if duration <= 0:
        raise RuntimeError("O vídeo final não possui duração válida para receber trilha.")
    fade_out_start = max(0.0, duration - 1.2)
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-stream_loop",
            "-1",
            "-i",
            str(music_path),
            "-filter_complex",
            (
                f"[1:a]atrim=duration={duration:.3f},"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.3f}:d=1.2,"
                f"volume={volume:.3f}[music];"
                "[0:a][music]amix=inputs=2:duration=first:normalize=0[audio]"
            ),
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )
    return duration


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} não encontrado: {path}")


def _normalize_scene(scene: CompositionScene, destination: Path, ffmpeg: str) -> None:
    _require_file(scene.video_path, f"Vídeo da {scene.scene_id}")
    if scene.slide_path and scene.slide_mode == "during":
        _require_file(scene.slide_path, f"Apoio visual da {scene.scene_id}")
        if scene.visual_start_seconds < 0:
            raise ValueError("O início do apoio visual não pode ser negativo.")
        if scene.slide_duration_seconds <= 0 or scene.slide_duration_seconds > 60:
            raise ValueError("A duração do apoio visual deve estar entre 0 e 60 segundos.")
    for overlay in scene.overlay_paths:
        _require_file(overlay, f"Overlay da {scene.scene_id}")
    for overlay in scene.timed_overlays:
        _require_file(overlay.path, f"Overlay temporizado da {scene.scene_id}")
        if overlay.start_seconds < 0 or overlay.end_seconds <= overlay.start_seconds:
            raise ValueError(f"Intervalo inválido no overlay temporizado da {scene.scene_id}.")
    for overlay in scene.timed_video_overlays:
        _require_file(overlay.path, f"Vídeo temporizado da {scene.scene_id}")
        if overlay.start_seconds < 0 or overlay.end_seconds <= overlay.start_seconds:
            raise ValueError(f"Intervalo inválido no vídeo temporizado da {scene.scene_id}.")
    if scene.captions_path:
        _require_file(scene.captions_path, f"Legendas da {scene.scene_id}")

    caption_assets: list[tuple[Path, float, float]] = []
    if scene.captions_path:
        for cue_index, (start, end, text) in enumerate(_srt_cues(scene.captions_path)):
            caption_text = destination.with_suffix(f".caption-{cue_index:02d}.png")
            _caption_image(text, caption_text)
            caption_assets.append((caption_text, start, end))

    input_args: list[str] = [ffmpeg, "-y", "-i", str(scene.video_path)]
    slide_input_index: int | None = None
    if scene.slide_path and scene.slide_mode == "during":
        slide_input_index = 1
        input_args.extend(["-loop", "1", "-i", str(scene.slide_path)])
    overlay_start_index = 1 + (1 if slide_input_index is not None else 0)
    for overlay in scene.overlay_paths:
        input_args.extend(["-loop", "1", "-i", str(overlay)])
    timed_overlay_start_index = overlay_start_index + len(scene.overlay_paths)
    for overlay in scene.timed_overlays:
        input_args.extend(["-loop", "1", "-i", str(overlay.path)])
    timed_video_start_index = timed_overlay_start_index + len(scene.timed_overlays)
    for overlay in scene.timed_video_overlays:
        input_args.extend(["-i", str(overlay.path)])
    caption_start_index = timed_video_start_index + len(scene.timed_video_overlays)
    for caption_asset, _start, _end in caption_assets:
        input_args.extend(["-loop", "1", "-i", str(caption_asset)])
    filters = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30[base]"
    ]
    previous = "base"
    if slide_input_index is not None:
        start = scene.visual_start_seconds
        end = start + scene.slide_duration_seconds
        fade = min(0.18, scene.slide_duration_seconds / 4)
        visual_filters = [
            f"[{slide_input_index}:v]scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
        ]
        if scene.visual_animation in {"soft_zoom", "fade_zoom"}:
            visual_filters.extend(
                [
                    "scale=1128:2005:force_original_aspect_ratio=increase",
                    "crop=1080:1920",
                ]
            )
        visual_filters.extend(["format=rgba", "colorchannelmixer=aa=0.96"])
        if scene.visual_animation in {"fade", "fade_zoom"}:
            visual_filters.extend(
                [
                    f"fade=t=in:st={start:.3f}:d={fade:.3f}:alpha=1",
                ]
            )
        filters.append(",".join(visual_filters) + "[visualslide]")
        filters.append(
            f"[{previous}][visualslide]overlay=0:0:shortest=1:"
            f"enable='between(t,{start:.3f},{end:.3f})'[withvisual]"
        )
        previous = "withvisual"
    for index, _overlay in enumerate(scene.overlay_paths, start=overlay_start_index):
        overlay_label = f"overlay{index}"
        output_label = f"composed{index}"
        filters.append(f"[{index}:v]format=rgba[{overlay_label}]")
        filters.append(f"[{previous}][{overlay_label}]overlay=0:0:shortest=1[{output_label}]")
        previous = output_label
    for timed_index, overlay in enumerate(scene.timed_overlays):
        input_index = timed_overlay_start_index + timed_index
        overlay_label = f"timedoverlay{timed_index}"
        output_label = f"timedcomposed{timed_index}"
        filters.append(f"[{input_index}:v]format=rgba[{overlay_label}]")
        filters.append(
            f"[{previous}][{overlay_label}]overlay=0:0:shortest=1:"
            f"enable='between(t,{overlay.start_seconds:.3f},{overlay.end_seconds:.3f})'[{output_label}]"
        )
        previous = output_label
    for video_index, overlay in enumerate(scene.timed_video_overlays):
        input_index = timed_video_start_index + video_index
        overlay_label = f"timedvideo{video_index}"
        output_label = f"timedvideocomposed{video_index}"
        target_duration = overlay.end_seconds - overlay.start_seconds
        source_duration = max(0.05, _probe_duration(overlay.path))
        visible_duration = min(source_duration, target_duration)
        freeze_duration = max(0.0, target_duration - visible_duration)
        video_filters = [
            f"[{input_index}:v]scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
            "fps=30",
            f"trim=duration={visible_duration:.3f}",
            "setpts=PTS-STARTPTS",
        ]
        if freeze_duration > 0.001:
            video_filters.append(
                f"tpad=stop_mode=clone:stop_duration={freeze_duration:.3f}"
            )
        video_filters.extend(
            [
                f"setpts=PTS+{overlay.start_seconds:.3f}/TB",
                "format=yuv420p",
            ]
        )
        filters.append(",".join(video_filters) + f"[{overlay_label}]")
        filters.append(
            f"[{previous}][{overlay_label}]overlay=0:0:shortest=0:eof_action=pass:"
            f"enable='between(t,{overlay.start_seconds:.3f},{overlay.end_seconds:.3f})'"
            f"[{output_label}]"
        )
        previous = output_label
    for cue_index, (_caption_asset, start, end) in enumerate(caption_assets):
        input_index = caption_start_index + cue_index
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


def _concat_segments(segments: list[Path], destination: Path, workdir: Path, ffmpeg: str) -> None:
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
            str(destination),
        ]
    )


def _transition_segments(
    segments: list[Path],
    destination: Path,
    *,
    style: str,
    ffmpeg: str,
) -> list[dict[str, Any]]:
    durations = [_probe_duration(path) for path in segments]
    ffmpeg_transition = "fade" if style == "smooth" else "fadeblack"
    requested_duration = 0.35 if style == "smooth" else 0.25
    input_args = [ffmpeg, "-y"]
    for segment in segments:
        input_args.extend(["-i", str(segment)])
    filters: list[str] = []
    for index in range(len(segments)):
        filters.extend(
            [
                f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}]",
                f"[{index}:a]aresample=48000,asetpts=PTS-STARTPTS[a{index}]",
            ]
        )
    video_label = "v0"
    audio_label = "a0"
    combined_duration = durations[0]
    transitions: list[dict[str, Any]] = []
    for index in range(1, len(segments)):
        duration = min(requested_duration, durations[index - 1] / 2, durations[index] / 2)
        duration = max(0.05, duration)
        offset = max(0.0, combined_duration - duration)
        next_video = f"vx{index}"
        next_audio = f"ax{index}"
        filters.append(
            f"[{video_label}][v{index}]xfade=transition={ffmpeg_transition}:"
            f"duration={duration:.3f}:offset={offset:.3f}[{next_video}]"
        )
        filters.append(
            f"[{audio_label}][a{index}]acrossfade=d={duration:.3f}:c1=tri:c2=tri[{next_audio}]"
        )
        transitions.append(
            {
                "fromSegment": index,
                "toSegment": index + 1,
                "style": style,
                "durationSeconds": round(duration, 3),
            }
        )
        video_label = next_video
        audio_label = next_audio
        combined_duration += durations[index] - duration
    input_args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{video_label}]",
            "-map",
            f"[{audio_label}]",
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
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    _run(input_args)
    return transitions


def compose_video(
    scenes: Iterable[CompositionScene],
    output_path: Path,
    *,
    background_music_path: Path | None = None,
    background_music_volume: float = 0.12,
    transition_style: str = "hard_cut",
    ffmpeg_binary: str | None = None,
) -> dict[str, Any]:
    """Compõe cenas em ordem e retorna um manifesto das transições aplicadas."""
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
    if not 0.03 <= background_music_volume <= 0.25:
        raise ValueError("O volume da trilha deve estar entre 0.03 e 0.25.")
    if transition_style not in TRANSITION_STYLES:
        raise ValueError(f"Transição inválida: {transition_style}.")
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
            avatar_segment: dict[str, Any] = {"sceneId": scene.scene_id, "kind": "avatar", "cut": "hard"}
            if scene.slide_path and scene.slide_mode == "during":
                avatar_segment["visualOverlay"] = {
                    "kind": "video_slide",
                    "startSeconds": scene.visual_start_seconds,
                    "durationSeconds": scene.slide_duration_seconds,
                    "animation": scene.visual_animation,
                    "audioSource": "avatar",
                }
            if scene.timed_video_overlays:
                avatar_segment["timedVideoOverlays"] = [
                    {
                        "shotId": overlay.shot_id,
                        "strategy": overlay.strategy,
                        "startSeconds": overlay.start_seconds,
                        "endSeconds": overlay.end_seconds,
                        "audioSource": "base_narration",
                        "generatedAudioMuted": True,
                    }
                    for overlay in scene.timed_video_overlays
                ]
            manifest.append(avatar_segment)
            if scene.slide_path and scene.slide_mode != "during":
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
        concatenated = workdir / "concatenated.mp4" if background_music_path else output_path
        transitions: list[dict[str, Any]] = []
        if transition_style == "hard_cut" or len(segments) == 1:
            _concat_segments(segments, concatenated, workdir, ffmpeg)
        else:
            transitions = _transition_segments(
                segments,
                concatenated,
                style=transition_style,
                ffmpeg=ffmpeg,
            )
        final_duration: float | None = None
        if background_music_path:
            final_duration = _mix_background_music(
                concatenated,
                background_music_path,
                output_path,
                volume=background_music_volume,
                ffmpeg=ffmpeg,
            )
    return {
        "outputPath": str(output_path),
        "width": VIDEO_WIDTH,
        "height": VIDEO_HEIGHT,
        "fps": VIDEO_FPS,
        "sceneCount": len(scene_list),
        "segmentCount": len(manifest),
        "cutPolicy": transition_style,
        "transitions": transitions,
        "segments": manifest,
        "backgroundMusic": (
            {
                "enabled": True,
                "volume": round(background_music_volume, 3),
                "durationSeconds": round(final_duration or 0, 2),
            }
            if background_music_path
            else {"enabled": False}
        ),
    }
