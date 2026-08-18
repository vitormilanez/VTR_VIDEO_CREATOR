"""Deterministic capability discovery for local provider CLIs.

The registry is derived from the schemas shipped by the installed CLI. It does
not call a generation endpoint and it never guesses fields that are absent from
the provider contract.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable


PROVIDER_CAPABILITIES_SCHEMA_VERSION = "provider-capabilities-v1"

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(command: str, args: list[str], *, runner: Runner, timeout: int = 20) -> str:
    process = runner(
        [command, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "Falha ao consultar o CLI do provider.").strip()
        raise RuntimeError(detail[-500:])
    return (process.stdout or "").strip()


def heygen_cli_version(command: str, *, runner: Runner = subprocess.run) -> str:
    raw = _run(command, ["--version"], runner=runner)
    match = re.search(r"\bv?([0-9]+(?:\.[0-9]+){1,3})\b", raw)
    if not match:
        raise RuntimeError("O CLI do HeyGen não informou uma versão reconhecível.")
    return match.group(1)


def _request_schema(command: str, args: list[str], *, runner: Runner) -> dict[str, Any]:
    raw = _run(command, [*args, "--request-schema"], runner=runner)
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("O CLI do HeyGen retornou um schema inválido.") from exc
    if not isinstance(schema, dict):
        raise RuntimeError("O schema do HeyGen precisa ser um objeto JSON.")
    return schema


def _schema_hash(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _schema_nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _schema_nodes(child)


def _enum_values_for_property(schema: dict[str, Any], property_name: str) -> list[str]:
    values: set[str] = set()
    for node in _schema_nodes(schema):
        properties = node.get("properties")
        if not isinstance(properties, dict):
            continue
        definition = properties.get(property_name)
        if not isinstance(definition, dict):
            continue
        enum = definition.get("enum")
        if isinstance(enum, list):
            values.update(str(item) for item in enum if isinstance(item, str))
    return sorted(values)


def _top_level_properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _discriminator_values(schema: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for node in _schema_nodes(schema):
        discriminator = node.get("discriminator")
        mapping = discriminator.get("mapping") if isinstance(discriminator, dict) else None
        if isinstance(mapping, dict):
            values.update(str(key) for key in mapping)
    return values


def build_heygen_capabilities(
    *,
    cli_version: str,
    video_agent_schema: dict[str, Any],
    direct_video_schema: dict[str, Any],
) -> dict[str, Any]:
    agent_properties = _top_level_properties(video_agent_schema)
    schema_hashes = {
        "videoAgentCreate": _schema_hash(video_agent_schema),
        "directVideoCreate": _schema_hash(direct_video_schema),
    }
    capability_digest = hashlib.sha256(
        json.dumps(
            {
                "schemaVersion": PROVIDER_CAPABILITIES_SCHEMA_VERSION,
                "cliVersion": cli_version,
                "schemaHashes": schema_hashes,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    direct_types = sorted(
        str(key)
        for key in ((direct_video_schema.get("discriminator") or {}).get("mapping") or {}).keys()
    )
    engine_candidates = set(_enum_values_for_property(direct_video_schema, "type"))
    engine_candidates.update(_discriminator_values(direct_video_schema))
    return {
        "schemaVersion": PROVIDER_CAPABILITIES_SCHEMA_VERSION,
        "provider": "heygen",
        "cliVersion": cli_version,
        "capabilitiesVersion": f"heygen-{cli_version}-{capability_digest[:16]}",
        "schemaHashes": schema_hashes,
        "videoAgent": {
            "supported": "prompt" in agent_properties,
            "supportsStyleId": "style_id" in agent_properties,
            "supportsBrandKitId": "brand_kit_id" in agent_properties,
            "supportsChatMode": "chat" in _enum_values_for_property(video_agent_schema, "mode"),
            "supportsAttachments": "files" in agent_properties,
            "supportsIncognitoMode": "incognito_mode" in agent_properties,
            "orientations": _enum_values_for_property(video_agent_schema, "orientation"),
            "modes": _enum_values_for_property(video_agent_schema, "mode"),
        },
        "directVideo": {
            "supported": bool(direct_types),
            "types": direct_types,
            "supportedEngines": [
                value
                for value in sorted(engine_candidates)
                if re.fullmatch(r"avatar_(?:iii|iv|v)", value)
            ],
            "resolutions": _enum_values_for_property(direct_video_schema, "resolution"),
            "aspectRatios": _enum_values_for_property(direct_video_schema, "aspect_ratio"),
        },
    }


def inspect_heygen_capabilities(
    command: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    if not Path(command).name:
        raise RuntimeError("Caminho do CLI do HeyGen inválido.")
    cli_version = heygen_cli_version(command, runner=runner)
    return build_heygen_capabilities(
        cli_version=cli_version,
        video_agent_schema=_request_schema(command, ["video-agent", "create"], runner=runner),
        direct_video_schema=_request_schema(command, ["video", "create"], runner=runner),
    )


def validate_video_agent_options(
    capabilities: dict[str, Any],
    *,
    style_id: str | None,
    brand_kit_id: str | None,
    mode: str,
    files: list[dict[str, str]] | None = None,
    incognito_mode: bool = False,
) -> None:
    agent = capabilities.get("videoAgent") or {}
    if not agent.get("supported"):
        raise ValueError("O Video Agent não é suportado pelo CLI instalado.")
    if style_id and not agent.get("supportsStyleId"):
        raise ValueError("O CLI instalado não suporta styleId no Video Agent.")
    if brand_kit_id and not agent.get("supportsBrandKitId"):
        raise ValueError("O CLI instalado não suporta brandKitId no Video Agent.")
    if files and not agent.get("supportsAttachments"):
        raise ValueError("O CLI instalado não suporta anexos no Video Agent.")
    if incognito_mode and not agent.get("supportsIncognitoMode"):
        raise ValueError("O CLI instalado não suporta modo privado no Video Agent.")
    if mode not in set(agent.get("modes") or []):
        raise ValueError(f"O modo '{mode}' não é suportado pelo Video Agent instalado.")


def video_agent_create_args(
    capabilities: dict[str, Any],
    *,
    prompt: str,
    avatar_id: str,
    voice_id: str,
    orientation: str,
    style_id: str | None = None,
    brand_kit_id: str | None = None,
    mode: str = "generate",
    files: list[dict[str, str]] | None = None,
    incognito_mode: bool = False,
) -> list[str]:
    validate_video_agent_options(
        capabilities,
        style_id=style_id,
        brand_kit_id=brand_kit_id,
        mode=mode,
        files=files,
        incognito_mode=incognito_mode,
    )
    orientations = set((capabilities.get("videoAgent") or {}).get("orientations") or [])
    if orientation not in orientations:
        raise ValueError(f"A orientação '{orientation}' não é suportada pelo Video Agent instalado.")
    args = [
        "video-agent",
        "create",
        "--prompt",
        prompt,
        "--avatar-id",
        avatar_id,
        "--voice-id",
        voice_id,
        "--orientation",
        orientation,
        "--mode",
        mode,
    ]
    if style_id:
        args.extend(["--style-id", style_id])
    if brand_kit_id:
        args.extend(["--brand-kit-id", brand_kit_id])
    if files:
        args.extend(["--data", json.dumps({"files": files}, separators=(",", ":"))])
    if incognito_mode:
        args.append("--incognito-mode")
    return args
