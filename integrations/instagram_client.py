"""Cliente leve para Instagram Graph API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


GRAPH_URL = "https://graph.facebook.com/v23.0"


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


class InstagramClient:
    def __init__(self, access_token: str | None = None, account_id: str | None = None) -> None:
        load_dotenv()
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN")
        self.account_id = account_id or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Defina META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID.")

        query = dict(params or {})
        query["access_token"] = self.access_token
        response = requests.get(f"{GRAPH_URL}{path}", params=query, timeout=30)
        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"Instagram API erro {response.status_code}: {payload}")
        return payload

    def profile(self) -> dict[str, Any]:
        return self._get(
            f"/{self.account_id}",
            {"fields": "id,username,name,profile_picture_url,followers_count,follows_count,media_count"},
        )

    def recent_media(self, limit: int = 10) -> dict[str, Any]:
        return self._get(
            f"/{self.account_id}/media",
            {"fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count", "limit": limit},
        )

    def media_insights(self, media_id: str, metrics: str = "reach,likes,comments,saved,shares,total_interactions") -> dict[str, Any]:
        return self._get(f"/{media_id}/insights", {"metric": metrics})
