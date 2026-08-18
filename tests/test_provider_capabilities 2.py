from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import pytest

from api import server
from api.services.provider_capabilities import (
    build_heygen_capabilities,
    inspect_heygen_capabilities,
    video_agent_create_args,
)


VIDEO_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "avatar_id": {"type": "string"},
        "voice_id": {"type": "string"},
        "orientation": {"type": "string", "enum": ["portrait", "landscape"]},
        "mode": {"type": "string", "enum": ["generate", "chat"]},
        "style_id": {"type": "string"},
        "brand_kit_id": {"type": "string"},
        "files": {"type": "array"},
        "incognito_mode": {"type": "boolean"},
    },
    "required": ["prompt"],
}

DIRECT_SCHEMA = {
    "type": "object",
    "discriminator": {
        "propertyName": "type",
        "mapping": {"avatar": "#/avatar", "image": "#/image", "studio": "#/studio"},
    },
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["avatar"]},
                "engine": {
                    "discriminator": {
                        "propertyName": "type",
                        "mapping": {"avatar_iv": "#/iv", "avatar_v": "#/v"},
                    },
                    "oneOf": [
                        {"properties": {"type": {"enum": ["avatar_iv"]}}},
                        {"properties": {"type": {"enum": ["avatar_v"]}}},
                    ]
                },
                "resolution": {"enum": ["720p", "1080p"]},
                "aspect_ratio": {"enum": ["9:16", "16:9"]},
            },
        }
    ],
}


def capabilities() -> dict:
    return build_heygen_capabilities(
        cli_version="0.5.0",
        video_agent_schema=VIDEO_AGENT_SCHEMA,
        direct_video_schema=DIRECT_SCHEMA,
    )


def test_registry_is_derived_from_cli_schemas() -> None:
    registry = capabilities()

    assert registry["videoAgent"] == {
        "supported": True,
        "supportsStyleId": True,
        "supportsBrandKitId": True,
        "supportsChatMode": True,
        "supportsAttachments": True,
        "supportsIncognitoMode": True,
        "orientations": ["landscape", "portrait"],
        "modes": ["chat", "generate"],
    }
    assert registry["directVideo"]["supportedEngines"] == ["avatar_iv", "avatar_v"]
    assert registry["capabilitiesVersion"].startswith("heygen-0.5.0-")


def test_inspection_uses_only_version_and_request_schema_commands() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-1] == "--version":
            output = "heygen version v0.5.0"
        elif command[1:3] == ["video-agent", "create"]:
            output = json.dumps(VIDEO_AGENT_SCHEMA)
        else:
            output = json.dumps(DIRECT_SCHEMA)
        return subprocess.CompletedProcess(command, 0, output, "")

    result = inspect_heygen_capabilities("/tmp/heygen", runner=runner)

    assert result["cliVersion"] == "0.5.0"
    assert calls == [
        ["/tmp/heygen", "--version"],
        ["/tmp/heygen", "video-agent", "create", "--request-schema"],
        ["/tmp/heygen", "video", "create", "--request-schema"],
    ]


def test_transport_sends_confirmed_style_brand_and_chat_fields() -> None:
    args = video_agent_create_args(
        capabilities(),
        prompt="Uma história aprovada.",
        avatar_id="avatar-1",
        voice_id="voice-1",
        orientation="portrait",
        style_id="style-1",
        brand_kit_id="brand-1",
        mode="chat",
        files=[{"type": "asset_id", "asset_id": "asset-1"}],
        incognito_mode=True,
    )

    assert args[0:2] == ["video-agent", "create"]
    assert args[args.index("--style-id") + 1] == "style-1"
    assert args[args.index("--brand-kit-id") + 1] == "brand-1"
    assert args[args.index("--mode") + 1] == "chat"
    assert json.loads(args[args.index("--data") + 1]) == {
        "files": [{"type": "asset_id", "asset_id": "asset-1"}]
    }
    assert "--incognito-mode" in args


def test_transport_rejects_unconfirmed_fields() -> None:
    registry = capabilities()
    registry["videoAgent"]["supportsStyleId"] = False

    with pytest.raises(ValueError, match="styleId"):
        video_agent_create_args(
            registry,
            prompt="História",
            avatar_id="avatar-1",
            voice_id="voice-1",
            orientation="portrait",
            style_id="unknown-style",
        )


def test_agent_prompt_carries_duration_seedance_and_editing_instructions() -> None:
    prompt, input_mode = server._compose_video_agent_prompt(
        "Explique o tema aprovado sem criar novas alegações.",
        None,
        90,
        "confident",
        visual_mode="seedance",
        agent_instructions="Use cortes rápidos e gráficos médicos discretos.",
    )

    assert "around 90 seconds" in prompt
    assert "AI-generated cinematic animated visuals" in prompt
    assert "Use cortes rápidos e gráficos médicos discretos." in prompt
    assert input_mode == "approved_text_plus_voice_direction"


def test_server_persists_registry_and_reuses_same_cli_version() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        original_database = server.OPERATIONAL_DB
        server.OPERATIONAL_DB = Path(temporary) / "operations.db"
        try:
            with (
                patch.object(server, "_heygen_cli_binary", return_value="heygen"),
                patch.object(server, "heygen_cli_version", return_value="0.5.0"),
                patch.object(server, "inspect_heygen_capabilities", return_value=capabilities()) as inspect,
            ):
                first = server._heygen_capabilities()
                second = server._heygen_capabilities()
        finally:
            server.OPERATIONAL_DB = original_database

    assert first["capabilitiesVersion"] == second["capabilitiesVersion"]
    assert inspect.call_count == 1


def test_direct_mode_blocks_video_agent_only_fields_before_reservation() -> None:
    payload = server.VideoCreateIn(
        scriptId="script-direct",
        generationMode="direct",
        styleId="style-1",
    )
    with patch.object(server, "_find_script") as find_script:
        with pytest.raises(server.HTTPException) as raised:
            server.create_video(payload)

    assert raised.value.status_code == 422
    find_script.assert_not_called()


def test_reserved_video_agent_job_requires_its_capability_snapshot() -> None:
    narration = (
        "Este conteúdo educativo explica por que cada decisão de saúde precisa "
        "de avaliação individual com profissional qualificado."
    )
    payload = server.VideoCreateIn(
        scriptId="script-agent",
        generationMode="video_agent",
        avatarId="avatar-1",
        voiceId="voice-1",
        narrationText=narration,
        displayText=narration,
        spokenText=narration,
        outroText="",
    )
    job = {"id": "video-agent", "productionSettings": {}}

    with (
        patch.object(server, "_heygen_cli", return_value="heygen"),
        patch.object(server, "_heygen_wallet", return_value=(10.0, "usd")),
        patch.object(
            server,
            "_private_avatar_library",
            return_value=([], [{"id": "avatar-1", "status": "completed"}], False),
        ),
        patch.object(server, "_heygen_capabilities") as inspect,
        patch.object(server, "_run_heygen_json") as submit,
    ):
        with pytest.raises(server.HTTPException) as raised:
            server._create_video_job(
                payload,
                job,
                script={"id": payload.scriptId, "status": "aprovado_clinicamente"},
                final_texts=(narration, narration),
            )

    assert raised.value.status_code == 409
    inspect.assert_not_called()
    submit.assert_not_called()
