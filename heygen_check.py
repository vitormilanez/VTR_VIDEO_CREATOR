#!/usr/bin/env python3
"""Valida a API key da HeyGen e lista alguns avatares."""

from __future__ import annotations

import argparse
import json

from integrations.heygen_client import HeyGenClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Testa acesso a HeyGen API.")
    parser.add_argument("--avatars", action="store_true", help="Tambem lista avatares.")
    parser.add_argument("--looks", action="store_true", help="Tambem lista looks de avatar.")
    parser.add_argument("--group-id", default=None)
    parser.add_argument("--ownership", choices=["public", "private"], default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = HeyGenClient()

    user = client.get_current_user()
    print("Conta HeyGen OK.")
    print(json.dumps(user.get("data", user), ensure_ascii=False, indent=2))

    if args.avatars:
        avatars = client.list_avatars(ownership=args.ownership, limit=10)
        print("\nAvatares:")
        print(json.dumps(avatars.get("data", avatars), ensure_ascii=False, indent=2))

    if args.looks:
        looks = client.list_avatar_looks(group_id=args.group_id, ownership=args.ownership, limit=20)
        print("\nLooks:")
        print(json.dumps(looks.get("data", looks), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
