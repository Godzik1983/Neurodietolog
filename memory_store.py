import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("bot_memory.db")


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                recent_dialog TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def get_user_memory(user_id: int) -> tuple[str, str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT summary, recent_dialog FROM user_memory WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return "", ""
    return row[0] or "", row[1] or ""


def upsert_user_memory(user_id: int, summary: str, recent_dialog: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_memory (user_id, summary, recent_dialog, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                summary = excluded.summary,
                recent_dialog = excluded.recent_dialog,
                updated_at = excluded.updated_at
            """,
            (user_id, summary, recent_dialog, now),
        )
        conn.commit()


def clear_user_memory(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_memory (user_id, summary, recent_dialog, updated_at)
            VALUES (?, '', '', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                summary = '',
                recent_dialog = '',
                updated_at = excluded.updated_at
            """,
            (user_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
