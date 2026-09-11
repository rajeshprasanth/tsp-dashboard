"""Integration tests for the dashboard API.

A fake ``tsp`` binary (tests/fake_tsp.py) replaces the real task
spooler so the whole stack — auth, role enforcement, mutating
endpoints — can be exercised without a daemon.
"""

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app

FAKE_TSP = Path(__file__).parent / "fake_tsp.py"

SEEDED_JOBS = [
    {"id": "0", "state": "running", "command": "sleep 30", "output": "/tmp/out0",
     "output_text": "running...", "time_ms": 500},
    {"id": "1", "state": "queued", "command": "echo hi", "output": "/tmp/out1",
     "output_text": "", "time_ms": 0},
    {"id": "2", "state": "finished", "command": "true", "output": "/tmp/out2",
     "output_text": "done", "exit_code": "0", "times": "0.01s", "time_ms": 10},
]


def _write_state(path, state):
    path.write_text(json.dumps(state))


@pytest.fixture
def client(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    _write_state(users, {
        "admin": {"role": "admin", "password": generate_password_hash("adminpw")},
        "viewer": {"role": "viewer", "password": generate_password_hash("viewpw")},
    })
    state = tmp_path / "state.json"
    _write_state(state, {
        "jobs": [dict(j) for j in SEEDED_JOBS],
        "slots": 2,
        "alive": True,
        "next_id": 3,
    })

    monkeypatch.setenv("TSP_BIN", str(FAKE_TSP))
    monkeypatch.setenv("FAKE_TSP_STATE", str(state))
    monkeypatch.setenv("TSPD_USERS_FILE", str(users))
    monkeypatch.setenv("TSPD_SECRET_KEY", "test-secret")

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        c.state_file = state
        yield c
    monkeypatch.delenv("TSP_BIN", raising=False)


def _login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


def _read_state(client):
    return json.loads(client.state_file.read_text())


# ----------------------------------------------------------------------
# auth
# ----------------------------------------------------------------------
def test_login_admin_and_viewer(client):
    assert _login(client, "admin", "adminpw").status_code == 200
    client.get("/api/logout")
    assert _login(client, "viewer", "viewpw").status_code == 200


def test_login_wrong_password(client):
    res = _login(client, "admin", "nope")
    assert res.status_code == 401


def test_login_unknown_user(client):
    assert _login(client, "ghost", "x").status_code == 401


def test_logout_clears_session(client):
    _login(client, "admin", "adminpw")
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_login_throttle(client):
    for _ in range(10):
        _login(client, "admin", "wrong")
    res = _login(client, "admin", "wrong")
    assert res.status_code == 429


# ----------------------------------------------------------------------
# read-only endpoints (both roles)
# ----------------------------------------------------------------------
def test_unauthenticated_is_rejected(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs/0/output").status_code == 401
    assert client.post("/api/slots", json={"slots": 4}).status_code == 401


def test_viewer_can_list_jobs(client):
    _login(client, "viewer", "viewpw")
    res = client.get("/api/jobs")
    assert res.status_code == 200
    data = res.get_json()
    assert data["server_alive"] is True
    assert [j["id"] for j in data["jobs"]] == ["0", "1", "2"]
    assert data["counts"]["running"] == 1
    assert data["counts"]["queued"] == 1
    assert data["counts"]["finished"] == 1
    assert data["counts"]["failed"] == 0
    assert data["role"] == "viewer"


def test_viewer_can_read_info_and_output(client):
    _login(client, "viewer", "viewpw")
    assert client.get("/api/jobs/0/info").status_code == 200
    res = client.get("/api/jobs/0/output")
    assert res.status_code == 200
    assert res.get_json()["output"] == "running..."


def test_viewer_cannot_mutate(client):
    _login(client, "viewer", "viewpw")
    assert client.post("/api/slots", json={"slots": 4}).status_code == 403
    assert client.post("/api/jobs/1/bump").status_code == 403
    assert client.post("/api/jobs/0/cancel", json={"action": "kill"}).status_code == 403
    assert client.post("/api/jobs/swap", json={"a": "1", "b": "0"}).status_code == 403
    assert client.post("/api/kill-all").status_code == 403
    assert client.post("/api/clear").status_code == 403
    assert client.post("/api/server/kill").status_code == 403


def test_viewer_does_not_see_server_controls_payload(client):
    # Role is echoed back so the UI can hide admin controls.
    _login(client, "viewer", "viewpw")
    assert client.get("/api/jobs").get_json()["role"] == "viewer"
    _login(client, "admin", "adminpw")
    assert client.get("/api/jobs").get_json()["role"] == "admin"


# ----------------------------------------------------------------------
# admin mutations
# ----------------------------------------------------------------------
def test_admin_can_set_slots(client):
    _login(client, "admin", "adminpw")
    res = client.post("/api/slots", json={"slots": 4})
    assert res.status_code == 200
    assert res.get_json()["slots"] == "4"
    assert _read_state(client)["slots"] == 4


def test_admin_slots_validates(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/slots", json={"slots": 0}).status_code == 400
    assert client.post("/api/slots", json={"slots": "abc"}).status_code == 400
    assert client.post("/api/slots", json={"slots": True}).status_code == 400


def test_admin_kill_server_then_jobs_503(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/server/kill").status_code == 200
    res = client.get("/api/jobs")
    assert res.status_code == 503
    assert res.get_json()["server_alive"] is False


def test_admin_can_bump_queued_job_to_front(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/jobs/1/bump").status_code == 200
    # Bumped job should now be first in the ordering.
    assert [j["id"] for j in _read_state(client)["jobs"]] == ["1", "0", "2"]


def test_admin_swap_two_jobs(client):
    _login(client, "admin", "adminpw")
    res = client.post("/api/jobs/swap", json={"a": "1", "b": "0"})
    assert res.status_code == 200
    assert [j["id"] for j in _read_state(client)["jobs"]] == ["1", "0", "2"]


def test_admin_kill_running_job(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/jobs/0/cancel", json={"action": "kill"}).status_code == 200
    job = next(j for j in _read_state(client)["jobs"] if j["id"] == "0")
    assert job["state"] == "finished"
    assert job["exit_code"] == 143


def test_admin_kill_all_running(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/kill-all").status_code == 200
    assert all(j["state"] != "running" for j in _read_state(client)["jobs"])


def test_admin_clear_finished(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/clear").status_code == 200
    remaining = [j["id"] for j in _read_state(client)["jobs"]]
    assert "2" not in remaining
    assert "0" in remaining and "1" in remaining


def test_admin_remove_queued_job(client):
    _login(client, "admin", "adminpw")
    assert client.post("/api/jobs/1/cancel", json={"action": "remove"}).status_code == 200
    assert [j["id"] for j in _read_state(client)["jobs"]] == ["0", "2"]


def test_job_output_truncates(client, tmp_path):
    _login(client, "admin", "adminpw")
    state = _read_state(client)
    state["jobs"][0]["output_text"] = "x" * 500_000
    _write_state(client.state_file, state)

    res = client.get("/api/jobs/0/output")
    assert res.status_code == 200
    body = res.get_json()
    assert body["truncated"] is True
    assert len(body["output"]) == 200_000


# ----------------------------------------------------------------------
# static / misc
# ----------------------------------------------------------------------
def test_login_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"tsp-dashboard" in res.data


def test_logo_asset_served(client):
    res = client.get("/images/logo-dark.svg")
    assert res.status_code == 200
    assert "image/svg+xml" in res.content_type
    assert b"<svg" in res.data


def test_security_headers(client):
    res = client.get("/api/me")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"