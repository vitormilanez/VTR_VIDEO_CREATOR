from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class VoiceProvider(Protocol):
    name: str

    def build_voice_payload(
        self,
        *,
        text: str,
        voice_id: str,
        voice_settings: dict[str, Any],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class HeyGenTextVoiceProvider:
    name: str = "heygen_text"

    def build_voice_payload(
        self,
        *,
        text: str,
        voice_id: str,
        voice_settings: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "script": text,
            "voice_id": voice_id,
            "voice_settings": voice_settings,
        }


@dataclass(frozen=True)
class ExternalAudioVoiceProvider:
    name: str = "external_audio"

    def build_voice_payload(
        self,
        *,
        text: str,
        voice_id: str,
        voice_settings: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError("Audio externo ainda nao esta habilitado.")


@dataclass(frozen=True)
class ElevenLabsVoiceProvider(ExternalAudioVoiceProvider):
    name: str = "elevenlabs"


def get_voice_provider(provider: str = "heygen_text", *, elevenlabs_enabled: bool = False) -> VoiceProvider:
    if provider == "elevenlabs":
        if not elevenlabs_enabled:
            raise RuntimeError("ElevenLabs esta desabilitado por feature flag.")
        return ElevenLabsVoiceProvider()
    if provider == "external_audio":
        return ExternalAudioVoiceProvider()
    return HeyGenTextVoiceProvider()
