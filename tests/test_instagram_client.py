from __future__ import annotations

from unittest.mock import Mock, patch

from integrations.instagram_client import InstagramClient


def response(payload: dict, status_code: int = 200) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.json.return_value = payload
    return result


def test_create_reel_container_sends_expected_meta_parameters() -> None:
    client = InstagramClient(access_token="secret", account_id="ig-123")
    with patch("integrations.instagram_client.requests.post") as post:
        post.return_value = response({"id": "container-1"})
        container_id = client.create_video_container(
            "https://files.example/video.mp4",
            media_type="REELS",
            caption="Legenda",
            share_to_feed=False,
        )

    assert container_id == "container-1"
    _, kwargs = post.call_args
    assert kwargs["params"] == {
        "media_type": "REELS",
        "video_url": "https://files.example/video.mp4",
        "caption": "Legenda",
        "share_to_feed": "false",
        "access_token": "secret",
    }


def test_story_container_does_not_send_caption_or_feed_flag() -> None:
    client = InstagramClient(access_token="secret", account_id="ig-123")
    with patch("integrations.instagram_client.requests.post") as post:
        post.return_value = response({"id": "container-story"})
        client.create_video_container(
            "https://files.example/story.mp4",
            media_type="STORIES",
            caption="Ignorada",
            share_to_feed=True,
        )

    params = post.call_args.kwargs["params"]
    assert "caption" not in params
    assert "share_to_feed" not in params


def test_publish_video_waits_until_container_is_finished() -> None:
    client = InstagramClient(access_token="secret", account_id="ig-123")
    with (
        patch.object(client, "create_video_container", return_value="container-1"),
        patch.object(
            client,
            "container_status",
            side_effect=[{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}],
        ),
        patch.object(client, "publish_container", return_value="media-1") as publish,
        patch("integrations.instagram_client.time.sleep"),
    ):
        result = client.publish_video(
            "https://files.example/video.mp4",
            media_type="REELS",
            poll_interval_seconds=0,
        )

    assert result == {
        "containerId": "container-1",
        "mediaId": "media-1",
        "mediaType": "REELS",
    }
    publish.assert_called_once_with("container-1")
