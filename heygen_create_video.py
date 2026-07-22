#!/usr/bin/env python3
"""Cria um video simples na HeyGen a partir de avatar_id e roteiro."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrations.portuguese_br import apply_portuguese_br_accents


def read_script(args: argparse.Namespace) -> str:
    if args.script:
        return apply_portuguese_br_accents(args.script.strip())
    if args.script_file:
        script = Path(args.script_file).read_text(encoding="utf-8").strip()
        return apply_portuguese_br_accents(script)
    raise RuntimeError("Informe --script ou --script-file.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cria video na HeyGen.")
    parser.add_argument("--avatar-id", required=True)
    parser.add_argument("--title", default="AI Video Creator - Teste")
    parser.add_argument("--script")
    parser.add_argument("--script-file")
    parser.add_argument("--voice-id")
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--no-caption", action="store_true", help="Nao solicita legenda/SRT.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script = read_script(args)
    if args.dry_run:
        result = {
            "dry_run": True,
            "payload": {
                "type": "avatar",
                "avatar_id": args.avatar_id,
                "title": args.title,
                "aspect_ratio": args.aspect_ratio,
                "resolution": args.resolution,
                "output_format": "mp4",
                "script": script,
            },
        }
        if not args.no_caption:
            result["payload"]["caption"] = {"file_format": "srt", "style": "default"}
        if args.voice_id:
            result["payload"]["voice_id"] = args.voice_id
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    from integrations.heygen_client import HeyGenClient

    client = HeyGenClient()
    result = client.create_avatar_video(
        avatar_id=args.avatar_id,
        title=args.title,
        script=script,
        voice_id=args.voice_id,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        caption=not args.no_caption,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
