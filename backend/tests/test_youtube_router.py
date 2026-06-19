from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

with patch("backend.routers.videos.Redis"), patch("backend.routers.videos.Queue"), \
     patch("backend.routers.youtube.Redis"), patch("backend.routers.youtube.Queue"):
    from backend.main import app

client = TestClient(app)


def test_start_connect_returns_auth_url():
    with patch("backend.routers.youtube.oauth.start_oauth", return_value="https://accounts.google.com/auth?state=x") as mock_start:
        resp = client.post("/youtube/connect/start", json={"telegram_user_id": 42})

    assert resp.status_code == 200
    assert resp.json() == {"auth_url": "https://accounts.google.com/auth?state=x"}
    mock_start.assert_called_once_with(42)


def test_oauth_callback_creates_channel_and_notifies():
    with patch("backend.routers.youtube.oauth.pop_pending_user", return_value=42), \
         patch("backend.routers.youtube.oauth.exchange_code", return_value={
             "channel_id": "UC1", "channel_title": "My Channel", "refresh_token": "tok",
         }), \
         patch("backend.routers.youtube.db.create_youtube_channel") as mock_create, \
         patch("backend.routers.youtube.httpx.post") as mock_post, \
         patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "bot-token"}):
        resp = client.get("/youtube/oauth/callback", params={"code": "abc", "state": "state-1"})

    assert resp.status_code == 200
    mock_create.assert_called_once_with("UC1", "My Channel", "tok", 42)
    mock_post.assert_called_once()


def test_oauth_callback_handles_expired_state():
    with patch("backend.routers.youtube.oauth.pop_pending_user", return_value=None):
        resp = client.get("/youtube/oauth/callback", params={"code": "abc", "state": "expired"})

    assert resp.status_code == 200
    assert "устарела" in resp.text


def test_list_channels_returns_id_and_title():
    with patch("backend.routers.youtube.db.list_youtube_channels", return_value=[
        {"id": "row-1", "channel_id": "UC1", "channel_title": "My Channel",
         "refresh_token": "tok", "connected_by_user_id": 1, "created_at": "2026-06-19"},
    ]):
        resp = client.get("/youtube/channels")

    assert resp.status_code == 200
    assert resp.json() == [{"id": "row-1", "channel_title": "My Channel"}]


def test_publish_rejects_video_not_completed():
    with patch("backend.routers.youtube.db.get_video", return_value={"status": "processing"}):
        resp = client.post("/youtube/publish", json={
            "video_id": "vid-1", "channel_id": "chan-1", "title": "T", "description": "D",
        })

    assert resp.status_code == 404


def test_publish_enqueues_job_for_completed_video():
    with patch("backend.routers.youtube.db.get_video", return_value={"status": "completed"}), \
         patch("backend.routers.youtube.db.create_publish", return_value={"id": "pub-1"}), \
         patch("backend.routers.youtube._queue") as mock_queue:
        resp = client.post("/youtube/publish", json={
            "video_id": "vid-1", "channel_id": "chan-1", "title": "T", "description": "D",
        })

    assert resp.status_code == 200
    assert resp.json() == {"id": "pub-1"}
    mock_queue.enqueue.assert_called_once()


def test_get_publish_status_returns_404_for_unknown():
    with patch("backend.routers.youtube.db.get_publish", return_value=None):
        resp = client.get("/youtube/publishes/nonexistent/status")
    assert resp.status_code == 404


def test_get_publish_status_returns_row():
    with patch("backend.routers.youtube.db.get_publish", return_value={"id": "pub-1", "status": "uploading"}):
        resp = client.get("/youtube/publishes/pub-1/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploading"
