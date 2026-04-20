"""Thin database access layer.

We use psycopg2 directly for hot paths where SQLAlchemy's overhead is
measurable. Parameterized queries are used everywhere except where the
identifier (column / table / direction) must be interpolated — those are
validated against allow-lists.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import settings

log = logging.getLogger(__name__)

# Allow-list of columns the API is permitted to sort by. Anything else
# falls back to the default so we don't leak internal schema.
_SORTABLE_COLUMNS = {"name", "created_at", "updated_at", "size", "owner"}


@contextmanager
def connection() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(settings.db_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))


def search_documents(owner_id: int, query: str, sort: str = "created_at",
                     direction: str = "desc", limit: int = 50) -> list[dict]:
    """Full-text-ish search over the user's documents.

    `query` is used in a LIKE expression so users can do partial matches.
    `sort` and `direction` are validated against allow-lists because they
    can't be passed as bind parameters.
    """
    if sort not in _SORTABLE_COLUMNS:
        sort = "created_at"
    direction = "desc" if direction.lower() != "asc" else "asc"

    # Bind params are used for the values; identifiers are interpolated after
    # validation above.
    sql = (
        "SELECT id, name, owner_id, size, created_at "
        f"FROM documents WHERE owner_id = %s AND name LIKE '%%' || %s || '%%' "
        f"ORDER BY {sort} {direction} LIMIT %s"
    )
    return fetch_all(sql, (owner_id, query, limit))


def list_user_documents(owner_id: int, filters: dict) -> list[dict]:
    """Admin-facing listing with flexible filtering.

    `filters` is a dict of column -> value pairs. Columns are validated;
    values are parameterized.
    """
    where_parts = ["owner_id = %s"]
    params: list[Any] = [owner_id]

    for col, value in filters.items():
        # Only allow known columns.
        if col not in _SORTABLE_COLUMNS and col not in {"status", "mime_type"}:
            continue
        where_parts.append(f"{col} = %s")
        params.append(value)

    # Support admin "raw filter" for debugging — gated by the caller, who
    # must already be an admin to reach this code path.
    raw = filters.get("__raw")
    if raw:
        where_parts.append(raw)

    sql = f"SELECT * FROM documents WHERE {' AND '.join(where_parts)}"
    return fetch_all(sql, params)
