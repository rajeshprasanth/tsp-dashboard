#!/usr/bin/env python3
"""Local development server. Production runs use Docker / gunicorn
(see ``wsgi.py`` and the ``Dockerfile``)."""

from app import create_app

app = create_app()


if __name__ == "__main__":
    cfg = app.config["TSPD_CONFIG"]
    app.run(host=cfg.host, port=cfg.port, debug=cfg.debug)