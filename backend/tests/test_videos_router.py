from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

with patch("backend.routers.videos.Redis"), patch("backend.routers.videos.Queue"):
    from backend.main import app

client = TestClient(app)

def test_create_video_returns_id():
    with patch("backend.routers.videos.db.create_video") as mock_create, \
         patch("backend.routers.videos._queue") as mock_q:
        mock_create.return_value = {"id": "abc", "status": "pending"}
        resp = client.post("/videos/", json={"topic": "AI news", "format": "short"})

    assert resp.status_code == 200
    assert "id" in resp.json()
    mock_q.enqueue.assert_called_once()

def test_create_video_rejects_invalid_format():
    resp = client.post("/videos/", json={"topic": "AI news", "format": "bad"})
    assert resp.status_code == 422

def test_get_status_returns_video():
    with patch("backend.routers.videos.db.get_video") as mock_get:
        mock_get.return_value = {
            "id": "abc", "topic": "AI news", "format": "short",
            "status": "processing", "video_path": None, "error": None,
            "created_at": "2026-06-14", "completed_at": None,
        }
        resp = client.get("/videos/abc/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"

def test_get_status_returns_404_for_unknown():
    with patch("backend.routers.videos.db.get_video", return_value=None):
        resp = client.get("/videos/nonexistent/status")
    assert resp.status_code == 404

def test_download_returns_404_when_not_completed():
    with patch("backend.routers.videos.db.get_video") as mock_get:
        mock_get.return_value = {"status": "processing", "video_path": None}
        resp = client.get("/videos/abc/download")
    assert resp.status_code == 404
