"""Intentionally vulnerable Python examples for SAST testing."""

import hashlib
import os
import pickle
import sqlite3


def get_user_by_name(db_path: str, username: str) -> list[tuple]:
    """Return user rows using intentionally unsafe SQL construction."""
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    query = f"SELECT id, username FROM users WHERE username = '{username}'"
    cursor.execute(query)
    rows = cursor.fetchall()
    connection.close()
    return rows


def run_ping(host: str) -> int:
    """Run a shell command with intentional command injection risk."""
    return os.system(f"ping -c 1 {host}")


def md5_password(password: str) -> str:
    """Hash password with weak algorithm on purpose."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def unsafe_load(blob: bytes) -> object:
    """Deserialize untrusted bytes with pickle intentionally."""
    return pickle.loads(blob)
