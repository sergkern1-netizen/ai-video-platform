from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import Scene
from backend.pipeline.asset_fetcher import fetch_assets, Assets

def _scene(keywords=None, duration_sec=5):
    return Scene(text="test scene", keywords=keywords or ["nature"], duration_sec=duration_sec)

def _mock_pexels_response(videos: list):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"videos": videos}
    return mock

def test_fetch_assets_returns_none_clips_when_pexels_empty():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.return_value = _mock_pexels_response([])
        assets = fetch_assets([_scene()], "short")
    assert isinstance(assets, Assets)
    assert assets.video_clips == [None]

def test_fetch_assets_returns_none_on_http_error():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.side_effect = Exception("connection refused")
        assets = fetch_assets([_scene()], "short")
    assert assets.video_clips == [None]

def test_fetch_assets_returns_clip_on_success(tmp_path):
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
        assets = fetch_assets([_scene()], "short", clip_dir=str(tmp_path))

    assert len(assets.video_clips) == 1
    assert assets.video_clips[0]["duration_sec"] == 15
    mock_dl.assert_called_once()

def test_fetch_assets_uses_portrait_orientation_for_short():
    captured = {}
    def capture(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _mock_pexels_response([])
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=capture):
        fetch_assets([_scene()], "short")
    assert captured["params"]["orientation"] == "portrait"

def test_fetch_assets_uses_landscape_orientation_for_long():
    captured = {}
    def capture(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _mock_pexels_response([])
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=capture):
        fetch_assets([_scene()], "long")
    assert captured["params"]["orientation"] == "landscape"

def test_fetch_assets_falls_back_to_previous_scene_clip():
    mock_video = {
        "id": 1,
        "duration": 10,
        "video_files": [{"width": 1920, "height": 1080, "link": "https://example.com/clip.mp4"}],
    }
    responses = [_mock_pexels_response([mock_video]), _mock_pexels_response([])]
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=responses), \
         patch("backend.pipeline.asset_fetcher._download_clip"):
        assets = fetch_assets([_scene(), _scene()], "short", clip_dir="temp")

    assert assets.video_clips[0] is not None
    assert assets.video_clips[1] == assets.video_clips[0]

def test_fetch_assets_first_scene_with_no_result_stays_none():
    responses = [_mock_pexels_response([])]
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=responses):
        assets = fetch_assets([_scene()], "short")

    assert assets.video_clips == [None]
