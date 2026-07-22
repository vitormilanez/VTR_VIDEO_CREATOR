#!/usr/bin/env python3
"""Cria novos looks de avatar na HeyGen a partir de fotos locais."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.heygen_client import HeyGenClient


AVATAR_GROUP_ID = "6cfd960b8d8d45bcae1ce3bbe4bd74dd"

LOOKS = [
    {
        "name": "Dr Guilherme - Formal sorrindo",
        "path": Path("assets/personas/dr-guilherme/raw/IMG_6223 TRATADA.jpg"),
    },
    {
        "name": "Dr Guilherme - Camisa branca close",
        "path": Path("assets/personas/dr-guilherme/raw/IMG_6506 TRATADA.jpg"),
    },
    {
        "name": "Dr Guilherme - Casual serio",
        "path": Path("assets/personas/dr-guilherme/raw/IMG_6518 TRATADA.jpg"),
    },
]


def extract_asset_id(payload: dict) -> str:
    data = payload.get("data", payload)
    asset_id = data.get("asset_id") or data.get("id")
    if not asset_id:
        raise RuntimeError(f"Upload sem asset_id: {payload}")
    return asset_id


def extract_avatar(payload: dict) -> dict:
    data = payload.get("data", payload)
    avatar = data.get("avatar_item") or data.get("avatar") or data
    if not avatar.get("id"):
        raise RuntimeError(f"Criação sem avatar id: {payload}")
    return avatar


def main() -> int:
    client = HeyGenClient()
    created = []
    for look in LOOKS:
        path = look["path"]
        upload = client.upload_asset(path)
        asset_id = extract_asset_id(upload)
        result = client.create_photo_avatar_look(
            name=look["name"],
            asset_id=asset_id,
            avatar_group_id=AVATAR_GROUP_ID,
        )
        avatar = extract_avatar(result)
        created.append(
            {
                "name": look["name"],
                "source_path": str(path),
                "asset_id": asset_id,
                "avatar_id": avatar.get("id"),
                "group_id": avatar.get("group_id"),
                "status": avatar.get("status"),
                "default_voice_id": avatar.get("default_voice_id"),
            }
        )
    print(json.dumps({"created": created}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
