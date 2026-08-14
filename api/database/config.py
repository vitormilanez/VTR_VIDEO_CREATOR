from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


SUPPORTED_DATABASE_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg",
}


def normalize_database_url(raw_url: str) -> str:
    """Normaliza URLs comuns de provedores para o driver psycopg 3."""

    value = raw_url.strip()
    if not value:
        raise ValueError("DATABASE_URL está vazia.")
    parsed = urlsplit(value)
    if parsed.scheme not in SUPPORTED_DATABASE_SCHEMES:
        raise ValueError("DATABASE_URL deve apontar para PostgreSQL.")
    return urlunsplit(
        (
            "postgresql+psycopg",
            parsed.netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout_seconds: int = 30
    statement_timeout_ms: int = 30_000
    application_name: str = "ai-video-creator"

    @classmethod
    def from_env(cls, *, required: bool = True) -> DatabaseSettings | None:
        raw_url = os.getenv("DATABASE_URL", "").strip()
        if not raw_url:
            if required:
                raise RuntimeError("Defina DATABASE_URL para ativar o backend PostgreSQL.")
            return None
        return cls(
            url=normalize_database_url(raw_url),
            pool_size=max(1, int(os.getenv("DATABASE_POOL_SIZE", "5"))),
            max_overflow=max(0, int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))),
            pool_timeout_seconds=max(1, int(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30"))),
            statement_timeout_ms=max(1_000, int(os.getenv("DATABASE_STATEMENT_TIMEOUT_MS", "30000"))),
            application_name=(
                os.getenv("DATABASE_APPLICATION_NAME", "ai-video-creator").strip()
                or "ai-video-creator"
            ),
        )
