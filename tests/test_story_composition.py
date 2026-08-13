from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api import server
from tests.test_story_shot_generation import authorization, payload, seed_story


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is required")


def mock_video(path: Path, color: str, frequency: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_story_composition_uses_completed_shots_in_order() -> None:
    with tempfile.TemporaryDirectory(dir=server.ROOT / "data") as temporary:
        root = Path(temporary)
        original_database = server.OPERATIONAL_DB
        original_outputs = server.COMPOSED_VIDEO_OUTPUTS
        original_exports = server.SCRIPT_EXPORTS
        server.OPERATIONAL_DB = root / "operations.db"
        server.COMPOSED_VIDEO_OUTPUTS = root / "composed"
        server.SCRIPT_EXPORTS = root / "Exports" / "roteiro"
        try:
            project, version = seed_story()
            context = authorization(project, version)
            shots = server._story_shots(version["id"])
            provider = MagicMock(
                side_effect=[{"session_id": "provider-01"}, {"session_id": "provider-02"}]
            )
            with (
                patch.object(server, "_authorize_story_production", return_value=context),
                patch.object(server, "_story_provider_submit", provider),
            ):
                generations = [
                    server.generate_story_shot(
                        shot["id"], payload(shot, version, f"compose-{shot['shotId']}")
                    )["generation"]
                    for shot in shots
                ]
                for index, generation in enumerate(generations):
                    shot_path = root / f"shot-{index + 1}.mp4"
                    mock_video(shot_path, "red" if index == 0 else "green", 250 + index * 100)
                    server._set_story_generation(
                        generation["id"],
                        status="completed",
                        output_path=str(shot_path.relative_to(server.ROOT)),
                    )

                narration = root / "narration.mp4"
                mock_video(narration, "blue", 900)
                server._job_store().upsert(
                    "video",
                    {
                        "id": "base-narration",
                        "scriptId": "script-story",
                        "status": "pronto",
                        "provider": "local",
                        "progresso": 100,
                        "criadoEm": "2026-08-09T00:00:00+00:00",
                        "atualizadoEm": "2026-08-09T00:00:01+00:00",
                        "outputPath": str(narration.relative_to(server.ROOT)),
                        "captionSrt": "1\n00:00:00,000 --> 00:00:02,000\nNarração principal\n",
                    },
                )
                job = server._compose_story_video(
                    version["id"],
                    server.StoryComposeIn(
                        expectedStoryHash=version["storyHash"], confirmed=True
                    ),
                )

            assert job["status"] == "pronto"
            assert job["narrationPolicy"] == "base_audio_continuous"
            assert [shot["shotId"] for shot in job["storyShots"]] == ["shot-01", "shot-02"]
            assert all(shot["generatedAudioMuted"] for shot in job["storyShots"])
            assert (server.ROOT / job["outputPath"]).is_file()
            assert job["exportVersion"] == "1.1"
            export_directory = server.ROOT / job["exportPath"]
            assert (export_directory / "video-final.mp4").is_file()
            assert len(list((export_directory / "tomadas").glob("*.mp4"))) == 3
            project_after = server._story_project("script-story")
            assert project_after["activeVersion"]["composition"]["id"] == job["id"]
        finally:
            server.OPERATIONAL_DB = original_database
            server.COMPOSED_VIDEO_OUTPUTS = original_outputs
            server.SCRIPT_EXPORTS = original_exports
