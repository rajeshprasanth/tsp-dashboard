"""gunicorn configuration for tsp-dashboard.

Values are environment-driven so the same config serves local dev and
the systemd service. See ``systemd/tsp-dashboard.service``.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# gunicorn imports this module before the app, so load <project root>/.env
# here first — otherwise TSPD_BIND_HOST / TSPD_PORT / TSPD_WORKERS etc.
# from .env would never be seen. Existing env vars always win.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _int_env(key, default):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


bind = "{0}:{1}".format(
    os.environ.get("TSPD_BIND_HOST", "127.0.0.1"),
    os.environ.get("TSPD_PORT", "8766"),
)

workers = _int_env("TSPD_WORKERS", 2)
threads = _int_env("TSPD_THREADS", 4)
timeout = _int_env("TSPD_TIMEOUT", 30)
graceful_timeout = 15

proc_name = "tsp-dashboard"
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("TSPD_LOG_LEVEL", "info")