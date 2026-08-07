"""Contexto editorial e identidade herdada pelo Pack de Conteúdo."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


PACK_CONTEXT_VERSION = "pack-context-v1"


def pack_identity(profile: Mapping[str, Any], avatar_set: Mapping[str, Any] | None) -> dict[str, Any]:
    mode = str(profile.get("avatarMode") or "single")
    looks = [
        {
            "role": str(look.get("role") or ""),
            "avatarId": str(look.get("avatarId") or ""),
        }
        for look in (avatar_set or {}).get("looks", [])
        if isinstance(look, Mapping) and look.get("avatarId")
    ]
    primary_avatar_id = str(
        profile.get("primaryAvatarId") or profile.get("avatarId") or (looks[0]["avatarId"] if looks else "")
    )
    return {
        "avatarMode": mode,
        "avatarSetId": str(profile.get("avatarSetId") or "") if mode == "set" else "",
        "primaryAvatarId": primary_avatar_id,
        "voiceId": str(profile.get("voiceId") or ""),
        "looks": looks,
    }


def identity_key(identity: Mapping[str, Any]) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def build_pack_context(
    *,
    script: Mapping[str, Any],
    profile: Mapping[str, Any],
    avatar_set: Mapping[str, Any] | None,
    design_system: Mapping[str, Any],
    compliance_rules: list[Mapping[str, Any]],
) -> dict[str, Any]:
    identity = pack_identity(profile, avatar_set)
    context = {
        "version": PACK_CONTEXT_VERSION,
        "idea": {
            "ideaId": script.get("ideaId"),
            "tema": script.get("tema"),
            "formatoSugerido": script.get("formatoSugerido"),
        },
        "script": dict(script),
        "performance": {
            "displayText": script.get("textoFalado") or "",
            "speechMode": profile.get("speechMode") or "natural",
            "generationMode": profile.get("generationMode") or "direct",
        },
        "avatarSet": dict(avatar_set) if avatar_set else {"mode": "single", "identity": identity},
        "identity": identity,
        "designSystem": dict(design_system),
        "compliance": list(compliance_rules),
    }
    context["identityKey"] = identity_key(identity)
    return context

