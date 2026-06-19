import sqlite3
import os
from contextlib import contextmanager
from uuid import uuid4

def _db_path() -> str:
    return os.environ.get("DB_PATH", "db.sqlite3")

@contextmanager
def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

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

def create_video(video_id: str, topic: str, format: str) -> dict:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO videos (id, topic, format) VALUES (?, ?, ?)",
            (video_id, topic, format),
        )
    return get_video(video_id)

def get_video(video_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

def update_video_status(
    video_id: str,
    status: str,
    video_path: str = None,
    error: str = None,
):
    with _conn() as conn:
        if status == "completed":
            conn.execute(
                "UPDATE videos SET status=?, video_path=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, video_path, video_id),
            )
        elif status == "failed":
            conn.execute(
                "UPDATE videos SET status=?, error=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, video_id),
            )
        else:
            conn.execute(
                "UPDATE videos SET status=? WHERE id=?",
                (status, video_id),
            )

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
