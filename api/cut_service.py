from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from api.job_store import JobStore


class CutCancelled(RuntimeError):
    pass


_PROCESS_LOCK = threading.Lock()
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_CANCEL_EVENTS: dict[str, threading.Event] = {}


def prepare_cut_job(job_id: str) -> None:
    with _PROCESS_LOCK:
        _CANCEL_EVENTS[job_id] = threading.Event()


def _cancel_event(job_id: str) -> threading.Event:
    with _PROCESS_LOCK:
        return _CANCEL_EVENTS.setdefault(job_id, threading.Event())


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()


def cancel_cut_job(job_id: str) -> bool:
    """Sinaliza cancelamento e encerra o subprocesso pesado do projeto."""
    with _PROCESS_LOCK:
        event = _CANCEL_EVENTS.setdefault(job_id, threading.Event())
        event.set()
        process = _ACTIVE_PROCESSES.get(job_id)
    if process:
        _terminate_process(process)
    return process is not None


def _finish_cut_job(job_id: str) -> None:
    with _PROCESS_LOCK:
        _ACTIVE_PROCESSES.pop(job_id, None)
        _CANCEL_EVENTS.pop(job_id, None)


def _check_cancelled(job_id: str) -> None:
    if _cancel_event(job_id).is_set():
        raise CutCancelled("Processamento interrompido pelo usuario.")


def _run_process(job_id: str, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    _check_cancelled(job_id)
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    with _PROCESS_LOCK:
        _ACTIVE_PROCESSES[job_id] = process
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
    finally:
        with _PROCESS_LOCK:
            if _ACTIVE_PROCESSES.get(job_id) is process:
                _ACTIVE_PROCESSES.pop(job_id, None)
    _check_cancelled(job_id)
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized[:60] or "corte"


def _caption_python(root: Path) -> Path:
    candidates = [
        Path(os.getenv("CUTS_PYTHON", "")),
        root / ".venv-cuts" / "bin" / "python",
        root.parent / "Video Creator" / ".venv_caption" / "bin" / "python",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return candidate
    raise RuntimeError(
        "Ambiente de transcricao nao encontrado. Configure CUTS_PYTHON ou crie .venv-cuts."
    )


def _download_source(job_id: str, url: str, destination: Path) -> None:
    temporary = destination.with_suffix(".part")
    with requests.get(url, stream=True, timeout=(20, 600)) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                _check_cancelled(job_id)
                if chunk:
                    output.write(chunk)
    temporary.replace(destination)


def _download_youtube(
    job_id: str,
    url: str,
    destination: Path,
    *,
    analysis_start: float = 0,
    analysis_end: float | None = None,
) -> None:
    args = [
            "yt-dlp",
            "--no-playlist",
            "--match-filter",
            "duration <= 7200",
            "--max-filesize",
            "2G",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "-f",
            "bv*[height<=1080]+ba/b[height<=1080]",
            "-o",
            str(destination),
        ]
    if analysis_end is not None:
        args.extend(["--download-sections", f"*{analysis_start:.3f}-{analysis_end:.3f}"])
    args.append(url)
    process = _run_process(job_id, args, timeout=1800)
    if process.returncode != 0 or not destination.is_file():
        detail = process.stderr or process.stdout or "Nao foi possivel baixar o video do YouTube."
        raise RuntimeError(detail[-1200:])


def _probe_duration(job_id: str, video: Path) -> float:
    process = _run_process(
        job_id,
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        timeout=60,
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or "Nao foi possivel ler o video.")[-500:])
    return float(process.stdout.strip())


def _trim_source(job_id: str, source: Path, destination: Path, start: float, end: float) -> None:
    duration = end - start
    process = _run_process(
        job_id,
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            str(destination),
        ],
        timeout=600,
    )
    if process.returncode != 0 or not destination.is_file():
        raise RuntimeError((process.stderr or "Nao foi possivel preparar o trecho.")[-1000:])


def _clip_schema(count: int | None) -> dict[str, Any]:
    min_items = 0 if count is None else count
    max_items = 8 if count is None else count
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "clips": {
                "type": "array",
                "minItems": min_items,
                "maxItems": max_items,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "score": {"type": "integer"},
                        "hook": {"type": "string"},
                        "summary": {"type": "string"},
                        "cta": {"type": "string"},
                        "caption": {"type": "string"},
                        "cover": {"type": "string"},
                        "hashtags": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "start",
                        "end",
                        "score",
                        "hook",
                        "summary",
                        "cta",
                        "caption",
                        "cover",
                        "hashtags",
                        "reason",
                    ],
                },
            }
        },
        "required": ["clips"],
    }


def _window_text(segments: list[dict[str, Any]], start: float, end: float) -> str:
    return " ".join(
        str(segment.get("text") or "").strip()
        for segment in segments
        if float(segment.get("end") or 0) > start and float(segment.get("start") or 0) < end
    ).strip()


def _content_words(text: str) -> set[str]:
    stopwords = {
        "a",
        "agora",
        "ainda",
        "ao",
        "aos",
        "as",
        "com",
        "como",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "ela",
        "ele",
        "em",
        "essa",
        "esse",
        "esta",
        "eu",
        "isso",
        "mais",
        "mas",
        "na",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "ou",
        "para",
        "por",
        "porque",
        "que",
        "se",
        "sem",
        "ser",
        "sua",
        "tem",
        "um",
        "uma",
        "voce",
    }
    return {
        word
        for word in re.findall(r"[a-zA-ZÀ-ÿ0-9-]{3,}", text.lower())
        if word not in stopwords
    }


def _editorial_score(
    text: str,
    *,
    duration: float,
    min_duration: int,
    max_duration: int,
    auto_duration: bool,
) -> tuple[int, str]:
    lowered = text.lower()
    opening = lowered[:180]
    signals: list[str] = []
    score = 48
    if "?" in text or any(
        term in opening
        for term in ("por que", "você sabia", "sabe qual", "o erro", "a verdade", "atenção")
    ):
        score += 14
        signals.append("abertura forte")
    if any(
        term in lowered
        for term in (
            "por isso",
            "significa",
            "resultado",
            "principal",
            "importante",
            "funciona",
            "evitar",
            "ajuda",
            "diferença",
        )
    ):
        score += 10
        signals.append("entrega uma ideia")
    if re.search(r"\b\d+\b", text):
        score += 5
        signals.append("informação específica")
    if text.rstrip().endswith((".", "!", "?")):
        score += 8
        signals.append("fechamento natural")
    if lowered.startswith(("e ", "mas ", "aí ", "então ", "ele ", "ela ", "isso ")):
        score -= 12
    word_count = len(text.split())
    if 24 <= word_count <= 125:
        score += 7
    elif word_count < 14:
        score -= 15
    if auto_duration:
        if 24 <= duration <= 45:
            score += 14
        elif 18 <= duration < 24:
            score += 6
        elif 45 < duration <= 60:
            score += 5
        elif duration < 18:
            score -= 16
        elif duration > 60:
            score -= round((duration - 60) * 0.9)
        else:
            score -= 4
    else:
        target = (min_duration + max_duration) / 2
        score -= round(abs(duration - target) * 0.35)
    reason = ", ".join(signals[:3]) or "fala clara com contexto suficiente"
    return max(30, min(96, score)), reason[0].upper() + reason[1:] + "."


def _bad_clip_start(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    first = stripped[:1]
    if first and first == first.lower() and first != first.upper():
        return True
    return lowered.startswith(
        (
            "beleza",
            "certo",
            "então",
            "entao",
            "e ",
            "mas ",
            "aí ",
            "ai ",
            "isso ",
            "ele ",
            "ela ",
            "pensando ",
            "na verdade ",
            "ou seja",
        )
    )


def _expand_auto_window(
    segments: list[dict[str, Any]],
    *,
    start_index: int,
    end_index: int,
    video_duration: float,
    min_duration: int,
    max_duration: int,
) -> tuple[int, int, float, float]:
    expanded_start = start_index
    expanded_end = end_index

    def bounds() -> tuple[float, float, float]:
        start = max(0.0, float(segments[expanded_start]["start"]))
        end = min(video_duration, float(segments[expanded_end]["end"]))
        return start, end, end - start

    while expanded_start > 0:
        current_text = " ".join(
            str(item.get("text") or "").strip()
            for item in segments[expanded_start : expanded_end + 1]
        )
        previous_text = str(segments[expanded_start - 1].get("text") or "").strip()
        previous_is_open_sentence = bool(previous_text) and not previous_text.endswith((".", "!", "?"))
        candidate_start = max(0.0, float(segments[expanded_start - 1]["start"]))
        _, end, _ = bounds()
        if end - candidate_start > max_duration:
            break
        if (
            _bad_clip_start(current_text)
            or previous_is_open_sentence
            or end - candidate_start <= max(min_duration, 24)
        ):
            expanded_start -= 1
            continue
        break

    while expanded_end + 1 < len(segments):
        start, _, current_duration = bounds()
        candidate_end = min(video_duration, float(segments[expanded_end + 1]["end"]))
        if candidate_end - start > max_duration:
            break
        if current_duration < max(min_duration, 28):
            expanded_end += 1
            continue
        break

    start, end, _ = bounds()
    return expanded_start, expanded_end, start, end


def _local_clip_suggestions(
    transcript: dict[str, Any],
    *,
    count: int | None,
    min_duration: int,
    max_duration: int,
    auto_duration: bool = False,
) -> list[dict[str, Any]]:
    segments = [segment for segment in transcript.get("segments", []) if segment.get("text")]
    duration = float(transcript.get("duration") or 0)
    if not segments or duration <= 0:
        raise RuntimeError("A transcricao nao encontrou fala suficiente para criar cortes.")

    candidates: list[dict[str, Any]] = []
    for start_index, segment in enumerate(segments):
        start = max(0.0, float(segment["start"]))
        for end_index in range(start_index, len(segments)):
            end = min(duration, float(segments[end_index]["end"]))
            candidate_duration = end - start
            if candidate_duration < min_duration:
                continue
            if candidate_duration > max_duration:
                break
            text = " ".join(
                str(item.get("text") or "").strip()
                for item in segments[start_index : end_index + 1]
            ).strip()
            if not text:
                continue
            effective_start_index = start_index
            effective_end_index = end_index
            if auto_duration:
                (
                    effective_start_index,
                    effective_end_index,
                    start,
                    end,
                ) = _expand_auto_window(
                    segments,
                    start_index=start_index,
                    end_index=end_index,
                    video_duration=duration,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )
                text = " ".join(
                    str(item.get("text") or "").strip()
                    for item in segments[effective_start_index : effective_end_index + 1]
                ).strip()
                candidate_duration = end - start
                if not text or candidate_duration < min_duration or candidate_duration > max_duration:
                    continue
            score, reason = _editorial_score(
                text,
                duration=candidate_duration,
                min_duration=min_duration,
                max_duration=max_duration,
                auto_duration=auto_duration,
            )
            title_words = re.sub(r"\s+", " ", text).strip(" .,!?:;").split()[:8]
            title = " ".join(title_words) + ("..." if len(text.split()) > 8 else "")
            candidates.append(
                {
                    "title": title[:80] or "Trecho em destaque",
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "score": score,
                    "hook": text[:180],
                    "summary": text[:320],
                    "cta": "Salve este trecho para rever depois.",
                    "caption": text[:500],
                    "cover": (title[:60] or "Trecho em destaque").upper(),
                    "hashtags": "#saude #bemestar #conteudoeducativo",
                    "reason": reason,
                    "_words": _content_words(text),
                    "_span": (effective_start_index, effective_end_index),
                }
            )

    unique_candidates: dict[tuple[int, int], dict[str, Any]] = {}
    for candidate in candidates:
        span = candidate["_span"]
        current = unique_candidates.get(span)
        if not current or int(candidate["score"]) > int(current["score"]):
            unique_candidates[span] = candidate

    ranked = sorted(
        unique_candidates.values(),
        key=lambda item: (-int(item["score"]), float(item["start"])),
    )[:800]
    if count is not None and len(ranked) < count:
        raise RuntimeError("O video nao possui fala suficiente para a quantidade de cortes pedida.")

    selected: list[dict[str, Any]] = []
    target_count = count or 8
    minimum_auto_score = 83
    while len(selected) < target_count:
        remaining = [candidate for candidate in ranked if candidate not in selected]
        if not remaining:
            break

        def adjusted_score(candidate: dict[str, Any]) -> float:
            if not selected:
                return float(candidate["score"])
            similarity = 0.0
            overlap = 0.0
            for current in selected:
                union = candidate["_words"] | current["_words"]
                if union:
                    similarity = max(
                        similarity,
                        len(candidate["_words"] & current["_words"]) / len(union),
                    )
                intersection = max(
                    0.0,
                    min(float(candidate["end"]), float(current["end"]))
                    - max(float(candidate["start"]), float(current["start"])),
                )
                shorter = min(
                    float(candidate["end"]) - float(candidate["start"]),
                    float(current["end"]) - float(current["start"]),
                )
                overlap = max(overlap, intersection / max(shorter, 0.1))
            return float(candidate["score"]) - similarity * 45 - overlap * 55

        best = max(remaining, key=lambda candidate: (adjusted_score(candidate), -candidate["start"]))
        if count is None and int(best["score"]) < minimum_auto_score:
            break
        selected.append(best)
    if count is not None and len(selected) < count:
        raise RuntimeError("O video nao possui fala suficiente para a quantidade de cortes pedida.")
    for candidate in selected:
        candidate.pop("_words", None)
        candidate.pop("_span", None)
    return selected


def _suggest_clips(
    transcript: dict[str, Any],
    *,
    count: int | None,
    min_duration: int,
    max_duration: int,
    auto_duration: bool = False,
    cache_get: Callable[[str, Any], dict[str, Any] | None] | None = None,
    cache_put: Callable[[str, Any, dict[str, Any]], None] | None = None,
    record_usage: Callable[[str, str, Any], None] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return (
            _local_clip_suggestions(
                transcript,
                count=count,
                min_duration=min_duration,
                max_duration=max_duration,
                auto_duration=auto_duration,
            ),
            "local",
        )

    import anthropic

    timeline = "\n".join(
        f"[{float(segment['start']):.2f}-{float(segment['end']):.2f}] {segment['text']}"
        for segment in transcript.get("segments", [])
    )
    if len(timeline) > 80000:
        timeline = timeline[:80000]
    quantity_rule = (
        "Escolha de 0 a 8 trechos. Se nenhum trecho tiver potencial viral real, retorne clips vazio."
        if count is None
        else f"Escolha exatamente {count} trechos independentes."
    )
    prompt = f"""Analise esta transcricao em portugues brasileiro.
{quantity_rule}

Regras:
- Cada trecho deve ter entre {min_duration} e {max_duration} segundos.
- Priorize somente potencial viral: hook forte, tensão, clareza, opinião memorável, quebra de expectativa ou utilidade imediata.
- Nao force cortes medianos apenas para preencher quantidade.
- {"Escolha livremente a duracao de cada corte pelo inicio e fechamento natural da ideia." if auto_duration else "Mantenha os cortes dentro da faixa solicitada, priorizando frases completas."}
- Use somente timestamps existentes e preserve frases completas.
- Evite sobreposicao entre os cortes.
- O trecho precisa comecar com contexto ou hook compreensivel.
- Para saude, nao transforme a fala em prescricao ou promessa.
- Score entre 0 e 100.
- CTA, legenda e hashtags sao sugestoes editoriais, nao devem inventar fatos.

TRANSCRICAO:
{timeline}"""
    cache_payload = {
        "timeline": timeline,
        "count": count,
        "minDuration": min_duration,
        "maxDuration": max_duration,
        "autoDuration": auto_duration,
    }
    if cache_get:
        cached = cache_get("cuts.suggest", cache_payload)
        if cached and isinstance(cached.get("clips"), list):
            return cached["clips"], "anthropic-cache"
    client = anthropic.Anthropic()
    model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    try:
        message = client.messages.create(
            model=model,
            max_tokens=4000,
            system="Voce e editor senior de videos curtos e conteudo medico responsavel.",
            output_config={"format": {"type": "json_schema", "schema": _clip_schema(count)}},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        detail = str(exc).lower()
        if "authentication" in detail or "api_key" in detail or "auth_token" in detail:
            return (
                _local_clip_suggestions(
                    transcript,
                    count=count,
                    min_duration=min_duration,
                    max_duration=max_duration,
                    auto_duration=auto_duration,
                ),
                "local",
            )
        raise
    raw = "".join(getattr(block, "text", "") for block in message.content)
    clips = json.loads(raw)["clips"]
    duration = float(transcript.get("duration") or 0)
    valid = []
    for clip in clips:
        start = max(0.0, float(clip["start"]))
        end = min(duration, float(clip["end"])) if duration else float(clip["end"])
        if end <= start:
            continue
        if end - start > max_duration:
            end = start + max_duration
        if end - start < min_duration:
            end = min(duration or start + min_duration, start + min_duration)
        clip["start"] = round(start, 3)
        clip["end"] = round(end, 3)
        clip["score"] = max(0, min(100, int(clip["score"])))
        valid.append(clip)
    if count is not None and len(valid) != count:
        raise RuntimeError("A analise nao retornou a quantidade esperada de cortes validos.")
    if record_usage:
        record_usage("cuts.suggest", model, message)
    if cache_put:
        cache_put("cuts.suggest", cache_payload, {"clips": valid})
    return valid, "anthropic"


def process_cut_project(
    *,
    store: JobStore,
    job_id: str,
    root: Path,
    output_root: Path,
    source_url: str | None,
    youtube_url: str | None,
    source_path: Path | None,
    compliance: Callable[[dict[str, Any]], dict[str, Any]],
    cache_get: Callable[[str, Any], dict[str, Any] | None] | None = None,
    cache_put: Callable[[str, Any, dict[str, Any]], None] | None = None,
    record_usage: Callable[[str, str, Any], None] | None = None,
) -> None:
    job = store.get("cut", job_id)
    if not job:
        return
    project_dir = output_root / job_id
    project_dir.mkdir(parents=True, exist_ok=True)
    source = project_dir / "source.mp4"
    settings = job["settings"]
    analysis_start = float(settings.get("analysisStartSeconds") or 0)
    analysis_end_raw = settings.get("analysisEndSeconds")
    analysis_end = float(analysis_end_raw) if analysis_end_raw is not None else None

    def update(**patch: Any) -> None:
        current = store.get("cut", job_id) or job
        current.update(patch)
        current["atualizadoEm"] = datetime.now(timezone.utc).isoformat()
        store.upsert("cut", current)

    try:
        _check_cancelled(job_id)
        update(status="processando", progresso=5, etapa="Preparando video")
        if analysis_end is not None and analysis_end <= analysis_start:
            raise RuntimeError("O fim do trecho deve ser posterior ao inicio.")

        if source_path or source_url:
            raw_source = project_dir / "source_full.mp4" if analysis_end is not None else source
            if source_path:
                shutil.copy2(source_path, raw_source)
            else:
                _download_source(job_id, str(source_url), raw_source)
            original_duration = _probe_duration(job_id, raw_source)
            if analysis_start >= original_duration:
                raise RuntimeError("O inicio escolhido fica depois do final do video.")
            if analysis_end is not None:
                effective_end = min(analysis_end, original_duration)
                update(progresso=12, etapa="Preparando trecho selecionado")
                _trim_source(job_id, raw_source, source, analysis_start, effective_end)
                update(duracaoOriginal=original_duration, analysisEndEffective=effective_end)
        elif youtube_url:
            update(progresso=8, etapa="Baixando video do YouTube")
            _download_youtube(
                job_id,
                youtube_url,
                source,
                analysis_start=analysis_start,
                analysis_end=analysis_end,
            )
        else:
            raise RuntimeError("Fonte do video nao encontrada.")
        duration = _probe_duration(job_id, source)
        update(progresso=18, etapa="Transcrevendo", duracaoFonte=duration)

        transcript_path = project_dir / "transcript.json"
        process = _run_process(
            job_id,
            [
                str(_caption_python(root)),
                str(root / "tools" / "transcribe_for_cuts.py"),
                str(source),
                str(transcript_path),
            ],
            timeout=3600,
        )
        if process.returncode != 0:
            raise RuntimeError((process.stderr or process.stdout or "Falha na transcricao.")[-1000:])
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        update(progresso=45, etapa="Escolhendo melhores trechos")

        clip_count = settings.get("clipCount")
        _check_cancelled(job_id)
        clips, selection_mode = _suggest_clips(
            transcript,
            count=int(clip_count) if clip_count is not None else None,
            min_duration=int(settings["minDuration"]),
            max_duration=int(settings["maxDuration"]),
            auto_duration=settings.get("durationMode") == "auto",
            cache_get=cache_get,
            cache_put=cache_put,
            record_usage=record_usage,
        )
        _check_cancelled(job_id)
        update(
            progresso=58,
            etapa="Renderizando cortes",
            clips=clips,
            selectionMode=selection_mode,
        )
        if not clips:
            update(
                status="pronto",
                progresso=100,
                etapa="Nenhum trecho com potencial viral suficiente",
                clips=[],
            )
            return

        caption_python = _caption_python(root)
        rendered = []
        for index, clip in enumerate(clips, start=1):
            filename = f"{index:02d}_{_slug(str(clip['title']))}.mp4"
            output = project_dir / filename
            config = {
                "source": str(source),
                "output": str(output),
                "transcript": str(transcript_path),
                "start": clip["start"],
                "end": clip["end"],
                "layout": settings["layout"],
                "captions": settings["captions"],
            }
            config_path = project_dir / f"render_{index:02d}.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            reusable = output.is_file() and output.stat().st_size > 100_000
            if not reusable:
                render = _run_process(
                    job_id,
                    [str(caption_python), str(root / "tools" / "render_cut.py"), str(config_path)],
                    timeout=1800,
                )
                if render.returncode != 0:
                    raise RuntimeError(
                        (render.stderr or render.stdout or "Falha ao renderizar.")[-1200:]
                    )
            clip["id"] = f"{job_id}-{index}"
            clip["filename"] = filename
            clip["duration"] = round(float(clip["end"]) - float(clip["start"]), 2)
            clip["compliance"] = compliance(
                {"hook": clip["hook"], "caption": clip["caption"], "cta": clip["cta"]}
            )
            rendered.append(clip)
            update(
                progresso=58 + round(index / len(clips) * 40),
                etapa=f"Renderizando corte {index} de {len(clips)}",
                clips=rendered,
            )
        update(status="pronto", progresso=100, etapa="Cortes prontos", clips=rendered)
    except CutCancelled:
        update(
            status="cancelado",
            progresso=0,
            etapa="Processamento interrompido",
            erro=None,
        )
    except Exception as exc:
        update(status="erro", progresso=0, etapa="Falha no processamento", erro=str(exc))
    finally:
        _finish_cut_job(job_id)
