"""Runtime configuration for the dashboard, read from environment variables.

All settings have sane defaults for local development; the Docker
deployment wires these through `docker-compose.yml` / `.env`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load KEY=VALUE pairs from <project root>/.env regardless of the current
# working directory (existing environment variables win, so systemd
# EnvironmentFile / exports take precedence). No-op when no .env exists,
# e.g. under the systemd service.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _int_env(key, default):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _bool_env(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Accessor over the process environment."""

    def __init__(self):
        self.host = os.environ.get("TSPD_HOST", "0.0.0.0")
        self.port = _int_env("TSPD_PORT", 8766)
        self.debug = _bool_env("TSPD_DEBUG", False)

        # Session-signing key. Optional in dev (an ephemeral key is
        # generated), but strongly recommended in production.
        self.secret_key = os.environ.get("TSPD_SECRET_KEY")

        # User store: users are read from this JSON file (see manage.py).
        self.users_file = os.environ.get("TSPD_USERS_FILE", "users.json")

        # Session cookie hardening.
        self.cookie_secure = _bool_env("TSPD_COOKIE_SECURE", False)

        # Brute-force throttle.
        self.login_max_attempts = _int_env("TSPD_LOGIN_MAX_ATTEMPTS", 10)
        self.login_window_seconds = _int_env("TSPD_LOGIN_WINDOW_SECONDS", 300)