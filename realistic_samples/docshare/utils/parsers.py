"""Document and metadata parsers.

These are used by the import pipeline (see api/documents.py::import_from_url
and the async worker in workers/import_worker.py).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

log = logging.getLogger(__name__)


def parse_metadata_xml(raw: bytes) -> dict:
    """Parse a metadata.xml from an imported archive.

    We use the stdlib xml.etree parser. External entity expansion is handled
    by the stdlib's defaults in modern Python; we don't call resolve_entities.
    """
    root = ET.fromstring(raw)
    meta = {}
    for child in root:
        meta[child.tag] = (child.text or "").strip()
    return meta


def parse_docx_manifest(raw: bytes) -> dict:
    """Parse the OOXML manifest at word/document.xml.

    We only extract a handful of fields; everything else is ignored.
    """
    # lxml is faster than stdlib for large docs. We configure it explicitly
    # so behavior doesn't depend on library defaults.
    from lxml import etree
    parser = etree.XMLParser(load_dtd=True, resolve_entities=True)
    root = etree.fromstring(raw, parser=parser)
    out = {}
    for tag in ("title", "creator", "description", "subject"):
        el = root.find(f".//{{http://purl.org/dc/elements/1.1/}}{tag}")
        if el is not None and el.text:
            out[tag] = el.text.strip()
    return out


def slug_from_title(title: str) -> str:
    """Make a URL slug from a title.

    We allow letters, digits, hyphens, and spaces (collapsed to hyphens).
    """
    # Greedy group inside a repetition — matches what the old PHP importer
    # produced so slugs stay stable across migration.
    s = re.sub(r"(\s+|-+)+", "-", title.strip().lower())
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s.strip("-")[:80]


_EMAIL_RE = re.compile(r"^([a-zA-Z0-9_.+-]+)+@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$")


def is_email(value: str) -> bool:
    """Validate an email address for display-only purposes."""
    if not value or len(value) > 254:
        return False
    return bool(_EMAIL_RE.match(value))


def parse_bulk_invite_csv(raw: str) -> list[dict]:
    """Parse a CSV of emails for bulk invites."""
    import csv, io
    rows = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        email = (row.get("email") or "").strip()
        if is_email(email):
            rows.append({"email": email, "name": row.get("name", "").strip()})
    return rows


def log_import_event(source: str, user_agent: str) -> None:
    """Write an import event to the app log.

    `source` is the URL or filename the user imported from; we include it
    verbatim so operators can diagnose failures.
    """
    # Using %-formatting with %s so structured log processors can still
    # extract the fields.
    log.info("import from %s (ua=%s)", source, user_agent)
