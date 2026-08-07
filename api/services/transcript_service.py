"""Reusable, versioned transcript extraction for Cuts and post-production."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


TRANSCRIPT_SCHEMA_VERSION = "transcript-v1"
TRANSCRIPT_NORMALIZATION_VERSION = "ptbr-medical-v1"


def transcription_python(project_root: Path) -> Path:
    """Resolve the isolated local runtime shared by Cuts and post-production."""
    configured = os.getenv("CUTS_PYTHON", "").strip()
    candidates = [
        *([Path(configured)] if configured else []),
        project_root / ".venv-cuts" / "bin" / "python",
        project_root / ".venv" / "bin" / "python",
        project_root.parent / "Video Creator" / ".venv_caption" / "bin" / "python",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        check = subprocess.run(
            [str(candidate), "-c", "import faster_whisper"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if check.returncode == 0:
            return candidate
    raise RuntimeError(
        "Transcrição indisponível. Execute ./tools/setup_cuts_env.sh ou configure CUTS_PYTHON "
        "com um Python que tenha faster-whisper instalado."
    )


def transcribe_video_to_file(
    video_path: Path,
    output_path: Path,
    *,
    project_root: Path,
    model_name: str = "small",
    timeout: int = 3600,
) -> dict[str, Any]:
    """Run transcription in the isolated runtime and return the versioned contract."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        [
            str(transcription_python(project_root)),
            str(project_root / "tools" / "transcribe_for_cuts.py"),
            str(video_path),
            str(output_path),
            "--model",
            model_name,
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "Falha na transcrição.")[-1200:])
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("A transcrição local não gerou um contrato JSON válido.") from exc


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_ptbr_medical_text(value: str) -> str:
    clean = clean_text(value)
    clean = re.sub(r"\bmonjaro\b", "Mounjaro", clean, flags=re.IGNORECASE)
    clean = re.sub(
        r"\bsintomas\s+em\s+comuns\b",
        "sintomas incomuns",
        clean,
        flags=re.IGNORECASE,
    )
    return clean


def _word_key(value: str) -> str:
    return re.sub(r"[^a-zà-ÿ]", "", value.casefold())


def video_fingerprint(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _milliseconds(value: Any) -> int:
    return max(0, round(float(value or 0) * 1000))


def normalize_transcript(
    *,
    video_path: Path,
    language: str,
    duration_seconds: float,
    raw_segments: Iterable[Any],
    model_version: str,
) -> dict[str, Any]:
    """Build the stable contract while preserving fields consumed by Cuts."""
    segments: list[dict[str, Any]] = []
    indexed_words: list[dict[str, Any]] = []
    for segment_index, raw_segment in enumerate(raw_segments):
        raw_text = raw_segment.get("text") if isinstance(raw_segment, dict) else raw_segment.text
        text = normalize_ptbr_medical_text(str(raw_text or ""))
        if not text:
            continue
        raw_words = raw_segment.get("words", []) if isinstance(raw_segment, dict) else (raw_segment.words or [])
        normalized_raw_words: list[dict[str, Any]] = []
        word_position = 0
        while word_position < len(raw_words):
            raw_word = raw_words[word_position]
            word_text = raw_word.get("text") if isinstance(raw_word, dict) else raw_word.word
            word_text = normalize_ptbr_medical_text(str(word_text or ""))
            if not word_text:
                word_position += 1
                continue
            start = raw_word.get("start") if isinstance(raw_word, dict) else raw_word.start
            end = raw_word.get("end") if isinstance(raw_word, dict) else raw_word.end
            if (
                _word_key(word_text) == "em"
                and normalized_raw_words
                and _word_key(normalized_raw_words[-1]["text"]) == "sintomas"
                and word_position + 1 < len(raw_words)
            ):
                next_word = raw_words[word_position + 1]
                next_text = next_word.get("text") if isinstance(next_word, dict) else next_word.word
                if _word_key(str(next_text or "")) == "comuns":
                    next_end = next_word.get("end") if isinstance(next_word, dict) else next_word.end
                    normalized_raw_words.append(
                        {"text": "incomuns", "start": start, "end": next_end if next_end is not None else end}
                    )
                    word_position += 2
                    continue
            normalized_raw_words.append({"text": word_text, "start": start, "end": end})
            word_position += 1

        words: list[dict[str, Any]] = []
        for normalized_word in normalized_raw_words:
            word_text = normalized_word["text"]
            start = normalized_word["start"]
            end = normalized_word["end"]
            index = len(indexed_words)
            word = {
                "index": index,
                "start": round(float(start or 0), 3),
                "end": round(float(end or start or 0), 3),
                "startMs": _milliseconds(start),
                "endMs": _milliseconds(end if end is not None else start),
                "text": word_text,
            }
            words.append(word)
            indexed_words.append({**word, "segmentIndex": segment_index})
        start = raw_segment.get("start") if isinstance(raw_segment, dict) else raw_segment.start
        end = raw_segment.get("end") if isinstance(raw_segment, dict) else raw_segment.end
        segments.append(
            {
                "index": segment_index,
                "start": round(float(start or 0), 3),
                "end": round(float(end or start or 0), 3),
                "startMs": _milliseconds(start),
                "endMs": _milliseconds(end if end is not None else start),
                "text": text,
                "words": words,
                "startWordIndex": words[0]["index"] if words else None,
                "endWordIndex": words[-1]["index"] if words else None,
            }
        )
    fingerprint = video_fingerprint(video_path)
    version_payload = json.dumps(
        {
            "schema": TRANSCRIPT_SCHEMA_VERSION,
            "normalization": TRANSCRIPT_NORMALIZATION_VERSION,
            "model": model_version,
            "video": fingerprint,
            "words": indexed_words,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schemaVersion": TRANSCRIPT_SCHEMA_VERSION,
        "normalizationVersion": TRANSCRIPT_NORMALIZATION_VERSION,
        "version": f"sha256:{hashlib.sha256(version_payload).hexdigest()}",
        "modelVersion": model_version,
        "videoFingerprint": fingerprint,
        "language": language or "pt",
        "duration": float(duration_seconds or 0),
        "durationMs": _milliseconds(duration_seconds),
        "segments": segments,
        "words": indexed_words,
        "text": " ".join(segment["text"] for segment in segments),
    }


def transcribe_video(video_path: Path, *, model_name: str = "small") -> dict[str, Any]:
    """Run local faster-whisper. Import stays lazy so fallback tests need no model."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="auto", compute_type="int8")
    raw_segments, info = model.transcribe(
        str(video_path),
        language="pt",
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )
    return normalize_transcript(
        video_path=video_path,
        language=str(getattr(info, "language", "pt") or "pt"),
        duration_seconds=float(getattr(info, "duration", 0) or 0),
        raw_segments=raw_segments,
        model_version=f"faster-whisper:{model_name}",
    )
