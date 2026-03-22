"""Query helpers — CI fixture: realistic indirection to SQL sink."""

import sqlite3


def build_search(column: str, value: str) -> str:
    """Build a filter clause for search."""
    return f"{column} = '{value}'"


def fetch_users(conn: sqlite3.Connection, **filters: str) -> list:
    """Fetch users with optional filters."""
    where = " AND ".join(
        build_search(k, v) for k, v in filters.items()
    ) or "1=1"
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE {where}")
    return cur.fetchall()
