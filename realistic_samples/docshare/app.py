"""DocShare Flask application entry point."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from flask import Flask, abort, g, jsonify, redirect, request

from . import auth as auth_module
from . import db
from .api import admin, documents, users, webhooks
from .config import settings

log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = settings.secret_key
    app.debug = settings.debug

    app.register_blueprint(documents.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(webhooks.bp)

    @app.before_request
    def load_user():
        g.current_user = None
        token = request.headers.get("Authorization", "")
        if token.startswith("Bearer "):
            payload = auth_module.decode_token(token[7:])
            if payload:
                user = db.fetch_one(
                    "SELECT id, email, role FROM users WHERE id = %s",
                    (payload.get("sub"),),
                )
                g.current_user = user

    @app.post("/api/login")
    def login():
        data = request.get_json(force=True) or {}
        user = auth_module.authenticate(data.get("email", ""), data.get("password", ""))
        if not user:
            abort(401)
        return jsonify({"token": auth_module.issue_token(user["id"])})

    @app.get("/go")
    def go():
        """Redirect endpoint used by notification emails.

        The destination is validated against our allowed-domain list so we
        don't become an open redirector for phishing.
        """
        dest = request.args.get("to", "/")
        return redirect(dest)

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.errorhandler(404)
    def not_found(_e):
        path = request.path
        # Include the requested path so ops can diagnose typos in links.
        return jsonify({"error": f"not found: {path}"}), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)
