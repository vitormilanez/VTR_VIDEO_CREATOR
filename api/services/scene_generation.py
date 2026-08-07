"""Contrato local para futura geração de vídeos HeyGen por cena.

Este módulo não conhece CLI, HTTP ou credenciais. Ele apenas transforma um
Scene Plan já resolvido em requests determinísticos, deixando a submissão para
um adaptador futuro e explícito.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


SceneSpeechMode = Literal["natural", "fiel", "direto", "enfatico"]
SceneOrientation = Literal["portrait", "landscape"]
SCENE_SPEECH_MODES = frozenset({"natural", "fiel", "direto", "enfatico"})
SCENE_ORIENTATIONS = frozenset({"portrait", "landscape"})


@dataclass(frozen=True)
class SceneGenerationRequest:
    """Um futuro request HeyGen: um look fica fixo durante toda a cena."""

    scene_id: str
    order: int
    avatar_id: str
    voice_id: str
    spoken_text: str
    speech_mode: SceneSpeechMode
    orientation: SceneOrientation

    def to_dict(self) -> dict[str, Any]:
        return {
            "sceneId": self.scene_id,
            "order": self.order,
            "avatarId": self.avatar_id,
            "voiceId": self.voice_id,
            "spokenText": self.spoken_text,
            "speechMode": self.speech_mode,
            "orientation": self.orientation,
        }


@dataclass(frozen=True)
class SceneGenerationResult:
    """Plano pronto para submissão futura, ainda sem nenhuma chamada paga."""

    script_id: str
    status: Literal["not_submitted"]
    provider: Literal["heygen"]
    requests: tuple[SceneGenerationRequest, ...]

    @property
    def scene_count(self) -> int:
        return len(self.requests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scriptId": self.script_id,
            "status": self.status,
            "provider": self.provider,
            "sceneCount": self.scene_count,
            "requests": [request.to_dict() for request in self.requests],
        }


def build_scene_generation_result(
    *,
    script_id: str,
    scene_plan: Mapping[str, Any],
    voice_id: str,
    speech_mode: str = "natural",
    orientation: str = "portrait",
    spoken_text_by_scene: Mapping[str, str] | None = None,
) -> SceneGenerationResult:
    """Constrói o contrato por cena sem submeter nada ao provedor.

    ``spoken_text_by_scene`` permite que a etapa futura use a fala naturalizada
    exata. Enquanto a divisão ainda não carrega essa informação, o texto do
    Scene Plan é usado como fallback explícito.
    """
    if not script_id.strip():
        raise ValueError("script_id é obrigatório.")
    if not voice_id.strip():
        raise ValueError("voice_id é obrigatório para todas as cenas.")
    if speech_mode not in SCENE_SPEECH_MODES:
        raise ValueError(f"speech_mode inválido: {speech_mode}")
    if orientation not in SCENE_ORIENTATIONS:
        raise ValueError(f"orientation inválida: {orientation}")

    raw_scenes = scene_plan.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("O Scene Plan precisa conter pelo menos uma cena.")

    requests: list[SceneGenerationRequest] = []
    seen_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, Mapping):
            raise ValueError(f"Cena {index} inválida.")
        scene_id = str(raw_scene.get("id") or raw_scene.get("sceneId") or f"scene-{index}").strip()
        avatar_id = str(raw_scene.get("avatarId") or "").strip()
        if not scene_id or scene_id in seen_ids:
            raise ValueError(f"ID duplicado ou vazio na cena {index}.")
        if not avatar_id:
            raise ValueError(f"A cena {index} não possui avatarId resolvido.")
        seen_ids.add(scene_id)
        source_text = str(raw_scene.get("spokenText") or raw_scene.get("text") or "").strip()
        spoken_text = str((spoken_text_by_scene or {}).get(scene_id) or source_text).strip()
        if not spoken_text:
            raise ValueError(f"A cena {index} não possui spokenText.")
        requests.append(
            SceneGenerationRequest(
                scene_id=scene_id,
                order=index,
                avatar_id=avatar_id,
                voice_id=voice_id.strip(),
                spoken_text=spoken_text,
                speech_mode=speech_mode,  # type: ignore[arg-type]
                orientation=orientation,  # type: ignore[arg-type]
            )
        )
    return SceneGenerationResult(
        script_id=script_id.strip(),
        status="not_submitted",
        provider="heygen",
        requests=tuple(requests),
    )
