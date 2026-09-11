"""Serves the static frontend at ``/`` and branded assets under ``/images``."""

from pathlib import Path

from flask import Blueprint, send_from_directory

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@bp.get("/images/<path:filename>")
def images(filename):
    """Serve branded assets (the SVG logo) from the top-level ``images/`` dir."""
    return send_from_directory(str(IMAGES_DIR), filename)