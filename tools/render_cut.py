from __future__ import annotations

import argparse
import json
import re
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def caption_image(text: str, output: Path) -> None:
    image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = load_font(68)
    lines = textwrap.wrap(re.sub(r"\s+", " ", text).strip().upper(), width=24)[:2]
    heights = [draw.textbbox((0, 0), line, font=font, stroke_width=6) for line in lines]
    y = 1510 - sum(box[3] - box[1] + 12 for box in heights)
    for line, box in zip(lines, heights):
        width = box[2] - box[0]
        draw.text(
            ((1080 - width) / 2, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=6,
            stroke_fill=(0, 0, 0, 245),
        )
        y += box[3] - box[1] + 12
    image.save(output)


def caption_events(transcript: dict, start: float, end: float) -> list[dict]:
    words = []
    for segment in transcript.get("segments", []):
        words.extend(segment.get("words") or [])
    if not words:
        return [
            {
                "start": max(float(segment["start"]), start) - start,
                "end": min(float(segment["end"]), end) - start,
                "text": segment["text"],
            }
            for segment in transcript.get("segments", [])
            if float(segment["end"]) > start and float(segment["start"]) < end
        ]

    selected = [word for word in words if float(word["end"]) > start and float(word["start"]) < end]
    events = []
    current = []
    event_start = None
    for word in selected:
        if event_start is None:
            event_start = max(float(word["start"]), start)
        candidate = " ".join([*current, word["text"]])
        duration = float(word["end"]) - event_start
        if current and (len(candidate) > 46 or duration > 2.8):
            events.append(
                {
                    "start": event_start - start,
                    "end": previous_end - start,
                    "text": " ".join(current),
                }
            )
            current = [word["text"]]
            event_start = float(word["start"])
        else:
            current.append(word["text"])
        previous_end = min(float(word["end"]), end)
    if current and event_start is not None:
        events.append(
            {"start": event_start - start, "end": previous_end - start, "text": " ".join(current)}
        )
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    source = Path(config["source"])
    output = Path(config["output"])
    transcript = json.loads(Path(config["transcript"]).read_text(encoding="utf-8"))
    start = float(config["start"])
    end = float(config["end"])
    duration = end - start
    output.parent.mkdir(parents=True, exist_ok=True)

    if config.get("layout") == "fill":
        base = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,fps=30[base]"
        )
    else:
        base = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=28:1,eq=brightness=-0.10:saturation=0.85[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30[base]"
        )

    inputs: list[str] = []
    filters = [base]
    current = "[base]"
    if config.get("captions", True):
        for index, event in enumerate(caption_events(transcript, start, end), start=1):
            image = output.parent / f"{output.stem}_caption_{index:03d}.png"
            caption_image(event["text"], image)
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(image)])
            target = f"[captioned{index}]"
            filters.append(
                f"{current}[{index}:v]overlay=0:0:"
                f"enable='between(t,{max(event['start'], 0):.3f},{min(event['end'] + 0.08, duration):.3f})'"
                f"{target}"
            )
            current = target
    filters.append(f"{current}format=yuv420p[out]")

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    main()
