import sqlite3
import os
from contextlib import contextmanager

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
