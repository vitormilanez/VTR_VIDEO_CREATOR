from __future__ import annotations

from typing import Any, Literal

from api.services.script_performance import display_text, speech_preset, spoken_text
from api.services.voice_providers import get_voice_provider


GenerationMode = Literal["direct", "video_agent"]

DIRECT_VIDEO_DURATIONS = frozenset({10, 15, 30, 45, 60})


def direct_video_payload(
    *,
    script: dict[str, Any],
    narration_text: str,
    avatar_id: str,
    voice_id: str,
    orientation: str,
    speech_mode: str,
    captions: bool,
    optimize_pronunciation: bool,
    caption_source_matches_spoken: bool = True,
) -> dict[str, Any]:
    voice_provider = get_voice_provider("heygen_text")
    voice_payload = voice_provider.build_voice_payload(
        text=spoken_text(narration_text, optimize_pronunciation=optimize_pronunciation),
        voice_id=voice_id,
        voice_settings=speech_preset(speech_mode),
    )
    payload: dict[str, Any] = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "title": str(script.get("titulo") or "AI Video Creator - video"),
        "aspect_ratio": "9:16" if orientation == "portrait" else "16:9",
        "resolution": "720p",
        "output_format": "mp4",
        "engine": {"type": "avatar_iv"},
        **voice_payload,
    }
    if captions:
        # HeyGen emits an SRT sidecar. When editorial and phonetic scripts differ,
        # callers keep it out of the rendered image and normalize it before use.
        payload["caption"] = {"file_format": "srt"}
        if not caption_source_matches_spoken:
            payload["caption"]["burned_in"] = False
    return payload


def normalize_caption_srt(srt: str) -> str:
    """Restores editorial spellings in an SRT generated from phonetic TTS text."""
    return display_text(srt)
