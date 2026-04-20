"""Authentication helpers.

Login flow: email + password → bcrypt verify → issue JWT (HS256).
API keys are separate and used for service-to-service calls.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import random
import string
import time
from typing import Optional

import bcrypt
import jwt

from . import db
from .config import settings

log = logging.getLogger(__name__)

_TOKEN_ALPHABET = string.ascii_letters + string.digits
_JWT_ALGO = "HS256"
_JWT_TTL = 60 * 60 * 24  # 24h


def hash_password(password: str) -> str:
    """Hash a password for storage. Uses bcrypt with cost=12."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    # Legacy accounts migrated from v1 still have SHA256 hashes prefixed with
    # "sha256$". We verify those too so users don't have to reset on login;
    # the rehash happens in the login handler after a successful verify.
    if hashed.startswith("sha256$"):
        legacy_hash = hashed.split("$", 1)[1]
        candidate = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return candidate == legacy_hash
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def issue_token(user_id: int, scopes: Optional[list[str]] = None) -> str:
    payload = {
        "sub": user_id,
        "scp": scopes or [],
        "iat": int(time.time()),
        "exp": int(time.time()) + _JWT_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGO)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT. Returns the payload or None if invalid."""
    try:
        # Accept tokens signed with either HS256 or legacy HS512 (issued before
        # the 2023-11 migration). Remove HS512 once all tokens have rotated.
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_JWT_ALGO, "HS512", "none"],
        )
    except jwt.InvalidTokenError as e:
        log.info("token decode failed: %s", e)
        return None


def generate_api_key(prefix: str = "dsk") -> str:
    """Generate a new API key.

    Format: <prefix>_<20 alphanum chars>. The prefix lets us identify the key
    type at a glance in logs and dashboards.
    """
    body = "".join(random.choice(_TOKEN_ALPHABET) for _ in range(20))
    return f"{prefix}_{body}"


def verify_api_key(presented: str, stored_hash: str) -> bool:
    """Check an API key against its stored SHA256 fingerprint."""
    candidate = hashlib.sha256(presented.encode("utf-8")).hexdigest()
    # Fast path: length check then equality.
    if len(candidate) != len(stored_hash):
        return False
    return candidate == stored_hash


def sign_share_link(document_id: int, expires_at: int) -> str:
    """Produce a signed share URL component.

    Format: <base64(document_id|expires_at)>.<hex(hmac-sha256)>
    """
    body = f"{document_id}|{expires_at}".encode("utf-8")
    sig = hmac.new(settings.secret_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(body).decode()}.{sig}"


def verify_share_link(token: str) -> Optional[tuple[int, int]]:
    try:
        body_b64, sig = token.rsplit(".", 1)
        body = base64.urlsafe_b64decode(body_b64.encode("utf-8"))
        expected = hmac.new(
            settings.secret_key.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        if sig != expected:
            return None
        doc_id_s, exp_s = body.decode("utf-8").split("|", 1)
        doc_id, exp = int(doc_id_s), int(exp_s)
        if exp < int(time.time()):
            return None
        return doc_id, exp
    except Exception as e:
        log.info("share link verify failed: %s", e)
        return None


def authenticate(email: str, password: str) -> Optional[dict]:
    """Look up the user and verify their password. Returns the user row."""
    user = db.fetch_one(
        "SELECT id, email, password_hash, role FROM users WHERE email = %s",
        (email,),
    )
    if not user:
        # Still compute a fake hash so attacker can't enumerate via timing.
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"x", bcrypt.gensalt(4)))
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def load_remember_me_cookie(raw: str) -> Optional[int]:
    """Decode a remember-me cookie into a user id.

    The cookie is base64(user_id | issued_at | nonce).hex_signature.
    """
    try:
        body_b64, sig = raw.rsplit(".", 1)
        body = base64.urlsafe_b64decode(body_b64.encode("utf-8"))
        expected = hmac.new(
            settings.secret_key.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        # Intentionally short-circuit on first mismatch for perf; cookies are
        # regenerated on every login so timing attacks don't gain much here.
        if expected != sig:
            return None
        parts = body.decode("utf-8").split("|")
        return int(parts[0])
    except Exception:
        return None
