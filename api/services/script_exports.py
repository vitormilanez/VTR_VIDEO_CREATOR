"""Arquivo local, aditivo e versionado dos vídeos gerados por roteiro.

Os arquivos de produção continuam nos diretórios usados pelo pipeline. Este
módulo apenas cria uma cópia organizada para entrega, sem mover ou apagar a
origem. A relação entre o ID estável da geração e a versão visível evita que
um refresh do mesmo job crie pastas ``1.2``, ``1.3`` indevidamente.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Iterable, Mapping
import unicodedata


EXPORT_INDEX_SCHEMA_VERSION = 1
_VERSION_PATTERN = re.compile(r"^1\.(\d+)$")
_EXPORT_LOCK = threading.RLock()


@dataclass(frozen=True)
class ScriptExportResult:
    version: str
    directory: Path
    files: tuple[str, ...]


def _slug(value: str, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:90] or fallback


def script_export_directory(
    export_root: Path,
    *,
    script_id: str,
    script_title: str,
) -> Path:
    title = _slug(script_title, fallback="roteiro")
    safe_id = _slug(script_id, fallback="sem-id")
    if export_root.is_dir():
        existing = sorted(
            path
            for path in export_root.glob(f"*--{safe_id}")
            if path.is_dir()
        )
        if existing:
            return existing[0]
    return export_root / f"{title}--{safe_id}"


def _read_version_index(script_directory: Path) -> dict[str, Any]:
    index_path = script_directory / "VERSOES.json"
    if not index_path.is_file():
        return {
            "schemaVersion": EXPORT_INDEX_SCHEMA_VERSION,
            "generations": {},
        }
    try:
        parsed = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Índice de versões inválido: {index_path}") from exc
    generations = parsed.get("generations")
    if not isinstance(generations, dict):
        raise RuntimeError(f"Índice de versões inválido: {index_path}")
    return {
        **parsed,
        "schemaVersion": EXPORT_INDEX_SCHEMA_VERSION,
        "generations": {
            str(generation_id): str(version)
            for generation_id, version in generations.items()
            if _VERSION_PATTERN.fullmatch(str(version))
        },
    }


def _write_version_index(script_directory: Path, index: Mapping[str, Any]) -> None:
    index_path = script_directory / "VERSOES.json"
    temporary = script_directory / ".VERSOES.json.tmp"
    temporary.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(index_path)


def reserve_export_version(
    script_directory: Path,
    *,
    generation_id: str,
    generated_at: str | None = None,
) -> str:
    """Reserva ``1.N`` uma única vez para o mesmo ID de geração."""

    stable_generation_id = str(generation_id).strip()
    if not stable_generation_id:
        raise ValueError("generation_id é obrigatório para versionar o arquivo.")
    with _EXPORT_LOCK:
        script_directory.mkdir(parents=True, exist_ok=True)
        index = _read_version_index(script_directory)
        generations = dict(index["generations"])
        existing = generations.get(stable_generation_id)
        if existing:
            (script_directory / existing).mkdir(parents=True, exist_ok=True)
            return existing

        used_minors = {
            int(match.group(1))
            for path in script_directory.iterdir()
            if path.is_dir() and (match := _VERSION_PATTERN.fullmatch(path.name))
        }
        used_minors.update(
            int(match.group(1))
            for version in generations.values()
            if (match := _VERSION_PATTERN.fullmatch(version))
        )
        next_minor = max(used_minors, default=0) + 1
        version = f"1.{next_minor}"
        generations[stable_generation_id] = version
        now = datetime.now(timezone.utc).isoformat()
        _write_version_index(
            script_directory,
            {
                **index,
                "schemaVersion": EXPORT_INDEX_SCHEMA_VERSION,
                "generations": generations,
                "generatedAt": {
                    **(
                        index.get("generatedAt")
                        if isinstance(index.get("generatedAt"), dict)
                        else {}
                    ),
                    stable_generation_id: generated_at or now,
                },
                "updatedAt": now,
            },
        )
        (script_directory / version).mkdir(parents=True, exist_ok=True)
        return version


def _copy_file(source: Path, destination: Path) -> str:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    same_file = source.resolve() == destination.resolve()
    already_current = False
    if not same_file and destination.is_file():
        source_stat = source.stat()
        destination_stat = destination.stat()
        already_current = (
            source_stat.st_size == destination_stat.st_size
            and source_stat.st_mtime_ns == destination_stat.st_mtime_ns
        )
    if not same_file and not already_current:
        shutil.copy2(source, destination)
    return str(destination)


def _safe_artifact_name(label: str, source: Path, *, fallback: str) -> str:
    base = _slug(label or source.stem, fallback=fallback)
    suffix = source.suffix.lower() or ".bin"
    return f"{base}{suffix}"


def archive_script_generation(
    export_root: Path,
    *,
    script_id: str,
    script_title: str,
    generation_id: str,
    final_video: Path,
    source_videos: Iterable[tuple[str, Path]] = (),
    captions: Iterable[tuple[str, str]] = (),
    local_assets: Iterable[tuple[str, Path]] = (),
    script_payload: Mapping[str, Any] | None = None,
    job_payload: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> ScriptExportResult:
    """Copia uma geração completa para a pasta versionada do roteiro."""

    if not final_video.is_file():
        raise FileNotFoundError(final_video)
    script_directory = script_export_directory(
        export_root,
        script_id=script_id,
        script_title=script_title,
    )
    version = reserve_export_version(
        script_directory,
        generation_id=generation_id,
        generated_at=generated_at,
    )
    version_directory = script_directory / version
    archived_files: list[Path] = []

    final_destination = version_directory / "video-final.mp4"
    _copy_file(final_video, final_destination)
    archived_files.append(final_destination)

    seen_names: set[str] = set()
    for position, (label, source) in enumerate(source_videos, start=1):
        if not source.is_file():
            continue
        base_name = _safe_artifact_name(label, source, fallback=f"tomada-{position:02d}")
        candidate = f"{position:02d}-{base_name}"
        while candidate in seen_names:
            candidate = f"{position:02d}-{len(seen_names) + 1:02d}-{base_name}"
        seen_names.add(candidate)
        destination = version_directory / "tomadas" / candidate
        _copy_file(source, destination)
        archived_files.append(destination)

    for position, (label, content) in enumerate(captions, start=1):
        normalized = str(content or "").strip()
        if not normalized:
            continue
        name = _slug(label, fallback=f"legenda-{position:02d}")
        destination = version_directory / "legendas" / f"{name}.srt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(normalized + "\n", encoding="utf-8")
        archived_files.append(destination)

    for position, (label, source) in enumerate(local_assets, start=1):
        if not source.is_file():
            continue
        name = _safe_artifact_name(label, source, fallback=f"arquivo-{position:02d}")
        destination = version_directory / "arquivos" / name
        _copy_file(source, destination)
        archived_files.append(destination)

    script_data = dict(script_payload or {})
    job_data = dict(job_payload or {})
    script_folder = version_directory / "roteiro"
    script_folder.mkdir(parents=True, exist_ok=True)
    script_json = script_folder / "dados-do-roteiro.json"
    script_json.write_text(
        json.dumps(script_data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    archived_files.append(script_json)

    settings = job_data.get("productionSettings")
    settings = settings if isinstance(settings, dict) else {}
    display_text = str(
        settings.get("displayText")
        or settings.get("narrationText")
        or script_data.get("textoFalado")
        or ""
    ).strip()
    spoken_text = str(settings.get("spokenText") or display_text).strip()
    speech_file = script_folder / "fala-final.txt"
    speech_sections = [spoken_text]
    if display_text and display_text != spoken_text:
        speech_sections.extend(["", "--- TEXTO EXIBIDO ---", "", display_text])
    speech_file.write_text("\n".join(speech_sections).rstrip() + "\n", encoding="utf-8")
    archived_files.append(speech_file)

    manifest_path = version_directory / "metadados-da-geracao.json"
    relative_artifacts = [
        str(path.relative_to(version_directory))
        for path in archived_files
    ]
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": EXPORT_INDEX_SCHEMA_VERSION,
                "scriptId": script_id,
                "scriptTitle": script_title,
                "generationId": generation_id,
                "version": version,
                "generatedAt": generated_at,
                "sourceFilesPreserved": True,
                "artifacts": relative_artifacts,
                "job": job_data,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    archived_files.append(manifest_path)

    readme_path = version_directory / "LEIA-ME.txt"
    readme_path.write_text(
        (
            f"Roteiro: {script_title}\n"
            f"Versão: {version}\n"
            f"Geração: {generation_id}\n\n"
            "video-final.mp4: vídeo pronto para uso.\n"
            "tomadas/: arquivos separados usados na composição, quando disponíveis.\n"
            "legendas/: legendas SRT disponíveis.\n"
            "roteiro/: fala final e dados do roteiro.\n"
            "metadados-da-geracao.json: configurações e auditoria da geração.\n\n"
            "Os arquivos originais de produção foram preservados.\n"
        ),
        encoding="utf-8",
    )
    archived_files.append(readme_path)

    return ScriptExportResult(
        version=version,
        directory=version_directory,
        files=tuple(str(path.relative_to(version_directory)) for path in archived_files),
    )
