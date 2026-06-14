import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.database import init_db, create_video, get_video, update_video_status

@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_file)
    init_db()
    yield

def test_create_video_returns_pending():
    video = create_video("vid-1", "AI trends", "short")
    assert video["id"] == "vid-1"
    assert video["status"] == "pending"
    assert video["topic"] == "AI trends"
    assert video["format"] == "short"

def test_get_video_returns_none_for_unknown():
    assert get_video("nonexistent") is None

def test_update_status_to_processing():
    create_video("vid-2", "History", "long")
    update_video_status("vid-2", "processing")
    video = get_video("vid-2")
    assert video["status"] == "processing"

def test_update_status_to_completed_sets_path():
    create_video("vid-3", "Science", "short")
    update_video_status("vid-3", "completed", video_path="output/vid-3.mp4")
    video = get_video("vid-3")
    assert video["status"] == "completed"
    assert video["video_path"] == "output/vid-3.mp4"
    assert video["completed_at"] is not None

def test_update_status_to_failed_sets_error():
    create_video("vid-4", "Math", "short")
    update_video_status("vid-4", "failed", error="OpenAI rate limit")
    video = get_video("vid-4")
    assert video["status"] == "failed"
    assert video["error"] == "OpenAI rate limit"
