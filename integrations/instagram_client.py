"""Cliente leve para Instagram Graph API."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_GRAPH_VERSION = "v23.0"


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
        version = os.getenv("META_GRAPH_API_VERSION", DEFAULT_GRAPH_VERSION).strip()
        self.graph_url = f"https://graph.facebook.com/{version.lstrip('/')}"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Defina META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID.")

        query = dict(params or {})
        query["access_token"] = self.access_token
        response = requests.get(f"{self.graph_url}{path}", params=query, timeout=30)
        return self._response_payload(response)

    def _post(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Defina META_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID.")

        query = dict(params or {})
        query["access_token"] = self.access_token
        response = requests.post(f"{self.graph_url}{path}", params=query, timeout=45)
        return self._response_payload(response)

    @staticmethod
    def _response_payload(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise RuntimeError(f"Instagram API retornou HTTP {response.status_code} sem JSON.") from exc
        if response.status_code >= 400:
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(
                f"Instagram API erro {response.status_code}: {message or 'requisicao rejeitada pela Meta.'}"
            )
        if not isinstance(payload, dict):
            raise RuntimeError("Instagram API retornou uma resposta inesperada.")
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

    def create_video_container(
        self,
        video_url: str,
        *,
        media_type: str,
        caption: str = "",
        share_to_feed: bool = True,
    ) -> str:
        normalized_type = media_type.upper()
        if normalized_type not in {"REELS", "STORIES"}:
            raise ValueError("media_type deve ser REELS ou STORIES.")
        params: dict[str, Any] = {
            "media_type": normalized_type,
            "video_url": video_url,
        }
        if normalized_type == "REELS":
            if caption:
                params["caption"] = caption
            params["share_to_feed"] = str(share_to_feed).lower()
        response = self._post(f"/{self.account_id}/media", params)
        container_id = str(response.get("id") or "")
        if not container_id:
            raise RuntimeError("Instagram nao retornou o ID do container de midia.")
        return container_id

    def container_status(self, container_id: str) -> dict[str, Any]:
        return self._get(f"/{container_id}", {"fields": "status_code,status"})

    def publish_container(self, container_id: str) -> str:
        response = self._post(
            f"/{self.account_id}/media_publish",
            {"creation_id": container_id},
        )
        media_id = str(response.get("id") or "")
        if not media_id:
            raise RuntimeError("Instagram nao retornou o ID da publicacao.")
        return media_id

    def publish_video(
        self,
        video_url: str,
        *,
        media_type: str,
        caption: str = "",
        share_to_feed: bool = True,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 3,
    ) -> dict[str, Any]:
        container_id = self.create_video_container(
            video_url,
            media_type=media_type,
            caption=caption,
            share_to_feed=share_to_feed,
        )
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_status = self.container_status(container_id)
            status_code = str(last_status.get("status_code") or "").upper()
            if status_code == "FINISHED":
                media_id = self.publish_container(container_id)
                return {
                    "containerId": container_id,
                    "mediaId": media_id,
                    "mediaType": media_type.upper(),
                }
            if status_code in {"ERROR", "EXPIRED"}:
                detail = last_status.get("status") or status_code
                raise RuntimeError(f"Instagram nao processou o video: {detail}")
            time.sleep(poll_interval_seconds)
        detail = last_status.get("status") or "processamento ainda nao concluido"
        raise RuntimeError(f"Tempo esgotado aguardando o Instagram: {detail}")
