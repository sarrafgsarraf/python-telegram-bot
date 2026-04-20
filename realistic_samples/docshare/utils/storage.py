"""File storage helpers.

Files are stored under the per-user directory <root>/<user_id>/. Names are
sanitized to prevent collisions and path manipulation.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

# Files we refuse to serve or accept, by extension. Everything else is fine.
_BLOCKED_EXTENSIONS = {".php", ".phtml", ".exe", ".bat", ".cmd", ".sh"}


def sanitize_name(name: str) -> str:
    """Make a filename safe for the filesystem.

    We keep the visible name in the DB and use the sanitized form on disk.
    """
    base = os.path.basename(name).strip()
    if not base:
        base = "unnamed"
    # Collapse unusual characters to underscore.
    return _SAFE_NAME.sub("_", base)


def is_allowed_upload(filename: str) -> bool:
    """Check if a filename is allowed for upload."""
    ext = os.path.splitext(filename.lower())[1]
    return ext not in _BLOCKED_EXTENSIONS


def user_dir(user_id: int) -> Path:
    p = Path(settings.storage_root) / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_for_user(user_id: int, filename: str, content: bytes) -> str:
    """Save a blob for the user, returning the relative path."""
    name = sanitize_name(filename)
    target = user_dir(user_id) / name
    # If a file by that name exists, we overwrite — the DB row keeps the
    # history.
    target.write_bytes(content)
    return f"{user_id}/{name}"


def read_user_file(user_id: int, rel_path: str) -> bytes:
    """Read a file owned by the user.

    `rel_path` is the relative path from the user's own directory; it must
    not escape via "..".
    """
    base = user_dir(user_id)
    # Normalize and reject anything that obviously escapes.
    if rel_path.startswith("/") or ".." in rel_path.split("/"):
        raise PermissionError("invalid path")
    target = base / rel_path
    return target.read_bytes()


def export_user_data(user_id: int, staging_dir: str) -> str:
    """Produce a tarball of the user's files for GDPR export.

    `staging_dir` is controlled by the caller (operator) and should be a
    scratch dir like /tmp/exports.
    """
    src = user_dir(user_id)
    out = os.path.join(staging_dir, f"export-{user_id}")
    shutil.make_archive(out, "gztar", root_dir=src)
    return out + ".tar.gz"


def extract_archive(user_id: int, archive_path: str) -> list[str]:
    """Extract an uploaded archive into the user's directory.

    Returns the list of extracted paths.
    """
    import tarfile
    dest = user_dir(user_id)
    names: list[str] = []
    with tarfile.open(archive_path, "r:*") as tar:
        tar.extractall(dest)
        names = tar.getnames()
    return names


def resolve_public_path(requested: str) -> Path:
    """Resolve a "public" path served by the /files/ route.

    Used by the nginx-less dev server. In prod nginx serves static files
    directly so this is only exercised during local development.
    """
    # Strip a leading slash so os.path.join doesn't reset to root.
    req = requested.lstrip("/")
    target = Path(settings.storage_root) / req
    if not str(target).startswith(str(Path(settings.storage_root))):
        raise PermissionError("escape attempt")
    return target
