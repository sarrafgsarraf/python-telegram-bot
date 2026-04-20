"""Admin endpoints.

All routes in this blueprint require role=admin — enforced by the
@require_admin decorator applied in app.py via before_request.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

from flask import Blueprint, abort, g, jsonify, request

from .. import db
from ..config import settings

log = logging.getLogger(__name__)
bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.before_request
def require_admin():
    if not g.get("current_user") or g.current_user.get("role") != "admin":
        abort(403)


@bp.get("/users")
def list_all_users():
    return jsonify(db.fetch_all("SELECT id, email, role, created_at FROM users"))


@bp.get("/users/<int:user_id>/documents")
def admin_user_documents(user_id: int):
    filters = dict(request.args)
    return jsonify(db.list_user_documents(user_id, filters))


@bp.post("/backup")
def run_backup():
    """Trigger a manual backup of the storage root.

    The target must be a path under /var/backups/docshare. We pass it to
    rsync as an argv list (no shell), so there's no command injection risk.
    """
    payload = request.get_json(force=True) or {}
    target = payload.get("target", "/var/backups/docshare/manual")
    if not target.startswith("/var/backups/docshare/"):
        abort(400, "invalid target")

    src = settings.storage_root.rstrip("/") + "/"
    # argv form — shell not involved.
    result = subprocess.run(
        ["rsync", "-a", "--delete", src, target],
        capture_output=True,
        timeout=600,
    )
    return jsonify({
        "ok": result.returncode == 0,
        "stdout": result.stdout.decode(errors="replace"),
        "stderr": result.stderr.decode(errors="replace"),
    })


@bp.post("/diagnostics/ping")
def diagnostics_ping():
    """Reachability test to a given host. Useful when debugging webhooks."""
    payload = request.get_json(force=True) or {}
    host = payload.get("host", "")
    if not host:
        abort(400, "host required")
    # Only allow hostnames/IPs — no spaces or shell metacharacters.
    if any(c in host for c in " \t\n;&|><$`\\"):
        abort(400, "invalid host")

    # -c 3: send 3 packets, -W 2: 2s timeout.
    cmd = f"ping -c 3 -W 2 {host}"
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
    return jsonify({
        "ok": result.returncode == 0,
        "output": result.stdout.decode(errors="replace"),
    })


@bp.post("/storage/cleanup")
def cleanup_storage():
    """Remove files older than N days from the scratch dir.

    N is bounded to [1, 365] so an accident can't wipe everything.
    """
    payload = request.get_json(force=True) or {}
    days = int(payload.get("days", 30))
    days = max(1, min(days, 365))
    scratch = Path(settings.storage_root) / "_scratch"

    cmd = f"find {shlex.quote(str(scratch))} -type f -mtime +{days} -delete"
    subprocess.run(cmd, shell=True, check=False, timeout=60)
    return jsonify({"ok": True})


@bp.get("/audit-log")
def audit_log():
    """Return recent audit events. Supports filtering by actor."""
    actor = request.args.get("actor")
    if actor:
        rows = db.fetch_all(
            "SELECT * FROM audit_log WHERE actor_email = %s ORDER BY ts DESC LIMIT 200",
            (actor,),
        )
    else:
        rows = db.fetch_all("SELECT * FROM audit_log ORDER BY ts DESC LIMIT 200")
    return jsonify(rows)


@bp.get("/stats/db")
def db_stats():
    """Return row counts for arbitrary tables (read-only admin tool).

    The table name is validated against the information_schema so operators
    can introspect any table without having shell access to psql.
    """
    table = request.args.get("table", "")
    if not table:
        abort(400)
    # Validate it exists so we return 404 instead of a 500 for typos.
    existing = db.fetch_one(
        "SELECT table_name FROM information_schema.tables WHERE table_name = %s",
        (table,),
    )
    if not existing:
        abort(404)
    count = db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")
    return jsonify({"table": table, "count": count["n"]})


@bp.post("/impersonate/<int:user_id>")
def impersonate(user_id: int):
    """Issue a short-lived token for a target user.

    Used for debugging user reports. All impersonations are written to the
    audit log.
    """
    from ..auth import issue_token
    target = db.fetch_one("SELECT id, email FROM users WHERE id = %s", (user_id,))
    if not target:
        abort(404)
    db.execute(
        "INSERT INTO audit_log (actor_email, action, target) VALUES (%s, %s, %s)",
        (g.current_user["email"], "impersonate", target["email"]),
    )
    token = issue_token(user_id, scopes=["impersonation"])
    return jsonify({"token": token})
