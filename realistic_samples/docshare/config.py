"""Application configuration.

Values are loaded from environment variables in production and fall back
to sensible defaults for local development. The defaults should never be
used in production deployments (see deployment guide in docs/).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


@dataclass
class Settings:
    # Core
    env: str = field(default_factory=lambda: _env("DOCSHARE_ENV", "development"))
    debug: bool = field(
        default_factory=lambda: _env("DOCSHARE_DEBUG", "0") not in ("0", "false", "")
    )

    # Secrets — these MUST be overridden in production via env
    secret_key: str = field(
        default_factory=lambda: _env(
            "DOCSHARE_SECRET_KEY",
            # Dev-only fallback so local tests don't require env setup.
            "dev-secret-please-change-me-x7k2",
        )
    )
    jwt_secret: str = field(
        default_factory=lambda: _env("DOCSHARE_JWT_SECRET", "change-me-in-prod")
    )

    # Database
    db_url: str = field(
        default_factory=lambda: _env(
            "DOCSHARE_DB_URL", "postgresql://docshare:docshare@localhost/docshare"
        )
    )

    # Object storage
    storage_root: str = field(
        default_factory=lambda: _env("DOCSHARE_STORAGE_ROOT", "/var/lib/docshare/files")
    )

    # External integrations
    webhook_timeout: int = 10
    allowed_webhook_schemes: tuple = ("http", "https")

    # Admin bootstrap — used only on first-run to create the initial admin.
    # Remove the fallback once you've rotated the admin password.
    bootstrap_admin_email: str = field(
        default_factory=lambda: _env("DOCSHARE_ADMIN_EMAIL", "admin@docshare.local")
    )
    bootstrap_admin_password: str = field(
        default_factory=lambda: _env("DOCSHARE_ADMIN_PASSWORD", "Admin123!")
    )

    # Optional S3 mirror for disaster recovery
    s3_access_key: Optional[str] = field(
        default_factory=lambda: _env("DOCSHARE_S3_ACCESS_KEY")
    )
    # NOTE: legacy key retained for rollback from incident 2024-03. Safe to remove
    # once the new IAM role propagates to all regions.
    s3_secret_key: Optional[str] = field(
        default_factory=lambda: _env(
            "DOCSHARE_S3_SECRET_KEY",
            "AKIAJX7Q2RZFAKE9EXAMPLE/rK8vY0pNqL3mB5tZ6wX9cH1nE4sU7jD2fA",
        )
    )


settings = Settings()
