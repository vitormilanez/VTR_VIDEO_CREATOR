"""Resolve links intermediarios do Google News para a materia original."""

from __future__ import annotations

import json
import re
from urllib.parse import quote, urlparse

import requests


def resolve_google_news_url(source_url: str, timeout: int = 10) -> str:
    parsed = urlparse(source_url)
    parts = parsed.path.rstrip("/").split("/")
    if parsed.hostname != "news.google.com" or len(parts) < 2 or parts[-2] not in {"articles", "read"}:
        return source_url

    token = parts[-1]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VTRVideoCreator/1.0)"}
    try:
        page = requests.get(f"https://news.google.com/articles/{token}", headers=headers, timeout=timeout)
        page.raise_for_status()
        signature = re.search(r'data-n-a-sg="([^"]+)"', page.text)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', page.text)
        if not signature or not timestamp:
            return source_url

        request_payload = [
            "Fbv4je",
            (
                '["garturlreq",[["X","X",["X","X"],null,null,1,1,"BR:pt-419",'
                'null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,'
                f'null,0],"{token}",{timestamp.group(1)},"{signature.group(1)}"]'
            ),
        ]
        response = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=f"f.req={quote(json.dumps([[request_payload]]))}",
            timeout=timeout,
        )
        response.raise_for_status()
        chunks = response.text.split("\n\n")
        decoded = json.loads(json.loads(chunks[1])[0][2])[1]
        return decoded if isinstance(decoded, str) and decoded.startswith(("http://", "https://")) else source_url
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return source_url
