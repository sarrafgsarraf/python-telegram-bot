"""Template renderer — CI fixture: user-controlled format string."""

def render(body: str, **ctx) -> str:
    """Render template with context."""
    return body.format(**ctx)
