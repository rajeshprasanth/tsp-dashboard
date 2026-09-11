"""Serves the static frontend at ``/``."""

from pathlib import Path

from flask import Blueprint, send_from_directory

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")