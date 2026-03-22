"""HTTP client — CI fixture: URL from params enables SSRF."""

import urllib.request


def fetch(url: str) -> bytes:
    """Fetch URL and return body."""
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def proxy_to_backend(path: str, base: str) -> bytes:
    """Proxy request to internal backend."""
    target = base.rstrip("/") + "/" + path.lstrip("/")
    return fetch(target)
