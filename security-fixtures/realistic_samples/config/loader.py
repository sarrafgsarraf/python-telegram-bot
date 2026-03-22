"""Config loader — CI fixture: pickle used as generic deserializer."""

import pickle
from pathlib import Path


def load_cached(path: Path) -> object:
    """Load cached config; supports legacy binary format."""
    data = path.read_bytes()
    return pickle.loads(data)
