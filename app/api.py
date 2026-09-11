"""REST API for the dashboard. All routes live under ``/api``.

Role model
----------
* ``viewer`` — read-only: job lists, job info/output, server state.
* ``admin``  — everything, plus mutating operations (slots, bump, swap,
  kill, clear, server shutdown).

Authentication is cookie-session based; see :mod:`app.auth`.
"""

from flask import Blueprint, current_app, g, jsonify, request, session

from .auth import admin_required, login_required
from .tsp import TSPDead, TSPError, TaskSpooler

bp = Blueprint("api", __name__)


def _store():
    return current_app.extensions["users"]


def _tsp():
    return TaskSpooler()


def _empty_counts():
    return {"queued": 0, "running": 0, "finished": 0, "failed": 0, "other": 0}


# ----------------------------------------------------------------------
# Session / identity
# ----------------------------------------------------------------------
@bp.get("/me")
def api_me():
    username = session.get("username")
    if not username:
        return jsonify({"error": "authentication required"}), 401
    return jsonify({"user": username, "role": session.get("role")})


@bp.post("/login")
def api_login():
    store = _store()
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    if not store.allowed_to_try_login():
        return jsonify(
            {"error": "too many failed login attempts; please try again later."}
        ), 429

    user = store.authenticate(username, password)
    if user is None:
        store.record_login_failure()
        return jsonify({"error": "invalid username or password"}), 401

    session.clear()
    session["username"] = user["username"]
    session["role"] = user["role"]
    return jsonify({"user": user["username"], "role": user["role"]})


@bp.post("/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# Read-only endpoints (viewer + admin)
# ----------------------------------------------------------------------
@bp.get("/jobs")
@login_required
def api_jobs():
    tsp = _tsp()
    counts = _empty_counts()

    try:
        jobs = tsp.list_jobs()
        alive = True
    except TSPDead:
        jobs, alive = [], False
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 500

    for job in jobs:
        state = job["state"]
        if state == "finished":
            if job["exit_code"] not in ("", "0"):
                counts["failed"] += 1
            else:
                counts["finished"] += 1
        elif state in counts:
            counts[state] += 1
        else:
            counts["other"] += 1

    payload = {
        "jobs": jobs,
        "counts": counts,
        "server_alive": alive,
        "binary": tsp.binary,
        "slots": tsp.get_slots() if alive else None,
        "version": tsp.version(),
        "role": g.role,
    }
    if not alive:
        payload["error"] = "task-spooler server is not running"
        return jsonify(payload), 503
    return jsonify(payload)


@bp.get("/info")
@login_required
def api_info():
    tsp = _tsp()
    alive = tsp.is_alive()
    return jsonify({
        "binary": tsp.binary,
        "server_alive": alive,
        "slots": tsp.get_slots() if alive else None,
        "version": tsp.version(),
        "role": g.role,
    })


@bp.get("/server/status")
@login_required
def api_server_status():
    return jsonify({"server_alive": _tsp().is_alive()})


@bp.get("/jobs/<job_id>/output")
@login_required
def api_job_output(job_id):
    if not job_id.isdigit():
        return jsonify({"error": "invalid job id"}), 400
    try:
        out = _tsp().job_output(job_id)
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 404

    MAX_CHARS = 200_000
    truncated = len(out) > MAX_CHARS
    if truncated:
        out = out[-MAX_CHARS:]
    return jsonify({"output": out, "truncated": truncated})


@bp.get("/jobs/<job_id>/info")
@login_required
def api_job_info(job_id):
    if not job_id.isdigit():
        return jsonify({"error": "invalid job id"}), 400
    try:
        return jsonify(_tsp().job_info(job_id))
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 404


# ----------------------------------------------------------------------
# Admin-only mutation endpoints
# ----------------------------------------------------------------------
@bp.post("/jobs/<job_id>/cancel")
@admin_required
def api_job_cancel(job_id):
    if not job_id.isdigit():
        return jsonify({"error": "invalid job id"}), 400
    body = request.get_json(silent=True) or {}
    action = body.get("action", "remove")
    if action not in ("kill", "remove"):
        action = "remove"
    try:
        _tsp().cancel(job_id, action)
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@bp.post("/jobs/<job_id>/bump")
@admin_required
def api_job_bump(job_id):
    if not job_id.isdigit():
        return jsonify({"error": "invalid job id"}), 400
    try:
        _tsp().bump(job_id)
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@bp.post("/jobs/swap")
@admin_required
def api_jobs_swap():
    body = request.get_json(silent=True) or {}
    a, b = str(body.get("a", "")), str(body.get("b", ""))
    if not (a.isdigit() and b.isdigit()):
        return jsonify({"error": "invalid job ids"}), 400
    try:
        _tsp().swap(a, b)
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@bp.post("/slots")
@admin_required
def api_set_slots():
    body = request.get_json(silent=True) or {}
    num = body.get("slots")
    is_num_int = isinstance(num, int) and not isinstance(num, bool)
    is_num_str = isinstance(num, str) and num.isdigit()
    if not (is_num_int or is_num_str):
        return jsonify({"error": "slots must be a positive integer"}), 400
    value = int(num)
    if value < 1:
        return jsonify({"error": "slots must be a positive integer"}), 400

    tsp = _tsp()
    try:
        tsp.set_slots(value)
        current = tsp.get_slots()
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"slots": current})


@bp.post("/kill-all")
@admin_required
def api_kill_all():
    try:
        _tsp().kill_all()
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@bp.post("/clear")
@admin_required
def api_clear():
    try:
        _tsp().clear()
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@bp.post("/server/kill")
@admin_required
def api_server_kill():
    """Kill the task-spooler server (`tsp -K`). Irreversible."""
    try:
        _tsp().shutdown()
    except TSPError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "server_alive": False})