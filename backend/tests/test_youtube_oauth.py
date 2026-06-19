import time
from unittest.mock import patch, MagicMock

import backend.youtube.oauth as oauth


def setup_function():
    oauth._pending_states.clear()


def test_start_oauth_returns_url_and_stores_state():
    fake_flow = MagicMock()
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/auth?state=abc", "abc")

    with patch("backend.youtube.oauth.Flow.from_client_config", return_value=fake_flow), \
         patch.dict("os.environ", {
             "GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "csecret",
             "PUBLIC_BASE_URL": "https://tunnel.example.com",
         }):
        auth_url = oauth.start_oauth(telegram_user_id=999)

    assert auth_url == "https://accounts.google.com/auth?state=abc"
    assert len(oauth._pending_states) == 1


def test_pop_pending_user_returns_user_id_once():
    oauth._pending_states["state-1"] = (42, time.time() + 600)
    assert oauth.pop_pending_user("state-1") == 42
    assert oauth.pop_pending_user("state-1") is None


def test_pop_pending_user_returns_none_for_unknown_state():
    assert oauth.pop_pending_user("nonexistent") is None


def test_pop_pending_user_returns_none_for_expired_state():
    oauth._pending_states["state-2"] = (42, time.time() - 1)
    assert oauth.pop_pending_user("state-2") is None


def test_exchange_code_returns_channel_info():
    fake_credentials = MagicMock(refresh_token="refresh-xyz")
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials

    fake_youtube = MagicMock()
    fake_youtube.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC123", "snippet": {"title": "My Channel"}}]
    }

    with patch("backend.youtube.oauth.Flow.from_client_config", return_value=fake_flow), \
         patch("backend.youtube.oauth.build", return_value=fake_youtube), \
         patch.dict("os.environ", {
             "GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "csecret",
             "PUBLIC_BASE_URL": "https://tunnel.example.com",
         }):
        result = oauth.exchange_code("auth-code-123")

    assert result == {
        "channel_id": "UC123",
        "channel_title": "My Channel",
        "refresh_token": "refresh-xyz",
    }
    fake_flow.fetch_token.assert_called_once_with(code="auth-code-123")
