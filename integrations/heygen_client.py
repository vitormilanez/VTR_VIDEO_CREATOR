"""Cliente simples para HeyGen API v3."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import requests

from integrations.portuguese_br import apply_portuguese_br_accents


BASE_URL = "https://api.heygen.com/v3"


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class HeyGenClient:
    def __init__(self, api_key: str | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("HEYGEN_API_KEY")
        if not self.api_key:
            raise RuntimeError("Defina HEYGEN_API_KEY no .env ou no ambiente.")

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{BASE_URL}{path}",
            headers={**self.headers, **kwargs.pop("headers", {})},
            timeout=int(os.getenv("HEYGEN_TIMEOUT_SECONDS", "20")),
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        if response.status_code >= 400:
            raise RuntimeError(f"HeyGen API erro {response.status_code}: {payload}")

        return payload

    def get_current_user(self) -> dict[str, Any]:
        return self._request("GET", "/users/me")

    def list_avatars(self, ownership: str | None = None, limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ownership:
            params["ownership"] = ownership
        return self._request("GET", "/avatars", params=params)

    def list_avatar_looks(
        self,
        *,
        group_id: str | None = None,
        avatar_type: str | None = None,
        ownership: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if group_id:
            params["group_id"] = group_id
        if avatar_type:
            params["avatar_type"] = avatar_type
        if ownership:
            params["ownership"] = ownership
        return self._request("GET", "/avatars/looks", params=params)

    def get_video(self, video_id: str) -> dict[str, Any]:
        return self._request("GET", f"/videos/{video_id}")

    def download_file(self, url: str, path: Path) -> Path:
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path

    def upload_asset(self, path: Path) -> dict[str, Any]:
        with path.open("rb") as file:
            response = requests.post(
                f"{BASE_URL}/assets",
                headers=self.headers,
                files={"file": (path.name, file)},
                timeout=int(os.getenv("HEYGEN_TIMEOUT_SECONDS", "60")),
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            raise RuntimeError(f"HeyGen API erro {response.status_code}: {payload}")
        return payload

    def create_photo_avatar_look(
        self,
        *,
        name: str,
        asset_id: str,
        avatar_group_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "photo",
            "name": name,
            "file": {"type": "asset_id", "asset_id": asset_id},
        }
        if avatar_group_id:
            payload["avatar_group_id"] = avatar_group_id
        return self._request(
            "POST",
            "/avatars",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )

    def create_avatar_video(
        self,
        *,
        avatar_id: str,
        script: str,
        title: str,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        voice_id: str | None = None,
        caption: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "avatar",
            "avatar_id": avatar_id,
            "title": title,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": "mp4",
            "script": apply_portuguese_br_accents(script),
            "engine": {"type": "avatar_iv"},
        }
        if caption:
            payload["caption"] = {"file_format": "srt", "style": "default"}
        if voice_id:
            payload["voice_id"] = voice_id

        if dry_run:
            return {"dry_run": True, "payload": payload}

        return self._request(
            "POST",
            "/videos",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
