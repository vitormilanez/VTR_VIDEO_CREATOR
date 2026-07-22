#!/usr/bin/env python3
"""Consulta status e links de um video HeyGen."""

from __future__ import annotations

import argparse
import json

from integrations.heygen_client import HeyGenClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta video na HeyGen.")
    parser.add_argument("video_id")
    args = parser.parse_args()

    result = HeyGenClient().get_video(args.video_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
