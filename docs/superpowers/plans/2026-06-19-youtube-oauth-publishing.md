# YouTube OAuth Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let allowlisted Telegram bot users connect YouTube channels (shared pool, no per-user ownership) and publish completed videos to them via OAuth + the YouTube Data API v3.

**Architecture:** New additive backend modules (`backend/youtube/oauth.py`, `backend/youtube/uploader.py`, `backend/routers/youtube.py`) plus two new SQLite tables (`youtube_channels`, `publishes`) appended to `backend/database.py`. The bot gets two new commands (`/connect_channel`, `/publish`) appended to `bot/handlers.py`, backed by new HTTP methods appended to `bot/client.py`. No existing function signatures change.

**Tech Stack:** FastAPI, RQ, SQLite (stdlib `sqlite3`), `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, aiogram 3.x, httpx, pytest.

All commands below assume the working directory is `ai-video-platform/` (where `pytest.ini` lives). Branch: continue on `feature/telegram-bot` (not yet merged to `master`).

---

### Task 1: Database — `youtube_channels` and `publishes` tables

**Files:**
- Modify: `backend/database.py` (append new tables to `init_db()`, append new functions at end of file)
- Test: `backend/tests/test_database.py` (append new test functions at end of file)

- [ ] **Step 1: Write failing tests for the new table functions**

Append to `backend/tests/test_database.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_database.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_youtube_channel'`

- [ ] **Step 3: Add the two tables to `init_db()`**

In `backend/database.py`, the current `init_db()` is:

```python
def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id           TEXT PRIMARY KEY,
                topic        TEXT NOT NULL,
                format       TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                video_path   TEXT,
                error        TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
        """)
```

Append two more `conn.execute(...)` calls inside the same `with _conn() as conn:` block, right after the existing `videos` table creation:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_channels (
                id                   TEXT PRIMARY KEY,
                channel_id           TEXT NOT NULL,
                channel_title        TEXT NOT NULL,
                refresh_token        TEXT NOT NULL,
                connected_by_user_id INTEGER NOT NULL,
                created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publishes (
                id               TEXT PRIMARY KEY,
                video_id         TEXT NOT NULL,
                channel_id       TEXT NOT NULL,
                title            TEXT NOT NULL,
                description      TEXT NOT NULL,
                privacy          TEXT NOT NULL DEFAULT 'unlisted',
                status           TEXT NOT NULL DEFAULT 'pending',
                youtube_video_id TEXT,
                error            TEXT,
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at     DATETIME
            )
        """)
```

- [ ] **Step 4: Add `from uuid import uuid4` import and append the new functions**

At the top of `backend/database.py`, add the import next to the existing `import sqlite3` / `import os`:

```python
from uuid import uuid4
```

Append at the end of `backend/database.py` (after the existing `update_video_status`):

```python
def create_youtube_channel(
    channel_id: str, channel_title: str, refresh_token: str, connected_by_user_id: int
) -> dict:
    row_id = str(uuid4())
    with _conn() as conn:
        conn.execute(
            "INSERT INTO youtube_channels (id, channel_id, channel_title, refresh_token, connected_by_user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (row_id, channel_id, channel_title, refresh_token, connected_by_user_id),
        )
    return get_youtube_channel(row_id)


def get_youtube_channel(channel_row_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM youtube_channels WHERE id = ?", (channel_row_id,)
        ).fetchone()
        return dict(row) if row else None


def list_youtube_channels() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM youtube_channels ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def create_publish(video_id: str, channel_id: str, title: str, description: str) -> dict:
    publish_id = str(uuid4())
    with _conn() as conn:
        conn.execute(
            "INSERT INTO publishes (id, video_id, channel_id, title, description) VALUES (?, ?, ?, ?, ?)",
            (publish_id, video_id, channel_id, title, description),
        )
    return get_publish(publish_id)


def get_publish(publish_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM publishes WHERE id = ?", (publish_id,)).fetchone()
        return dict(row) if row else None


def update_publish_status(
    publish_id: str,
    status: str,
    youtube_video_id: str = None,
    error: str = None,
):
    with _conn() as conn:
        if status == "completed":
            conn.execute(
                "UPDATE publishes SET status=?, youtube_video_id=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, youtube_video_id, publish_id),
            )
        elif status == "failed":
            conn.execute(
                "UPDATE publishes SET status=?, error=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, publish_id),
            )
        else:
            conn.execute(
                "UPDATE publishes SET status=? WHERE id=?",
                (status, publish_id),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_database.py -v`
Expected: all PASS (existing `videos` tests + new ones)

- [ ] **Step 6: Commit**

```bash
git add backend/database.py backend/tests/test_database.py
git commit -m "feat: add youtube_channels and publishes tables"
```

---

### Task 2: `backend/youtube/oauth.py` — OAuth URL, state tracking, code exchange

**Files:**
- Create: `backend/youtube/__init__.py` (empty)
- Create: `backend/youtube/oauth.py`
- Test: `backend/tests/test_youtube_oauth.py`

- [ ] **Step 1: Create the empty package init**

Create `backend/youtube/__init__.py` with no content (empty file).

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_youtube_oauth.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_youtube_oauth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.youtube'`

- [ ] **Step 4: Add google libraries to requirements**

Append to `backend/requirements.txt`:

```
google-auth==2.32.0
google-auth-oauthlib==1.2.1
google-api-python-client==2.137.0
```

Run: `pip install -r backend/requirements.txt`

- [ ] **Step 5: Implement `backend/youtube/oauth.py`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_youtube_oauth.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/youtube/__init__.py backend/youtube/oauth.py backend/tests/test_youtube_oauth.py backend/requirements.txt
git commit -m "feat: youtube oauth url generation and code exchange"
```

---

### Task 3: `backend/youtube/uploader.py` — resumable upload RQ job

**Files:**
- Create: `backend/youtube/uploader.py`
- Test: `backend/tests/test_youtube_uploader.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_youtube_uploader.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_youtube_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.youtube.uploader'`

- [ ] **Step 3: Implement `backend/youtube/uploader.py`**

```python
import os

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import backend.database as db


def _build_youtube_client(refresh_token: str):
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=credentials)


def upload_video(publish_id: str) -> None:
    publish = db.get_publish(publish_id)
    try:
        db.update_publish_status(publish_id, "uploading")

        channel = db.get_youtube_channel(publish["channel_id"])
        video = db.get_video(publish["video_id"])

        youtube = _build_youtube_client(channel["refresh_token"])
        media = MediaFileUpload(video["video_path"], chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": publish["title"],
                    "description": publish["description"],
                },
                "status": {"privacyStatus": publish["privacy"]},
            },
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        db.update_publish_status(publish_id, "completed", youtube_video_id=response["id"])

    except RefreshError:
        db.update_publish_status(
            publish_id, "failed",
            error="Канал отключён в Google, подключите заново через /connect_channel",
        )
        raise
    except Exception as exc:
        db.update_publish_status(publish_id, "failed", error=str(exc))
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_youtube_uploader.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/youtube/uploader.py backend/tests/test_youtube_uploader.py
git commit -m "feat: youtube resumable upload rq job"
```

---

### Task 4: `backend/routers/youtube.py` — HTTP endpoints, wired into `main.py`

**Files:**
- Create: `backend/routers/youtube.py`
- Modify: `backend/main.py:1-23`
- Test: `backend/tests/test_youtube_router.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_youtube_router.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_youtube_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.routers.youtube'`

- [ ] **Step 3: Implement `backend/routers/youtube.py`**

```python
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from redis import Redis
from rq import Queue

import backend.database as db
import backend.youtube.oauth as oauth
from backend.youtube.uploader import upload_video

router = APIRouter()

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
_queue = Queue(connection=_redis)


class StartConnectRequest(BaseModel):
    telegram_user_id: int


@router.post("/connect/start")
def start_connect(request: StartConnectRequest):
    auth_url = oauth.start_oauth(request.telegram_user_id)
    return {"auth_url": auth_url}


@router.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(code: str, state: str):
    telegram_user_id = oauth.pop_pending_user(state)
    if telegram_user_id is None:
        return HTMLResponse(
            "<h1>Ссылка устарела, начните заново через /connect_channel в боте.</h1>"
        )

    channel_info = oauth.exchange_code(code)
    db.create_youtube_channel(
        channel_info["channel_id"],
        channel_info["channel_title"],
        channel_info["refresh_token"],
        telegram_user_id,
    )
    _notify_telegram(telegram_user_id, f"Канал «{channel_info['channel_title']}» подключён!")
    return HTMLResponse("<h1>Готово! Возвращайтесь в Telegram.</h1>")


def _notify_telegram(user_id: int, text: str):
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": user_id, "text": text},
        timeout=10,
    )


@router.get("/channels")
def list_channels():
    channels = db.list_youtube_channels()
    return [{"id": c["id"], "channel_title": c["channel_title"]} for c in channels]


class PublishRequest(BaseModel):
    video_id: str
    channel_id: str
    title: str
    description: str


@router.post("/publish")
def publish(request: PublishRequest):
    video = db.get_video(request.video_id)
    if not video or video["status"] != "completed":
        raise HTTPException(status_code=404, detail="Video not ready")

    publish_row = db.create_publish(
        request.video_id, request.channel_id, request.title, request.description
    )
    _queue.enqueue(upload_video, publish_row["id"], job_timeout=1800)
    return {"id": publish_row["id"]}


@router.get("/publishes/{publish_id}/status")
def get_publish_status(publish_id: str):
    publish_row = db.get_publish(publish_id)
    if not publish_row:
        raise HTTPException(status_code=404, detail="Publish not found")
    return publish_row
```

- [ ] **Step 4: Wire the router into `backend/main.py`**

Current `backend/main.py`:

```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers.videos import router as videos_router

app = FastAPI(title="AI Video Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(videos_router, prefix="/videos")
```

Change the import line and add one `include_router` call:

```python
from backend.database import init_db
from backend.routers.videos import router as videos_router
from backend.routers.youtube import router as youtube_router

app = FastAPI(title="AI Video Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(videos_router, prefix="/videos")
app.include_router(youtube_router, prefix="/youtube")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_youtube_router.py -v`
Expected: all PASS

Run the full backend suite to confirm nothing else broke: `pytest backend/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/youtube.py backend/main.py backend/tests/test_youtube_router.py
git commit -m "feat: youtube router endpoints (connect, callback, channels, publish, status)"
```

---

### Task 5: `.env.example` — document new variables

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Append the two new variables**

Current `.env.example`:

```
OPENAI_API_KEY=sk-...
PEXELS_API_KEY=...
DB_PATH=db.sqlite3
REDIS_URL=redis://localhost:6379
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456,789012
PUBLIC_BASE_URL=https://your-tunnel-subdomain.example.com
BACKEND_URL=http://localhost:8000
```

Append:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document GOOGLE_CLIENT_ID/SECRET in .env.example"
```

---

### Task 6: `bot/client.py` — HTTP methods for the youtube endpoints

**Files:**
- Modify: `bot/client.py` (append four functions at end of file)
- Test: `bot/tests/test_client.py` (append four test functions at end of file)

- [ ] **Step 1: Write failing tests**

Append to `bot/tests/test_client.py`:

```python
async def test_start_channel_connect_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"auth_url": "https://accounts.google.com/auth"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.start_channel_connect(42)

    assert result == {"auth_url": "https://accounts.google.com/auth"}
    mock_client.post.assert_called_once_with(
        "/youtube/connect/start", json={"telegram_user_id": 42}
    )


async def test_get_channels_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = [{"id": "row-1", "channel_title": "My Channel"}]
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_channels()

    assert result == [{"id": "row-1", "channel_title": "My Channel"}]
    mock_client.get.assert_called_once_with("/youtube/channels")


async def test_publish_video_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"id": "pub-1"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.publish_video("vid-1", "chan-1", "Title", "Description")

    assert result == {"id": "pub-1"}
    mock_client.post.assert_called_once_with(
        "/youtube/publish",
        json={"video_id": "vid-1", "channel_id": "chan-1", "title": "Title", "description": "Description"},
    )


async def test_get_publish_status_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"status": "completed", "youtube_video_id": "yt-1"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_publish_status("pub-1")

    assert result == {"status": "completed", "youtube_video_id": "yt-1"}
    mock_client.get.assert_called_once_with("/youtube/publishes/pub-1/status")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest bot/tests/test_client.py -v`
Expected: FAIL with `AttributeError: module 'bot.client' has no attribute 'start_channel_connect'`

- [ ] **Step 3: Append the four functions to `bot/client.py`**

```python
async def start_channel_connect(telegram_user_id: int) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.post(
            "/youtube/connect/start", json={"telegram_user_id": telegram_user_id}
        )
        response.raise_for_status()
        return response.json()


async def get_channels() -> list[dict]:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.get("/youtube/channels")
        response.raise_for_status()
        return response.json()


async def publish_video(video_id: str, channel_id: str, title: str, description: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.post(
            "/youtube/publish",
            json={
                "video_id": video_id,
                "channel_id": channel_id,
                "title": title,
                "description": description,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_publish_status(publish_id: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.get(f"/youtube/publishes/{publish_id}/status")
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest bot/tests/test_client.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add bot/client.py bot/tests/test_client.py
git commit -m "feat: bot http client methods for youtube endpoints"
```

---

### Task 7: `bot/handlers.py` — `/connect_channel` and `/publish` commands

**Files:**
- Modify: `bot/handlers.py`

No automated tests for this task — the existing codebase has no FSM/handler unit tests for `/generate` either (only `bot/client.py`'s HTTP layer is unit-tested; handler/FSM behavior is verified manually). This task is verified manually in Task 8.

- [ ] **Step 1: Add the `PublishStates` group**

After the existing `GenerateStates` class in `bot/handlers.py`, add:

```python
class PublishStates(StatesGroup):
    waiting_video = State()
    waiting_channel = State()
    waiting_mode = State()
    waiting_title = State()
    waiting_description = State()
```

- [ ] **Step 2: Update `cmd_start` to mention the new commands**

Replace the existing `cmd_start` body's message text:

```python
    await message.answer(
        "Привет! Команды:\n"
        "/generate — создать видео\n"
        "/history — последние запросы\n"
        "/connect_channel — подключить YouTube-канал\n"
        "/publish — опубликовать готовое видео на YouTube\n"
        "/cancel — отменить текущий ввод"
    )
```

- [ ] **Step 3: Add `cmd_connect_channel`**

Add after `cmd_cancel`:

```python
@router.message(Command("connect_channel"))
async def cmd_connect_channel(message: Message):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    try:
        result = await client.start_channel_connect(message.from_user.id)
    except Exception:
        logger.exception("start_channel_connect failed")
        await message.answer("Backend недоступен, попробуйте позже.")
        return
    await message.answer(
        f"Перейдите по ссылке и войдите в Google: {result['auth_url']}\n"
        "После подтверждения канал станет доступен всем."
    )
```

- [ ] **Step 4: Add `cmd_publish` and the video-selection callback**

Add after the existing `_poll_and_notify` function:

```python
@router.message(Command("publish"))
async def cmd_publish(message: Message, state: FSMContext):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    requests = bot_state.get_history(message.from_user.id, limit=20)
    completed = []
    for req in requests:
        try:
            status_data = await client.get_status(req["video_id"])
        except Exception:
            continue
        if status_data["status"] == "completed":
            completed.append(req)

    if not completed:
        await message.answer("Нет готовых видео для публикации.")
        return

    await state.update_data(videos={str(i): req for i, req in enumerate(completed)})
    await state.set_state(PublishStates.waiting_video)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=req["topic"], callback_data=f"pubvid:{i}")]
            for i, req in enumerate(completed)
        ]
    )
    await message.answer("Выберите видео для публикации:", reply_markup=keyboard)


@router.callback_query(PublishStates.waiting_video, F.data.startswith("pubvid:"))
async def on_publish_video_selected(callback: CallbackQuery, state: FSMContext):
    index = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = data["videos"][index]
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        channels = await client.get_channels()
    except Exception:
        logger.exception("get_channels failed")
        await callback.message.answer("Backend недоступен, попробуйте позже.")
        await callback.answer()
        return

    if not channels:
        await callback.message.answer("Сначала подключите канал: /connect_channel")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(
        video_id=selected["video_id"],
        topic=selected["topic"],
        channels={str(i): ch for i, ch in enumerate(channels)},
    )
    await state.set_state(PublishStates.waiting_channel)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ch["channel_title"], callback_data=f"pubch:{i}")]
            for i, ch in enumerate(channels)
        ]
    )
    await callback.message.answer("Выберите канал:", reply_markup=keyboard)
    await callback.answer()
```

- [ ] **Step 5: Add the channel-selection and mode-selection callbacks**

```python
@router.callback_query(PublishStates.waiting_channel, F.data.startswith("pubch:"))
async def on_publish_channel_selected(callback: CallbackQuery, state: FSMContext):
    index = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected_channel = data["channels"][index]
    await callback.message.edit_reply_markup(reply_markup=None)

    await state.update_data(channel_id=selected_channel["id"])
    await state.set_state(PublishStates.waiting_mode)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Автоматически", callback_data="pubmode:auto"),
                InlineKeyboardButton(text="Указать вручную", callback_data="pubmode:manual"),
            ]
        ]
    )
    await callback.message.answer("Как оформить заголовок и описание?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(PublishStates.waiting_mode, F.data.startswith("pubmode:"))
async def on_publish_mode_selected(callback: CallbackQuery, state: FSMContext, bot: Bot):
    mode = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if mode == "manual":
        await state.set_state(PublishStates.waiting_title)
        await callback.message.answer("Введите заголовок видео:")
        await callback.answer()
        return

    data = await state.get_data()
    topic = data["topic"]
    await _start_publish(
        callback.message, bot, state,
        title=topic,
        description=f"Сгенерировано AI Video Platform. Тема: {topic}",
    )
    await callback.answer()
```

- [ ] **Step 6: Add the manual title/description steps and the shared publish starter**

```python
@router.message(PublishStates.waiting_title)
async def on_publish_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Введите заголовок видео:")
        return
    await state.update_data(title=title)
    await state.set_state(PublishStates.waiting_description)
    await message.answer('Введите описание видео (или "-" чтобы оставить пустым):')


@router.message(PublishStates.waiting_description)
async def on_publish_description(message: Message, state: FSMContext, bot: Bot):
    raw = (message.text or "").strip()
    description = "" if raw == "-" else raw
    data = await state.get_data()
    await _start_publish(message, bot, state, title=data["title"], description=description)


async def _start_publish(message: Message, bot: Bot, state: FSMContext, title: str, description: str):
    data = await state.get_data()
    video_id = data["video_id"]
    channel_id = data["channel_id"]
    await state.clear()

    try:
        result = await client.publish_video(video_id, channel_id, title, description)
    except Exception:
        logger.exception("publish_video failed for video_id=%s", video_id)
        await message.answer("Backend недоступен, попробуйте позже.")
        return

    publish_id = result["id"]
    await message.answer("Публикация запущена. Сообщу, когда будет готово.")
    asyncio.create_task(_poll_and_notify_publish(bot, message.chat.id, publish_id))


async def _poll_and_notify_publish(bot: Bot, chat_id: int, publish_id: str):
    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        try:
            status_data = await client.get_publish_status(publish_id)
        except Exception:
            logger.exception("publish status poll failed for publish_id=%s", publish_id)
            continue

        status = status_data["status"]
        if status == "completed":
            youtube_video_id = status_data["youtube_video_id"]
            await bot.send_message(
                chat_id, f"Опубликовано! https://youtube.com/watch?v={youtube_video_id}"
            )
            return
        if status == "failed":
            await bot.send_message(chat_id, f"Не получилось: {status_data.get('error')}")
            return
```

- [ ] **Step 7: Run the full bot test suite to confirm nothing broke**

Run: `pytest bot/ -v`
Expected: all PASS (no new tests added in this task, existing ones still green)

- [ ] **Step 8: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: /connect_channel and /publish bot commands"
```

---

### Task 8: Manual E2E setup and verification

**Files:** none (manual verification only)

- [ ] **Step 1: Create a Google Cloud OAuth client**

In Google Cloud Console: create/select a project → enable "YouTube Data API v3" → create OAuth 2.0 Client ID credentials (type: Web application) → add authorized redirect URI `{PUBLIC_BASE_URL}/youtube/oauth/callback` (the same tunnel URL already used for Telegram). Copy the generated Client ID/Secret into `.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

- [ ] **Step 2: Restart all four processes**

Per the existing pattern (`docs/session-history.md` Сессия 4): restart `uvicorn`, the RQ worker, the bot, and confirm the tunnel (`PUBLIC_BASE_URL`) still points at the running uvicorn instance. Restart uvicorn manually rather than relying on `--reload` (documented as unreliable on this machine).

- [ ] **Step 3: Test `/connect_channel`**

In Telegram: send `/connect_channel`. Open the returned link in a browser, sign in with a real Google account that owns (or can create) a YouTube channel, grant consent. Confirm: browser shows "Готово! Возвращайтесь в Telegram", and a Telegram message "Канал «...» подключён!" arrives.

- [ ] **Step 4: Test `/publish` end-to-end with a real short video**

Generate a short video via `/generate` if none is completed yet. Send `/publish`, pick the video, pick the just-connected channel, pick "Автоматически". Confirm the bot reports "Публикация запущена", then later sends a `https://youtube.com/watch?v=...` link. Open that link and confirm the video plays, is set to "Unlisted", and the title matches the topic.

- [ ] **Step 5: Test the manual metadata path**

Run `/publish` again on a (possibly the same) completed video, this time choosing "Указать вручную". Provide a custom title and a custom description (and once with `-` for an empty description). Confirm the resulting YouTube video reflects the custom title/description.

- [ ] **Step 6: Update session history**

Append a new session entry to `docs/session-history.md` documenting the outcome (what worked, any bugs found and fixed, similar to the existing Telegram bot E2E entries).

---

## Notes for the implementer

- This plan only touches `feature/telegram-bot` (not yet merged to `master`). Keep working on that branch; merging both this feature and the bot is a decision for `finishing-a-development-branch` once everything is verified.
- Privacy is hardcoded to `"unlisted"` everywhere — there is intentionally no API parameter or bot prompt for choosing a different value (see spec's "Вне рамок").
- There is no channel-removal/disconnect command — out of scope per spec.
