#!/usr/bin/env python3
"""Build a title/date-oriented library for all local content artifacts.

The app stores operational files by subsystem because those paths are stable API
contracts. This tool creates a human-facing library under content/biblioteca/
using relative symlinks, so files are easy to find without moving originals.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_ROOT = ROOT / "content" / "biblioteca"

PROJECT_SUBDIRS = {
    "packs": "01-packs",
    "produced": "02-videos-produzidos",
    "edits": "03-edicao-local",
    "post": "04-pos-producao",
    "cuts": "05-cortes",
    "assets": "06-assets",
    "uploads": "07-uploads-e-fontes",
    "reports": "08-relatorios-exportados",
}


@dataclass
class Artifact:
    kind: str
    source: Path
    label: str


@dataclass
class Project:
    title: str
    date: str
    slug: str
    artifacts: list[Artifact] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.date}_{self.slug}"


SEEN_ARTIFACT_SOURCES: set[Path] = set()
TITLE_ALIASES: dict[str, tuple[str, str]] = {}


def slugify(value: str, fallback: str = "conteudo") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:80] or fallback


def title_from_slug(value: str) -> str:
    clean = re.sub(r"--(?:v|kit|vc|post|cut)-[a-z0-9_-]+.*$", "", value, flags=re.I)
    clean = re.sub(r"--kit-grafico--kit-[a-z0-9_-]+.*$", "", clean, flags=re.I)
    clean = re.sub(r"\.(mp4|mov|webm|jpg|jpeg|png|md|json|txt|csv|docx|html|pdf)$", "", clean, flags=re.I)
    clean = clean.replace("_", "-").strip("- ")
    return " ".join(part for part in clean.split("-") if part).strip().capitalize() or "Conteudo"


def loose_slug(value: str) -> str:
    slug = slugify(value)
    replacements = {
        "est": "esta",
        "voc": "voce",
        "n": "nao",
        "m": "mae",
        "c": "ce",
        "mol": "moleculas",
        "gen": "genetica",
        "tica": "",
        "culas": "",
    }
    tokens = [replacements.get(token, token) for token in slug.split("-")]
    return "-".join(token for token in tokens if token)


def register_title_alias(title: str, date: str) -> None:
    canonical = (title, date)
    slug = slugify(title)
    TITLE_ALIASES[slug] = canonical
    TITLE_ALIASES[loose_slug(title)] = canonical


def canonical_title_date(title: str, date: str) -> tuple[str, str]:
    slug = slugify(title)
    loose = loose_slug(title)
    if slug in TITLE_ALIASES:
        return TITLE_ALIASES[slug]
    if loose in TITLE_ALIASES:
        return TITLE_ALIASES[loose]
    for alias, canonical in TITLE_ALIASES.items():
        if slug.startswith(alias[: min(34, len(alias))]) or alias.startswith(slug[: min(34, len(slug))]):
            return canonical
        if loose.startswith(alias[: min(34, len(alias))]) or alias.startswith(loose[: min(34, len(loose))]):
            return canonical
    return title, date


def date_from_any(value: Any, fallback: str | None = None) -> str:
    if isinstance(value, str) and value:
        match = re.search(r"20\d{2}-\d{2}-\d{2}", value)
        if match:
            return match.group(0)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).date().isoformat()
        except ValueError:
            pass
    return fallback or datetime.now().date().isoformat()


def load_snapshot() -> dict[str, Any]:
    path = ROOT / "data" / "sheets_snapshot.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def scripts_by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = snapshot.get("sheets", {}).get("roteiros", [])
    out: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        script_id = str(row.get("ID") or f"s-{index}").strip()
        title = str(row.get("Título") or row.get("Tema") or "Roteiro").strip()
        date = date_from_any(row.get("Criado em") or row.get("Data") or snapshot.get("updated_at"))
        out[script_id] = {"title": title, "date": date, "slug": slugify(title)}
    return out


def ensure_project(projects: dict[str, Project], title: str, date: str) -> Project:
    title, date = canonical_title_date(title, date)
    slug = slugify(title)
    key = f"{date}_{slug}"
    if key not in projects:
        projects[key] = Project(title=title.strip() or "Conteudo", date=date, slug=slug)
    return projects[key]


def add_artifact(projects: dict[str, Project], title: str, date: str, kind: str, source: Path, label: str) -> None:
    source = source.resolve()
    if not source.exists():
        return
    if source in SEEN_ARTIFACT_SOURCES:
        return
    SEEN_ARTIFACT_SOURCES.add(source)
    project = ensure_project(projects, title, date)
    project.artifacts.append(Artifact(kind=kind, source=source, label=label))


def add_packs(projects: dict[str, Project]) -> None:
    packs_root = ROOT / "content" / "packs"
    if not packs_root.is_dir():
        return
    for folder in sorted(path for path in packs_root.iterdir() if path.is_dir()):
        match = re.match(r"(20\d{2}-\d{2}-\d{2})_(.+)", folder.name)
        date = match.group(1) if match else date_from_any(None)
        title = title_from_slug(match.group(2) if match else folder.name)
        readme = folder / "LEIA-ME.md"
        if readme.is_file():
            first = next((line.strip("# \n") for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines() if line.startswith("# ")), "")
            title = first or title
        register_title_alias(title, date)
        add_artifact(projects, title, date, "packs", folder, folder.name)


def operational_jobs() -> list[dict[str, Any]]:
    db = ROOT / "data" / "operations.db"
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "select kind,id,status,script_id,payload_json,created_at,updated_at from operational_jobs"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    jobs: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            pass
        jobs.append({**dict(row), "payload": payload})
    return jobs


def add_operational_jobs(projects: dict[str, Project], script_index: dict[str, dict[str, str]]) -> None:
    for job in operational_jobs():
        payload = job["payload"]
        script_meta = script_index.get(str(job.get("script_id") or ""))
        title = script_meta["title"] if script_meta else title_from_slug(str(payload.get("sourceName") or job["id"]))
        date = date_from_any(job.get("created_at"), script_meta["date"] if script_meta else None)
        kind = str(job.get("kind") or "")
        if kind == "video":
            output_path = payload.get("outputPath")
            if output_path:
                add_artifact(projects, title, date, "produced", ROOT / str(output_path), f"{job['id']}.mp4")
        elif kind == "post_production":
            directory = ROOT / "content" / "videos" / "pos-producao" / str(job["id"])
            add_artifact(projects, title, date, "post", directory, str(job["id"]))


def add_local_video_kits(projects: dict[str, Project]) -> None:
    jobs_root = ROOT / "data" / "local_video_kits"
    if not jobs_root.is_dir():
        return
    for job_file in sorted(jobs_root.glob("*/job.json")):
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        config = job.get("config") if isinstance(job.get("config"), dict) else {}
        title_source = job.get("sourceName") or job.get("outputPath") or config.get("title") or job.get("id")
        title = title_from_slug(str(title_source or "Edicao local"))
        date = date_from_any(job.get("criadoEm") or job.get("createdAt"))
        job_id = str(job.get("id") or job_file.parent.name)
        output = ROOT / str(job.get("outputPath") or "")
        if output.exists():
            add_artifact(projects, title, date, "edits", output, f"{job_id}-video-final{output.suffix}")
        add_artifact(projects, title, date, "edits", job_file.parent, f"{job_id}-arquivos")


def add_files_by_folder(projects: dict[str, Project]) -> None:
    produced_root = ROOT / "content" / "videos" / "produzidos"
    if produced_root.is_dir():
        for path in produced_root.rglob("*.mp4"):
            date = date_from_any(datetime.fromtimestamp(path.stat().st_mtime).isoformat())
            add_artifact(projects, title_from_slug(path.name), date, "produced", path, path.name)

    edits_root = ROOT / "content" / "videos" / "video feito"
    if edits_root.is_dir():
        for path in edits_root.glob("*"):
            if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".webm", ".jpg", ".png"}:
                date = date_from_any(datetime.fromtimestamp(path.stat().st_mtime).isoformat())
                add_artifact(projects, title_from_slug(path.name), date, "edits", path, path.name)

    for cuts_root in (ROOT / "content" / "videos" / "cortes", ROOT / "content" / "videos" / "arquivo"):
        if cuts_root.is_dir():
            for path in cuts_root.rglob("*.mp4"):
                date = date_from_any(str(path))
                add_artifact(projects, title_from_slug(path.name), date, "cuts", path, path.name)

    for folder, kind, title in (
        (ROOT / "data" / "pack_assets", "assets", "Assets gerais"),
        (ROOT / "data" / "local_video_kit_uploads", "uploads", "Uploads locais"),
        (ROOT / "exports", "reports", "Relatorios e exports"),
        (ROOT / "output", "reports", "Relatorios e outputs"),
    ):
        if folder.is_dir():
            add_artifact(projects, title, date_from_any(datetime.fromtimestamp(folder.stat().st_mtime).isoformat()), kind, folder, folder.name)


def relative_symlink(source: Path, target: Path, *, dry_run: bool = False) -> None:
    if target.exists() or target.is_symlink():
        return
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    rel_source = os.path.relpath(source, target.parent)
    try:
        target.symlink_to(rel_source, target_is_directory=source.is_dir())
    except OSError:
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def unique_target(base: Path) -> Path:
    if not base.exists() and not base.is_symlink():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    for index in range(2, 1000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise RuntimeError(f"nao consegui criar nome unico para {base}")


def clean_library(*, dry_run: bool = False) -> None:
    if dry_run or not LIBRARY_ROOT.exists():
        return
    shutil.rmtree(LIBRARY_ROOT)


def render_project(project: Project, *, dry_run: bool = False) -> None:
    project_dir = LIBRARY_ROOT / project.key
    if not dry_run:
        project_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ["00-resumo", *PROJECT_SUBDIRS.values()]:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    by_kind: dict[str, list[Artifact]] = {}
    for artifact in project.artifacts:
        by_kind.setdefault(artifact.kind, []).append(artifact)

    for kind, artifacts in by_kind.items():
        subdir = PROJECT_SUBDIRS.get(kind, "99-outros")
        for artifact in artifacts:
            label = slugify(Path(artifact.label).stem, "artefato") + Path(artifact.label).suffix.lower()
            target = unique_target(project_dir / subdir / label)
            relative_symlink(artifact.source, target, dry_run=dry_run)

    if dry_run:
        return
    lines = [
        f"# {project.title}",
        "",
        f"Data: {project.date}",
        f"Pasta: `{project.key}`",
        "",
        "## Conteudos por tipo",
        "",
    ]
    for kind, subdir in PROJECT_SUBDIRS.items():
        count = len(by_kind.get(kind, []))
        if count:
            lines.append(f"- `{subdir}/` — {count} item(ns)")
    lines += [
        "",
        "## Observacao",
        "",
        "Esta pasta e uma biblioteca de atalhos relativos para os arquivos reais do app.",
        "Nao apague os arquivos originais em `content/` ou `data/` se o app ainda precisar deles.",
        "",
    ]
    (project_dir / "00-resumo" / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def build_library(*, dry_run: bool = False, clean: bool = True) -> dict[str, int]:
    SEEN_ARTIFACT_SOURCES.clear()
    TITLE_ALIASES.clear()
    snapshot = load_snapshot()
    script_index = scripts_by_id(snapshot)
    for meta in script_index.values():
        register_title_alias(meta["title"], meta["date"])
    projects: dict[str, Project] = {}
    add_packs(projects)
    add_operational_jobs(projects, script_index)
    add_local_video_kits(projects)
    add_files_by_folder(projects)

    if clean:
        clean_library(dry_run=dry_run)
    if not dry_run:
        LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    for project in sorted(projects.values(), key=lambda item: item.key):
        render_project(project, dry_run=dry_run)
    return {
        "projects": len(projects),
        "artifacts": sum(len(project.artifacts) for project in projects.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Organiza os artefatos locais por data, titulo e tipo.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra contagens sem escrever arquivos.")
    parser.add_argument("--no-clean", action="store_true", help="Nao recria content/biblioteca do zero.")
    args = parser.parse_args()
    result = build_library(dry_run=args.dry_run, clean=not args.no_clean)
    print(
        f"Biblioteca {'simulada' if args.dry_run else 'organizada'}: "
        f"{result['projects']} projeto(s), {result['artifacts']} artefato(s)."
    )
    if not args.dry_run:
        print(f"Pasta: {LIBRARY_ROOT}")


if __name__ == "__main__":
    main()
