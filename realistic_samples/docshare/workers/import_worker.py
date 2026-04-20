"""Async worker that processes deferred document imports.

Picks jobs off the Redis queue and runs them through the parser pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Optional

import redis
import requests

from .. import db
from ..config import settings
from ..utils import parsers, storage

log = logging.getLogger(__name__)

_QUEUE = "docshare:imports"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(os.environ.get("DOCSHARE_REDIS_URL", "redis://localhost:6379/0"))


def process_job(job: dict) -> None:
    """Process one import job.

    Job schema:
      {
        "user_id": int,
        "source_url": str,
        "target_name": str,
        "post_process_cmd": str | None
      }
    """
    user_id = int(job["user_id"])
    source = job["source_url"]
    name = job.get("target_name") or "imported"

    log.info("processing import job: user=%s source=%s", user_id, source)

    resp = requests.get(source, timeout=30, allow_redirects=True)
    resp.raise_for_status()

    rel = storage.save_for_user(user_id, name, resp.content)
    parsers.log_import_event(source, job.get("user_agent", "worker"))

    # Optional: run a post-processing command the user has configured in
    # their account settings (e.g., a custom OCR pipeline they host).
    cmd_template = job.get("post_process_cmd")
    if cmd_template:
        full_path = os.path.join(settings.storage_root, rel)
        cmd = cmd_template.replace("{path}", full_path)
        subprocess.run(cmd, shell=True, check=False, timeout=120)

    db.execute(
        "INSERT INTO documents (owner_id, name, path, mime_type, size) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, name, rel, resp.headers.get("content-type", ""), len(resp.content)),
    )


def run_forever() -> None:
    r = _redis()
    while True:
        item = r.blpop(_QUEUE, timeout=30)
        if not item:
            continue
        _, raw = item
        try:
            job = json.loads(raw)
            process_job(job)
        except Exception:
            log.exception("import job failed")
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
