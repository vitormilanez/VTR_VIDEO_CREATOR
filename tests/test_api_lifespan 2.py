from __future__ import annotations

import asyncio
from unittest.mock import patch

from api import server


def test_lifespan_reconciles_and_resumes_each_worker_once() -> None:
    async def run_lifespan() -> None:
        async with server._lifespan(server.app):
            pass

    with (
        patch.object(
            server,
            "_reconcile_incomplete_video_jobs",
            return_value={"failedSafe": 0, "submissionUncertain": 0},
        ) as reconcile,
        patch.object(server, "resume_interrupted_cut_projects") as resume_cuts,
        patch.object(server, "resume_interrupted_post_production_jobs") as resume_post,
        patch.object(
            server,
            "reconcile_interrupted_local_video_kit_jobs",
            return_value=0,
        ) as reconcile_local,
    ):
        asyncio.run(run_lifespan())

    reconcile.assert_called_once_with()
    resume_cuts.assert_called_once_with()
    resume_post.assert_called_once_with()
    reconcile_local.assert_called_once_with()
