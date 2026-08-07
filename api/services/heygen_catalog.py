from __future__ import annotations

from typing import Any


def _text(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def avatar_type(value: dict[str, Any]) -> str | None:
    return _text(value.get("avatar_type") or value.get("type") or value.get("avatarType"))


def default_voice_id(value: dict[str, Any]) -> str | None:
    return _text(value.get("default_voice_id") or value.get("defaultVoiceId") or value.get("voice_id"))


def supports_direct_avatar(value: dict[str, Any]) -> bool:
    raw = value.get("supported_generation_modes") or value.get("supportedGenerationModes")
    if isinstance(raw, list):
        return any(str(item).lower() in {"direct", "avatar", "avatar_video"} for item in raw)
    unsupported = str(value.get("status") or "").lower() not in {"completed", "ready"}
    return not unsupported


def normalize_avatar_look(look: dict[str, Any]) -> dict[str, Any] | None:
    avatar_id = _text(look.get("id"))
    if not avatar_id:
        return None
    orientation = "landscape" if look.get("preferred_orientation") == "landscape" else "portrait"
    return {
        "id": avatar_id,
        "name": _text(look.get("name")) or "Avatar sem nome",
        "type": avatar_type(look),
        "orientation": orientation,
        "status": _text(look.get("status")),
        "groupId": _text(look.get("group_id")),
        "groupName": _text(look.get("group_name")),
        "previewImageUrl": _text(look.get("preview_image_url")),
        "previewVideoUrl": _text(look.get("preview_video_url")),
        "defaultVoiceId": default_voice_id(look),
        "supportsDirectAvatar": supports_direct_avatar(look),
        "supportsVideoAgent": True,
    }


def build_catalog(
    looks: list[dict[str, Any]],
    voices: list[dict[str, Any]],
) -> dict[str, Any]:
    avatars = [
        avatar
        for look in looks
        if (avatar := normalize_avatar_look(look)) and avatar["status"] == "completed"
    ]
    normalized_voices = [dict(voice) for voice in voices]
    known_voice_ids = {str(voice.get("id") or "") for voice in normalized_voices}
    for avatar in avatars:
        voice_id = str(avatar.get("defaultVoiceId") or "")
        if voice_id and voice_id not in known_voice_ids:
            normalized_voices.append(
                {"id": voice_id, "name": f"Voz de {avatar['name']}", "gender": ""}
            )
            known_voice_ids.add(voice_id)
    return {
        "avatars": avatars,
        "voices": normalized_voices,
        "defaultAvatarId": None,
        "defaultVoiceId": normalized_voices[0]["id"] if normalized_voices else None,
    }
