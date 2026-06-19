from unittest.mock import patch, MagicMock
from google.auth.exceptions import RefreshError

from backend.youtube.uploader import upload_video


def _common_db_mocks(mock_db):
    mock_db.get_publish.return_value = {
        "id": "pub-1", "video_id": "vid-1", "channel_id": "chan-1",
        "title": "T", "description": "D", "privacy": "unlisted",
    }
    mock_db.get_youtube_channel.return_value = {"refresh_token": "refresh-abc"}
    mock_db.get_video.return_value = {"video_path": "output/vid-1.mp4"}


def test_upload_video_marks_completed_on_success():
    with patch("backend.youtube.uploader.db") as mock_db, \
         patch("backend.youtube.uploader._build_youtube_client") as mock_build_client, \
         patch("backend.youtube.uploader.MediaFileUpload"):
        _common_db_mocks(mock_db)
        fake_request = MagicMock()
        fake_request.next_chunk.return_value = (None, {"id": "yt-999"})
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.insert.return_value = fake_request
        mock_build_client.return_value = mock_youtube

        upload_video("pub-1")

        mock_db.update_publish_status.assert_any_call("pub-1", "uploading")
        mock_db.update_publish_status.assert_any_call("pub-1", "completed", youtube_video_id="yt-999")


def test_upload_video_marks_failed_on_refresh_error():
    with patch("backend.youtube.uploader.db") as mock_db, \
         patch("backend.youtube.uploader._build_youtube_client") as mock_build_client:
        _common_db_mocks(mock_db)
        mock_build_client.side_effect = RefreshError("token revoked")

        try:
            upload_video("pub-1")
            assert False, "expected RefreshError to propagate"
        except RefreshError:
            pass

        mock_db.update_publish_status.assert_any_call(
            "pub-1", "failed",
            error="Канал отключён в Google, подключите заново через /connect_channel",
        )


def test_upload_video_marks_failed_on_other_error():
    with patch("backend.youtube.uploader.db") as mock_db, \
         patch("backend.youtube.uploader._build_youtube_client") as mock_build_client:
        _common_db_mocks(mock_db)
        mock_build_client.side_effect = Exception("network down")

        try:
            upload_video("pub-1")
            assert False, "expected Exception to propagate"
        except Exception as exc:
            assert str(exc) == "network down"

        mock_db.update_publish_status.assert_any_call("pub-1", "failed", error="network down")
