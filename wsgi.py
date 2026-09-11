"""gunicorn entrypoint: ``gunicorn wsgi:app`` (see Dockerfile)."""

from app import create_app

app = create_app()