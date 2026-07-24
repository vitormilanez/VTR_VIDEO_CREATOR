from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal


JobKind = Literal["video", "avatar", "cut"]

_JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS operational_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('video', 'avatar', 'cut')),
    status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    script_id TEXT,
    remote_session_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class JobStore:
    def __init__(
        self,
        path: Path,
        *,
        legacy_video_path: Path | None = None,
        legacy_avatar_path: Path | None = None,
    ) -> None:
        self.path = path
        self.legacy_video_path = legacy_video_path
        self.legacy_avatar_path = legacy_avatar_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(_JOBS_TABLE_SQL)
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'operational_jobs'"
            ).fetchone()
            if table_sql and "'cut'" not in str(table_sql["sql"]):
                connection.execute("ALTER TABLE operational_jobs RENAME TO operational_jobs_v1")
                connection.execute(_JOBS_TABLE_SQL)
                connection.execute(
                    """
                    INSERT INTO operational_jobs
                    SELECT * FROM operational_jobs_v1
                    """
                )
                connection.execute("DROP TABLE operational_jobs_v1")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_kind_created "
                "ON operational_jobs(kind, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_script "
                "ON operational_jobs(kind, script_id, created_at DESC)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_remote_session "
                "ON operational_jobs(remote_session_id) WHERE remote_session_id IS NOT NULL"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operational_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            imported = connection.execute(
                "SELECT value FROM operational_meta WHERE key = 'legacy_json_imported_v1'"
            ).fetchone()
            if not imported:
                self._import_legacy(connection, "video", self.legacy_video_path)
                self._import_legacy(connection, "avatar", self.legacy_avatar_path)
                connection.execute(
                    "INSERT INTO operational_meta(key, value) VALUES (?, ?)",
                    ("legacy_json_imported_v1", "true"),
                )

    def _import_legacy(
        self,
        connection: sqlite3.Connection,
        kind: JobKind,
        path: Path | None,
    ) -> None:
        if not path or not path.exists():
            return
        try:
            jobs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(jobs, list):
            return
        for job in jobs:
            if isinstance(job, dict) and job.get("id"):
                self._upsert_on(connection, kind, job)

    @staticmethod
    def _record(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if row["idempotency_key"]:
            payload["idempotencyKey"] = row["idempotency_key"]
        return payload

    @staticmethod
    def _upsert_on(
        connection: sqlite3.Connection,
        kind: JobKind,
        job: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> None:
        job_id = str(job["id"])
        created_at = str(job.get("criadoEm") or job.get("createdAt") or job.get("updatedAt") or "")
        updated_at = str(job.get("atualizadoEm") or job.get("updatedAt") or created_at)
        connection.execute(
            """
            INSERT INTO operational_jobs(
                id, kind, status, idempotency_key, script_id, remote_session_id,
                payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                idempotency_key = COALESCE(
                    excluded.idempotency_key,
                    operational_jobs.idempotency_key
                ),
                script_id = excluded.script_id,
                remote_session_id = excluded.remote_session_id,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                job_id,
                kind,
                str(job.get("status") or "fila"),
                idempotency_key or job.get("idempotencyKey"),
                job.get("scriptId"),
                job.get("remoteSessionId"),
                json.dumps(job, ensure_ascii=False),
                created_at,
                updated_at,
            ),
        )

    def list(self, kind: JobKind) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM operational_jobs WHERE kind = ? ORDER BY created_at DESC, id DESC",
                (kind,),
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    def get(self, kind: JobKind, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM operational_jobs WHERE kind = ? AND id = ?",
                (kind, job_id),
            ).fetchone()
        return self._record(row)

    def upsert(
        self,
        kind: JobKind,
        job: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> None:
        with self._connection() as connection:
            self._upsert_on(connection, kind, job, idempotency_key)

    def replace(self, kind: JobKind, jobs: list[dict[str, Any]]) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM operational_jobs WHERE kind = ?", (kind,))
            for job in jobs:
                self._upsert_on(connection, kind, job)

    def reserve(
        self,
        kind: JobKind,
        job: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], Literal["created", "duplicate"]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM operational_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if duplicate:
                return self._record(duplicate) or job, "duplicate"
            self._upsert_on(connection, kind, job, idempotency_key)
            return job, "created"

    def reserve_video(
        self,
        job: dict[str, Any],
        *,
        idempotency_key: str,
        force_new_version: bool,
    ) -> tuple[dict[str, Any], Literal["created", "duplicate", "conflict"]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM operational_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if duplicate:
                return self._record(duplicate) or job, "duplicate"

            rows = connection.execute(
                """
                SELECT * FROM operational_jobs
                WHERE kind = 'video' AND script_id = ?
                ORDER BY created_at DESC
                """,
                (job.get("scriptId"),),
            ).fetchall()
            for row in rows:
                existing = self._record(row)
                if existing and existing.get("submissionState") in {
                    "reserved",
                    "submitting",
                    "submission_uncertain",
                }:
                    return existing, "conflict"

            if not force_new_version:
                for row in rows:
                    existing = self._record(row)
                    if not existing:
                        continue
                    retry_safe = bool(existing.get("retrySafe", existing.get("status") == "erro"))
                    if existing.get("status") != "erro" or not retry_safe:
                        return existing, "conflict"

            self._upsert_on(connection, "video", job, idempotency_key)
            return job, "created"
