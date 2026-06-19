import os
import time
import uuid

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_STATE_TTL_SEC = 600
_pending_states: dict[str, tuple[int, float]] = {}


def _redirect_uri() -> str:
    return os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/youtube/oauth/callback"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def start_oauth(telegram_user_id: int) -> str:
    state = uuid.uuid4().hex
    _pending_states[state] = (telegram_user_id, time.time() + _STATE_TTL_SEC)
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=_redirect_uri())
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    return auth_url


def pop_pending_user(state: str) -> int | None:
    entry = _pending_states.pop(state, None)
    if entry is None:
        return None
    user_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return user_id


def exchange_code(code: str) -> dict:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=_redirect_uri())
    flow.fetch_token(code=code)
    credentials = flow.credentials

    youtube = build("youtube", "v3", credentials=credentials)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    channel = response["items"][0]

    return {
        "channel_id": channel["id"],
        "channel_title": channel["snippet"]["title"],
        "refresh_token": credentials.refresh_token,
    }
