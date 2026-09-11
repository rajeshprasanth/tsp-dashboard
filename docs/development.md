# Development

## Setup

```bash
pip install -r requirements-dev.txt
pytest -q              # runs the full API suite against a fake tsp
python3 run.py
```

Tests use `tests/fake_tsp.py`, a small in-memory emulator of the `tsp`
CLI (selected via `TSP_BIN`), so nothing real is touched.

## API flow

* **`app/__init__.py`** — Flask app factory, security headers, blueprint
  registration.
* **`app/config.py`** — environment-driven configuration.
* **`app/auth.py`** — user store (`manage.py` writes PBKDF2 hashes), role
  decorators (`@login_required`, `@admin_required`).
* **`app/tsp.py`** — `TaskSpooler` client wrapper over the `tsp` CLI with
  output parsing (`--serialize json` with `-l` fallback).
* **`app/api.py`** — REST API blueprint, role-aware (see [API reference](api.md)).
* **`app/web.py`** — serves the frontend (`/`) and branded assets (`/images/…`).

## Frontend

The whole UI lives in `static/index.html` (inline HTML + CSS + vanilla JS):

* `fetchJobs()` polls `GET /api/jobs` and renders the table.
* Theme (dark/light) is stored under the `tsp-theme` key in `localStorage`,
  applied to `<html data-theme>` on every toggle, and switches the logo
  between `logo-dark.svg` and `logo-light.svg`.
* The poll interval is stored under `tsp-poll` in `localStorage`.

## Layout

```
images/
  logo-dark.svg         # official application logo (dark theme)
  logo-light.svg        # official application logo (light theme)
app/
  __init__.py   # Flask app factory, security headers
  config.py     # env-driven configuration
  auth.py       # user store, password hashing, role decorators
  tsp.py        # TaskSpooler client (parsing + tsp commands)
  api.py        # REST API blueprint (role-aware)
  web.py        # serves the frontend and branded assets
docs/           # this MkDocs site
static/index.html
systemd/
  tsp-dashboard.service   # main dashboard unit
  task-spooler.service    # optional persistent tsp daemon
scripts/install_service.sh  # one-shot systemd installer
gunicorn.conf.py          # production server config (env-driven)
manage.py       # user management CLI
run.py          # dev server
wsgi.py         # gunicorn entrypoint
tests/          # pytest suite + fake tsp
```

## Documentation

This site is built with [MkDocs](https://www.mkdocs.org/) and the
[Material theme](https://squidfunk.github.io/mkdocs-material/):

```bash
pip install -r requirements-dev.txt
mkdocs build               # outputs to site/
mkdocs serve               # live preview at http://127.0.0.1:8000
mkdocs gh-deploy           # publish to GitHub Pages
```