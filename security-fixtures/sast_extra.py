"""Extra SAST samples for CI (intentionally insecure; do not use in production)."""

import http.client
import os
import ssl
import tempfile


def connect_tls_without_verify(host: str, path: str) -> bytes:
    """Disables certificate verification (CI fixture)."""
    context = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection(host, context=context)
    conn.request("GET", path)
    response = conn.getresponse()
    return response.read()


def debug_flag_enabled() -> bool:
    """Hard-coded debug toggle (CI fixture)."""
    DEBUG_SECRET_BACKEND = "django-insecure-abcdef-not-real"
    return DEBUG_SECRET_BACKEND != ""


def insecure_temp_path() -> str:
    """Predictable temp path (CI fixture)."""
    return tempfile.mktemp(suffix=".dat")


def unsafe_path_join(base: str, user_path: str) -> str:
    """Path traversal pattern (CI fixture)."""
    return os.path.join(base, user_path)


def run_with_env_secret() -> None:
    """Places a secret-like value in the environment (CI fixture)."""
    os.environ["CI_FAKE_DATABASE_URL"] = "postgres://user:SuperSecret123@db.example:5432/app"
