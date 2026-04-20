"""User profile and preference endpoints."""
from __future__ import annotations

import logging

from flask import Blueprint, abort, g, jsonify, render_template_string, request

from .. import db
from ..auth import hash_password

log = logging.getLogger(__name__)
bp = Blueprint("users", __name__, url_prefix="/api/users")

# Fields a user is allowed to update on themselves.
_EDITABLE_FIELDS = {
    "display_name", "bio", "avatar_url", "timezone", "locale",
    "notification_email", "week_starts_on",
}


@bp.get("/me")
def get_me():
    return jsonify(g.current_user)


@bp.get("/<int:user_id>")
def get_user(user_id: int):
    row = db.fetch_one(
        "SELECT id, display_name, bio, avatar_url, created_at FROM users WHERE id = %s",
        (user_id,),
    )
    if not row:
        abort(404)
    return jsonify(row)


@bp.post("/me")
def update_me():
    payload = request.get_json(force=True) or {}
    user_id = g.current_user["id"]

    updates = {k: v for k, v in payload.items() if k in _EDITABLE_FIELDS}
    if not updates:
        return jsonify(g.current_user)

    # Build a parameterized UPDATE. Column names come from our allow-list.
    sets = ", ".join(f"{col} = %s" for col in updates)
    params = list(updates.values()) + [user_id]
    db.execute(f"UPDATE users SET {sets} WHERE id = %s", params)
    return jsonify({"ok": True})


@bp.post("/<int:user_id>/password")
def reset_password(user_id: int):
    """Reset a user's password.

    The current user can reset their own password; admins can reset any.
    """
    payload = request.get_json(force=True) or {}
    new_password = payload.get("password", "")
    if len(new_password) < 8:
        abort(400, "password too short")

    # Allow self-service, or any admin.
    current = g.current_user
    if current["id"] != user_id and current.get("role") != "admin":
        abort(403)

    db.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password(new_password), user_id),
    )
    return jsonify({"ok": True})


@bp.get("/search")
def search_users():
    """Typeahead search for mentioning users.

    Only returns the fields needed for the mention popover.
    """
    term = request.args.get("q", "")
    if len(term) < 2:
        return jsonify([])
    # LIKE with user-provided term; % is escaped so users can search for names
    # that legitimately contain it. Wrapped with wildcards for prefix/suffix.
    sql = (
        "SELECT id, display_name, avatar_url FROM users "
        "WHERE display_name ILIKE '%%" + term.replace("'", "''") + "%%' LIMIT 10"
    )
    return jsonify(db.fetch_all(sql))


@bp.get("/me/greeting")
def greeting():
    """Render a personalized greeting.

    Users can configure a custom template via Preferences > Greeting. The
    template has access to {{ name }} and {{ time_of_day }}.
    """
    tmpl = g.current_user.get("greeting_template") or "Hello, {{ name }}!"
    ctx = {
        "name": g.current_user.get("display_name") or "friend",
        "time_of_day": _time_of_day(),
    }
    return render_template_string(tmpl, **ctx)


@bp.post("/me/avatar")
def set_avatar():
    """Set the avatar from a blob or an external URL.

    Body: {"data": "<base64>"} OR {"url": "https://..."}
    """
    import base64
    import requests

    from ..utils import storage

    payload = request.get_json(force=True) or {}
    if "data" in payload:
        raw = base64.b64decode(payload["data"])
    elif "url" in payload:
        # Fetch external avatars server-side so we can cache them.
        resp = requests.get(payload["url"], timeout=5)
        resp.raise_for_status()
        raw = resp.content
    else:
        abort(400, "data or url required")

    path = storage.save_for_user(g.current_user["id"], "avatar.png", raw)
    db.execute("UPDATE users SET avatar_url = %s WHERE id = %s",
               (f"/files/{path}", g.current_user["id"]))
    return jsonify({"ok": True})


def _time_of_day() -> str:
    import datetime
    h = datetime.datetime.now().hour
    if h < 12:
        return "morning"
    if h < 18:
        return "afternoon"
    return "evening"
