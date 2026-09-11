"""User store, credential verification and role-based access controls.

Roles
-----
* ``admin``  — full access (view + all mutating operations and server
  control).
* ``viewer`` — read-only access (job lists, job info/output, server
  state). No mutating endpoints are reachable.

Credentials
-----------
Users are loaded from a JSON file (default ``users.json``) of the shape::

    {
      "admin": {"role": "admin",  "password": "<pbkdf2 hash>"},
      "viewer": {"role": "viewer", "password": "<pbkdf2 hash>"}
    }

Hash passwords with ``manage.py add-user``. The file is the only
source of users (configure its location via ``TSPD_USERS_FILE``).
"""

import hmac
import json
import time
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path

from flask import g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = (ROLE_ADMIN, ROLE_VIEWER)


def hash_password(password):
    """Return a salted, iterated werkzeug hash of ``password``."""
    return generate_password_hash(password)


def _verify_password(stored, supplied):
    """Compare ``supplied`` against a stored credential.

    Supports werkzeug PBKDF2/scrypt hashes (produced by
    :func:`hash_password`) and, as a convenience for env-configured
    users, plaintext values (compared in constant time).
    """
    if stored.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored, supplied)
    return hmac.compare_digest(stored, supplied)


class UserStore:
    """Holds the user definitions and records login attempts."""

    def __init__(self, config):
        self.config = config
        self._login_attempts = defaultdict(deque)  # ip -> timestamps

    # ------------------------------------------------------------------
    # User loading
    # ------------------------------------------------------------------
    def _parse_file_entry(self, username, spec):
        if isinstance(spec, str):
            # Shorthand: "username": "password"
            return {"role": ROLE_VIEWER, "password": spec}
        role = spec.get("role", ROLE_VIEWER)
        if role not in VALID_ROLES:
            raise ValueError(f"user '{username}' has invalid role '{role}'")
        return {"role": role, "password": str(spec.get("password", ""))}

    def load_users(self):
        users = {}

        if self.config.users_file:
            path = Path(self.config.users_file)
            if path.exists():
                data = (path.read_text() or "{}").strip()
                if data:
                    raw = json.loads(data)
                    for username, spec in (raw.items() if isinstance(raw, dict) else []):
                        if str(username).startswith("_"):
                            continue  # allow "_comment" style keys
                        users[str(username)] = self._parse_file_entry(str(username), spec)
            else:
                from flask import current_app
                current_app.logger.warning(
                    "users file '%s' not found — no users can log in.", path
                )

        return users

    def authenticate(self, username, password):
        user = self.load_users().get(username)
        if user is None:
            return None
        if not _verify_password(user["password"], password):
            return None
        return {"username": username, "role": user["role"]}

    # ------------------------------------------------------------------
    # Login throttle (per client IP)
    # ------------------------------------------------------------------
    def _client_ip(self):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _prune(self, queue, now):
        while queue and now - queue[0] > self.config.login_window_seconds:
            queue.popleft()

    def allowed_to_try_login(self):
        now = time.time()
        queue = self._login_attempts[self._client_ip()]
        self._prune(queue, now)
        return len(queue) < self.config.login_max_attempts

    def record_login_failure(self):
        now = time.time()
        queue = self._login_attempts[self._client_ip()]
        self._prune(queue, now)
        queue.append(now)


# ----------------------------------------------------------------------
# Decorators
# ----------------------------------------------------------------------
def login_required(fn):
    """Any authenticated user (admin or viewer)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        username = session.get("username")
        if not username:
            return jsonify({"error": "authentication required"}), 401
        g.username = username
        g.role = session.get("role")
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    """Admins only; everyone else gets a 403."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        username = session.get("username")
        if not username:
            return jsonify({"error": "authentication required"}), 401
        if session.get("role") != ROLE_ADMIN:
            return jsonify({"error": "admin privileges required"}), 403
        g.username = username
        g.role = ROLE_ADMIN
        return fn(*args, **kwargs)

    return wrapper