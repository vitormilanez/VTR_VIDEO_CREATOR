"""Contrato determinístico para podcasts com dois avatares.

O plano mantém a autoria de cada fala. Cada request resultante contém um único
avatar, uma única voz e um único trecho, de modo que o lip-sync nunca precise
ser trocado na pós-produção.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


PodcastSpeakerId = Literal["a", "b"]
PodcastSpeechMode = Literal["natural", "fiel", "direto", "enfatico"]
PodcastVoiceMood = Literal["confident", "upbeat", "warm", "serious", "neutral"]
PodcastOrientation = Literal["portrait", "landscape"]

PODCAST_SPEAKERS = frozenset({"a", "b"})
PODCAST_SPEECH_MODES = frozenset({"natural", "fiel", "direto", "enfatico"})
PODCAST_VOICE_MOODS = frozenset({"confident", "upbeat", "warm", "serious", "neutral"})
PODCAST_ORIENTATIONS = frozenset({"portrait", "landscape"})


@dataclass(frozen=True)
class PodcastGenerationRequest:
    turn_id: str
    order: int
    speaker_id: PodcastSpeakerId
    speaker_name: str
    avatar_id: str
    voice_id: str
    spoken_text: str
    speech_mode: PodcastSpeechMode
    voice_mood: PodcastVoiceMood
    orientation: PodcastOrientation

    def to_dict(self) -> dict[str, Any]:
        return {
            "turnId": self.turn_id,
            "order": self.order,
            "speakerId": self.speaker_id,
            "speakerName": self.speaker_name,
            "avatarId": self.avatar_id,
            "voiceId": self.voice_id,
            "spokenText": self.spoken_text,
            "speechMode": self.speech_mode,
            "voiceMood": self.voice_mood,
            "orientation": self.orientation,
        }


@dataclass(frozen=True)
class PodcastGenerationResult:
    script_id: str
    requests: tuple[PodcastGenerationRequest, ...]

    @property
    def turn_count(self) -> int:
        return len(self.requests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scriptId": self.script_id,
            "status": "not_submitted",
            "provider": "heygen",
            "turnCount": self.turn_count,
            "estimatedCalls": self.turn_count,
            "requiresExplicitConfirmation": True,
            "warning": (
                "Cada fala representa uma chamada HeyGen potencial; "
                "nenhum job foi criado."
            ),
            "requests": [request.to_dict() for request in self.requests],
        }


def podcast_spoken_text(plan: Mapping[str, Any]) -> str:
    raw_turns = plan.get("turns")
    if not isinstance(raw_turns, list):
        return ""
    return "\n\n".join(
        str(turn.get("text") or turn.get("spokenText") or "").strip()
        for turn in raw_turns
        if isinstance(turn, Mapping)
        and str(turn.get("text") or turn.get("spokenText") or "").strip()
    )


def build_podcast_generation_result(
    *,
    script_id: str,
    podcast_plan: Mapping[str, Any],
    speech_mode: str = "natural",
    voice_mood: str = "confident",
    orientation: str | None = None,
) -> PodcastGenerationResult:
    if not script_id.strip():
        raise ValueError("script_id é obrigatório.")
    if speech_mode not in PODCAST_SPEECH_MODES:
        raise ValueError(f"speech_mode inválido: {speech_mode}")
    if voice_mood not in PODCAST_VOICE_MOODS:
        raise ValueError(f"voice_mood inválido: {voice_mood}")
    resolved_orientation = str(orientation or podcast_plan.get("orientation") or "portrait")
    if resolved_orientation not in PODCAST_ORIENTATIONS:
        raise ValueError(f"orientation inválida: {resolved_orientation}")

    raw_participants = podcast_plan.get("participants")
    if not isinstance(raw_participants, list) or len(raw_participants) != 2:
        raise ValueError("O podcast precisa conter exatamente dois participantes.")

    participants: dict[str, dict[str, str]] = {}
    for index, raw_participant in enumerate(raw_participants, start=1):
        if not isinstance(raw_participant, Mapping):
            raise ValueError(f"Participante {index} inválido.")
        speaker_id = str(raw_participant.get("id") or "").strip()
        if speaker_id not in PODCAST_SPEAKERS or speaker_id in participants:
            raise ValueError("Os participantes precisam usar os identificadores a e b.")
        participant = {
            "id": speaker_id,
            "name": str(raw_participant.get("name") or "").strip(),
            "avatarId": str(raw_participant.get("avatarId") or "").strip(),
            "voiceId": str(raw_participant.get("voiceId") or "").strip(),
        }
        if not participant["name"]:
            raise ValueError(f"O participante {speaker_id.upper()} está sem nome.")
        if not participant["avatarId"]:
            raise ValueError(f"O participante {speaker_id.upper()} está sem avatar.")
        if not participant["voiceId"]:
            raise ValueError(f"O participante {speaker_id.upper()} está sem voz.")
        participants[speaker_id] = participant

    if len({participant["avatarId"] for participant in participants.values()}) != 2:
        raise ValueError("Cada participante precisa usar um avatar diferente.")
    if len({participant["voiceId"] for participant in participants.values()}) != 2:
        raise ValueError("Cada participante precisa usar uma voz diferente.")

    raw_turns = podcast_plan.get("turns")
    if not isinstance(raw_turns, list) or not 2 <= len(raw_turns) <= 30:
        raise ValueError("O podcast precisa conter entre 2 e 30 falas.")

    requests: list[PodcastGenerationRequest] = []
    seen_ids: set[str] = set()
    speakers_used: set[str] = set()
    for index, raw_turn in enumerate(raw_turns, start=1):
        if not isinstance(raw_turn, Mapping):
            raise ValueError(f"Fala {index} inválida.")
        turn_id = str(raw_turn.get("id") or raw_turn.get("turnId") or f"turn-{index}").strip()
        speaker_id = str(raw_turn.get("speakerId") or "").strip()
        spoken_text = str(raw_turn.get("text") or raw_turn.get("spokenText") or "").strip()
        if not turn_id or turn_id in seen_ids:
            raise ValueError(f"ID duplicado ou vazio na fala {index}.")
        if speaker_id not in participants:
            raise ValueError(f"A fala {index} não possui um participante válido.")
        if not spoken_text:
            raise ValueError(f"A fala {index} está vazia.")
        seen_ids.add(turn_id)
        speakers_used.add(speaker_id)
        participant = participants[speaker_id]
        requests.append(
            PodcastGenerationRequest(
                turn_id=turn_id,
                order=index,
                speaker_id=speaker_id,  # type: ignore[arg-type]
                speaker_name=participant["name"],
                avatar_id=participant["avatarId"],
                voice_id=participant["voiceId"],
                spoken_text=spoken_text,
                speech_mode=speech_mode,  # type: ignore[arg-type]
                voice_mood=voice_mood,  # type: ignore[arg-type]
                orientation=resolved_orientation,  # type: ignore[arg-type]
            )
        )

    if speakers_used != PODCAST_SPEAKERS:
        raise ValueError("Os dois participantes precisam ter ao menos uma fala.")
    return PodcastGenerationResult(script_id=script_id.strip(), requests=tuple(requests))
