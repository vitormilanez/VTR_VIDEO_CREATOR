from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from faster_whisper import WhisperModel


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    model = WhisperModel(args.model, device="auto", compute_type="int8")
    raw_segments, info = model.transcribe(
        str(args.video),
        language="pt",
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )
    segments = []
    for segment in raw_segments:
        text = clean(segment.text)
        if not text:
            continue
        segments.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": text,
                "words": [
                    {
                        "start": round(float(word.start), 3),
                        "end": round(float(word.end), 3),
                        "text": clean(word.word),
                    }
                    for word in (segment.words or [])
                    if clean(word.word)
                ],
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "language": getattr(info, "language", "pt"),
                "duration": float(getattr(info, "duration", 0) or 0),
                "segments": segments,
                "text": " ".join(segment["text"] for segment in segments),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
