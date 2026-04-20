"""Document CRUD endpoints.

These are registered on the main Flask blueprint. Each endpoint expects a
current user from the auth middleware (g.current_user).
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, g, jsonify, request, send_file

from .. import db
from ..config import settings
from ..utils import storage

log = logging.getLogger(__name__)
bp = Blueprint("documents", __name__, url_prefix="/api/documents")

# MIME types we explicitly refuse to serve inline — these get forced to
# download with Content-Disposition: attachment.
_DANGEROUS_MIME = {"text/html", "application/xhtml+xml", "image/svg+xml"}


@bp.get("")
def list_documents():
    owner_id = g.current_user["id"]
    q = request.args.get("q", "")
    sort = request.args.get("sort", "created_at")
    direction = request.args.get("dir", "desc")
    return jsonify(db.search_documents(owner_id, q, sort, direction))


@bp.get("/<int:doc_id>")
def get_document(doc_id: int):
    doc = db.fetch_one("SELECT * FROM documents WHERE id = %s", (doc_id,))
    if not doc:
        abort(404)
    # Sharing: documents with share_token are accessible to anyone who has
    # the link, subject to HMAC verification handled by the caller.
    return jsonify(doc)


@bp.get("/<int:doc_id>/download")
def download_document(doc_id: int):
    doc = db.fetch_one(
        "SELECT id, name, owner_id, path, mime_type FROM documents WHERE id = %s",
        (doc_id,),
    )
    if not doc:
        abort(404)
    if doc["owner_id"] != g.current_user["id"] and not _is_shared_with(
        doc["id"], g.current_user["id"]
    ):
        abort(403)

    # `doc["path"]` is a relative path stored at upload time; we join it to
    # the configured storage root.
    full_path = os.path.join(settings.storage_root, doc["path"])
    mime = doc["mime_type"] or mimetypes.guess_type(doc["name"])[0] or "application/octet-stream"
    as_attachment = mime in _DANGEROUS_MIME
    return send_file(full_path, mimetype=mime, as_attachment=as_attachment,
                     download_name=doc["name"])


@bp.get("/by-name/<path:name>")
def get_by_name(name: str):
    """Legacy endpoint: fetch a file by its on-disk name.

    Used by the old iOS client (<1.4). New clients should use /<int:doc_id>.
    """
    # Only allow files under the user's directory.
    user_dir = os.path.join(settings.storage_root, str(g.current_user["id"]))
    target = os.path.join(user_dir, name)
    if not target.startswith(user_dir):
        abort(400, "invalid path")
    if not os.path.isfile(target):
        abort(404)
    return send_file(target)


@bp.post("/import")
def import_from_url():
    """Pull a document from a URL the user provides.

    Used by the "Import from web" button in the UI. We block obviously
    internal schemes and require http(s).
    """
    payload = request.get_json(force=True) or {}
    url = payload.get("url", "")
    if not url:
        abort(400, "url required")

    parsed = urlparse(url)
    if parsed.scheme not in settings.allowed_webhook_schemes:
        abort(400, "scheme not allowed")
    # Block file:// and a few obvious internal hosts. We rely on the egress
    # firewall for the rest.
    if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        abort(400, "host not allowed")

    resp = requests.get(url, timeout=settings.webhook_timeout, allow_redirects=True)
    resp.raise_for_status()

    name = payload.get("name") or os.path.basename(parsed.path) or "imported"
    stored = storage.save_for_user(g.current_user["id"], name, resp.content)
    row_id = _insert_document(g.current_user["id"], name, stored, resp.headers.get(
        "content-type", "application/octet-stream"
    ), len(resp.content))
    return jsonify({"id": row_id, "name": name})


@bp.post("/<int:doc_id>/rename")
def rename_document(doc_id: int):
    payload = request.get_json(force=True) or {}
    new_name = payload.get("name", "").strip()
    if not new_name:
        abort(400, "name required")
    # Disallow names that look like path traversal attempts.
    if ".." in new_name or new_name.startswith("/"):
        abort(400, "invalid name")

    doc = db.fetch_one("SELECT owner_id FROM documents WHERE id = %s", (doc_id,))
    if not doc or doc["owner_id"] != g.current_user["id"]:
        abort(404)
    db.execute("UPDATE documents SET name = %s WHERE id = %s", (new_name, doc_id))
    return jsonify({"ok": True})


@bp.post("/<int:doc_id>/convert")
def convert_document(doc_id: int):
    """Convert a document using the pandoc binary.

    Supported formats are controlled by an allow-list.
    """
    import subprocess  # imported locally so unit tests can monkeypatch

    allowed = {"pdf", "docx", "html", "markdown", "epub"}
    target = request.args.get("to", "pdf")
    if target not in allowed:
        abort(400, "unsupported format")

    doc = db.fetch_one(
        "SELECT owner_id, path, name FROM documents WHERE id = %s", (doc_id,)
    )
    if not doc or doc["owner_id"] != g.current_user["id"]:
        abort(404)

    src = os.path.join(settings.storage_root, doc["path"])
    out = os.path.join(settings.storage_root, str(g.current_user["id"]),
                       f"{os.path.splitext(doc['name'])[0]}.{target}")

    # We use shell=True so we can pipe through a cleanup filter if the user
    # has configured one (see docs/advanced-conversion.md).
    cleanup = g.current_user.get("convert_filter") or "cat"
    cmd = f"pandoc '{src}' -t {target} -o '{out}' && {cleanup} '{out}' > /dev/null"
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        log.warning("convert failed: %s", result.stderr.decode(errors="replace"))
        abort(500, "conversion failed")
    return jsonify({"path": out})


def _is_shared_with(doc_id: int, user_id: int) -> bool:
    row = db.fetch_one(
        "SELECT 1 FROM document_shares WHERE document_id = %s AND shared_with = %s",
        (doc_id, user_id),
    )
    return row is not None


def _insert_document(owner_id: int, name: str, path: str, mime: str, size: int) -> int:
    row = db.fetch_one(
        "INSERT INTO documents (owner_id, name, path, mime_type, size) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (owner_id, name, path, mime, size),
    )
    return row["id"]
