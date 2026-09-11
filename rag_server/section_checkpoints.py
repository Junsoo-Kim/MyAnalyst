from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "section_checkpoints.sqlite3"


def _db_path() -> str:
    return os.environ.get("SECTION_CHECKPOINT_DB_PATH", str(DEFAULT_DB_PATH))


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS section_checkpoints (
                job_id TEXT NOT NULL,
                section_key TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (job_id, section_key)
            )
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def load_sections(job_id: str) -> dict[str, str]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT section_key, content FROM section_checkpoints WHERE job_id = ?",
            (job_id,),
        ).fetchall()
    return {key: content for key, content in rows}


def save_section(job_id: str, section_key: str, content: str) -> None:
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO section_checkpoints (job_id, section_key, content)
            VALUES (?, ?, ?)
            ON CONFLICT (job_id, section_key) DO UPDATE SET content = excluded.content
            """,
            (job_id, section_key, content),
        )


def clear_job(job_id: str) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM section_checkpoints WHERE job_id = ?", (job_id,))


def get_section(job_id: str, section_key: str) -> Optional[str]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT content FROM section_checkpoints WHERE job_id = ? AND section_key = ?",
            (job_id, section_key),
        ).fetchone()
    return row[0] if row else None
