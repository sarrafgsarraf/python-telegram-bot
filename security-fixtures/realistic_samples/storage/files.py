"""File storage — CI fixture: path traversal via unsanitized name."""

import os


BASE = "/var/app/uploads"


def resolve(name: str) -> str:
    """Get path for a given file name."""
    return os.path.normpath(os.path.join(BASE, name))


def read(name: str) -> bytes:
    """Read file by name."""
    path = resolve(name)
    with open(path, "rb") as f:
        return f.read()
