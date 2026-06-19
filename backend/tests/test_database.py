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


from backend.database import (
    create_youtube_channel,
    get_youtube_channel,
    list_youtube_channels,
    create_publish,
    get_publish,
    update_publish_status,
)


def test_create_youtube_channel_returns_row():
    channel = create_youtube_channel("UC123", "My Channel", "refresh-abc", 555)
    assert channel["channel_id"] == "UC123"
    assert channel["channel_title"] == "My Channel"
    assert channel["refresh_token"] == "refresh-abc"
    assert channel["connected_by_user_id"] == 555


def test_get_youtube_channel_returns_none_for_unknown():
    assert get_youtube_channel("nonexistent") is None


def test_list_youtube_channels_returns_all():
    create_youtube_channel("UC1", "Channel One", "tok1", 1)
    create_youtube_channel("UC2", "Channel Two", "tok2", 2)
    channels = list_youtube_channels()
    titles = {c["channel_title"] for c in channels}
    assert titles == {"Channel One", "Channel Two"}


def test_create_publish_returns_pending():
    publish = create_publish("vid-1", "chan-1", "My Title", "My description")
    assert publish["video_id"] == "vid-1"
    assert publish["channel_id"] == "chan-1"
    assert publish["title"] == "My Title"
    assert publish["description"] == "My description"
    assert publish["privacy"] == "unlisted"
    assert publish["status"] == "pending"


def test_get_publish_returns_none_for_unknown():
    assert get_publish("nonexistent") is None


def test_update_publish_status_to_uploading():
    publish = create_publish("vid-2", "chan-1", "T", "D")
    update_publish_status(publish["id"], "uploading")
    assert get_publish(publish["id"])["status"] == "uploading"


def test_update_publish_status_to_completed_sets_youtube_video_id():
    publish = create_publish("vid-3", "chan-1", "T", "D")
    update_publish_status(publish["id"], "completed", youtube_video_id="yt-xyz")
    row = get_publish(publish["id"])
    assert row["status"] == "completed"
    assert row["youtube_video_id"] == "yt-xyz"
    assert row["completed_at"] is not None


def test_update_publish_status_to_failed_sets_error():
    publish = create_publish("vid-4", "chan-1", "T", "D")
    update_publish_status(publish["id"], "failed", error="quota exceeded")
    row = get_publish(publish["id"])
    assert row["status"] == "failed"
    assert row["error"] == "quota exceeded"
