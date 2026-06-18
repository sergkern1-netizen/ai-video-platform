import sqlite3
import os
from contextlib import contextmanager


def _db_path() -> str:
    return os.environ.get("BOT_DB_PATH", "bot_state.db")


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
            CREATE TABLE IF NOT EXISTS requests (
                video_id    TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                topic       TEXT NOT NULL,
                format      TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def add_request(video_id: str, user_id: int, topic: str, format: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO requests (video_id, user_id, topic, format) VALUES (?, ?, ?, ?)",
            (video_id, user_id, topic, format),
        )


def get_history(user_id: int, limit: int = 5) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM requests WHERE user_id = ? ORDER BY created_at DESC, video_id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
