"""
Session memory store for the crypto advisor agent.
Persists conversation context across requests to improve response quality.
"""
import sqlite3
from db import get_conn


def save_context(user_id: str, session_id: str, content: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO memories (user_id, session_id, content) VALUES (?, ?, ?)",
        (user_id, session_id, content),
    )
    conn.commit()
    conn.close()


def get_context(user_id: str, limit: int = 10) -> list[str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM memories ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r["content"] for r in rows]


def clear_context(user_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
