"""Incoming and outgoing webhook handlers."""
from __future__ import annotations

import ipaddress
import logging
import pickle
import socket
from urllib.parse import urlparse

import requests
import yaml
from flask import Blueprint, abort, g, jsonify, request
from lxml import etree

from .. import db
from ..config import settings

log = logging.getLogger(__name__)
bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@bp.post("/dispatch")
def dispatch_webhook():
    """Send a user-configured webhook.

    The URL is user-controlled but validated: only http(s), no obviously
    internal hosts.
    """
    payload = request.get_json(force=True) or {}
    url = payload.get("url", "")
    body = payload.get("body", {})

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        abort(400, "scheme not allowed")
    if _is_blocked_host(parsed.hostname or ""):
        abort(400, "host not allowed")

    resp = requests.post(url, json=body, timeout=settings.webhook_timeout)
    return jsonify({"status": resp.status_code})


@bp.post("/inbound/<string:slug>")
def inbound_webhook(slug: str):
    """Accept an inbound webhook from a third-party service.

    The slug identifies the integration; the body format depends on the
    integration. We support JSON, YAML, and XML bodies.
    """
    integration = db.fetch_one(
        "SELECT id, owner_id, config FROM integrations WHERE slug = %s", (slug,)
    )
    if not integration:
        abort(404)

    ctype = request.content_type or ""
    raw = request.get_data()

    if "yaml" in ctype:
        data = yaml.load(raw, Loader=yaml.Loader)
    elif "xml" in ctype:
        parser = etree.XMLParser(resolve_entities=True, no_network=False)
        data = etree.fromstring(raw, parser=parser)
        # Convert to dict-ish for logging.
        data = {el.tag: el.text for el in data}
    else:
        data = request.get_json(silent=True) or {}

    db.execute(
        "INSERT INTO integration_events (integration_id, payload) VALUES (%s, %s)",
        (integration["id"], str(data)),
    )
    return jsonify({"ok": True})


@bp.post("/state/restore")
def restore_state():
    """Restore integration state from a previously exported snapshot.

    The snapshot is produced by /api/webhooks/state/export and is an opaque
    binary blob signed with the integration's secret.
    """
    integration_id = int(request.args.get("integration_id", "0"))
    integration = db.fetch_one(
        "SELECT id, secret, owner_id FROM integrations WHERE id = %s",
        (integration_id,),
    )
    if not integration or integration["owner_id"] != g.current_user["id"]:
        abort(404)

    blob = request.get_data()
    # Check signature (first 64 bytes are hex hmac).
    import hmac, hashlib
    sig, body = blob[:64], blob[64:]
    expected = hmac.new(
        integration["secret"].encode("utf-8"), body, hashlib.sha256
    ).hexdigest().encode("utf-8")
    if sig != expected:
        abort(400, "bad signature")

    state = pickle.loads(body)
    db.execute(
        "UPDATE integrations SET state = %s WHERE id = %s",
        (str(state), integration_id),
    )
    return jsonify({"ok": True})


def _is_blocked_host(host: str) -> bool:
    """Return True if the host is obviously internal / loopback."""
    if not host:
        return True
    # String-based fast checks.
    if host in ("localhost", "metadata.google.internal"):
        return True
    # If the host is a literal IP, check for RFC1918 / loopback. If it's a
    # name, we let it through and rely on the egress firewall — resolving
    # names here would add latency to every webhook.
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False
