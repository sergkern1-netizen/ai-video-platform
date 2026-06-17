import pytest
from unittest.mock import patch, MagicMock
from backend.pipeline.asset_fetcher import fetch_assets, Assets

def _mock_pexels_response(videos: list):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"videos": videos}
    return mock

def test_fetch_assets_returns_empty_when_pexels_fails():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.return_value = _mock_pexels_response([])
        assets = fetch_assets(["unknown_xyz_topic_abc"], 60)
    assert isinstance(assets, Assets)
    assert assets.video_clips == []

def test_fetch_assets_returns_empty_on_http_error():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.side_effect = Exception("connection refused")
        assets = fetch_assets(["nature"], 60)
    assert assets.video_clips == []

def test_fetch_assets_returns_clips_on_success(tmp_path):
    mock_video = {
        "id": 999,
        "duration": 15,
        "video_files": [
            {"width": 1920, "height": 1080, "link": "https://example.com/clip.mp4"}
        ],
    }

    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get, \
         patch("backend.pipeline.asset_fetcher._download_clip") as mock_dl:
        mock_get.return_value = _mock_pexels_response([mock_video])
        mock_dl.return_value = str(tmp_path / "999.mp4")

        assets = fetch_assets(["nature", "forest"], 60, clip_dir=str(tmp_path))

    assert len(assets.video_clips) == 1
    assert assets.video_clips[0]["duration_sec"] == 15
