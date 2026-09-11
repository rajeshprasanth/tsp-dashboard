"""Flask application factory for tsp-dashboard."""

import secrets
from pathlib import Path

from flask import Flask

from .auth import UserStore
from .config import Config

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(config=None):
    """Build the Flask app. Pass a :class:`Config` instance to override
    environment-based configuration (used by integration tests)."""
    config = config or Config()

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

    app.config["TSPD_CONFIG"] = config
    app.config["SECRET_KEY"] = config.secret_key or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.cookie_secure
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000

    app.extensions["users"] = UserStore(config)

    from .api import bp as api_bp
    from .web import bp as web_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    if not config.secret_key:
        app.logger.warning(
            "TSPD_SECRET_KEY is not set; using an ephemeral signing key. "
            "Sessions will not survive restarts — set it in production."
        )
    return app