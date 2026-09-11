# Deployment

## Configuration

All runtime settings come from environment variables (set via
`/etc/tsp-dashboard.env` when running as a service). For local dev a
`.env` file in the project root is loaded automatically; real
environment variables always take precedence.

| Variable                          | Default            | Purpose                                             |
|-----------------------------------|--------------------|-----------------------------------------------------|
| `TSPD_SECRET_KEY`                 | *(ephemeral)*      | Session-signing key. Set a stable secret in prod.   |
| `TSPD_USERS_FILE`                 | `users.json`       | Path to the user database (JSON) — the only source of users. |
| `TSPD_BIND_HOST`                  | `127.0.0.1`        | gunicorn bind address.                             |
| `TSPD_PORT`                       | `8766`             | gunicorn / dev-server port.                        |
| `TSPD_WORKERS` / `TSPD_THREADS`   | `2` / `4`          | gunicorn settings.                                 |
| `TSPD_LOG_LEVEL`                  | `info`             | gunicorn log level.                                 |
| `TSPD_COOKIE_SECURE`              | `false`            | Set `true` behind TLS for `Secure` cookies.         |
| `TSPD_LOGIN_MAX_ATTEMPTS`         | `10`               | Failed attempts permitted per window.               |
| `TSPD_LOGIN_WINDOW_SECONDS`       | `300`              | Login-throttle window.                              |
| `TSP_BIN`                         | *(auto-detect)*    | Override the `tsp` binary path.                     |
| `TS_SOCKET` / `TMPDIR`            | *(tsp defaults)*   | Inherited by the `tsp` client to reach the daemon.  |

## User database

Passwords are stored as salted PBKDF2 hashes. Manage them with
`manage.py`:

```bash
python3 manage.py add-user --username alice --role admin
python3 manage.py add-user --username bob   --role viewer
python3 manage.py list-users
python3 manage.py remove-user --username bob
```

`users.json` is gitignored; `users.example.json` documents the schema.

## Notes

* The dashboard service binds to `127.0.0.1:8766` by default. Put it behind
  a reverse proxy (nginx / Caddy / Traefik) with TLS and set
  `TSPD_COOKIE_SECURE=true`.
* Logs land in the journal: `journalctl -u tsp-dashboard -f`.
* The service runs hardened (`NoNewPrivileges`, `PrivateTmp`,
  `ProtectSystem=strict`, `ProtectHome=true`); only `/data` is writable.
* To control the **host's** task-spooler daemon instead of a per-user one,
  point `TS_SOCKET` at the existing socket (e.g. `TS_SOCKET=/tmp/ts.socket`)
  and make sure the service user can read/write that socket.
* Rotate/regenerate `TSPD_SECRET_KEY` if it is ever leaked — it signs all
  sessions.
* The login throttle keys on the `X-Forwarded-For` client IP; only trust it
  if your proxy sets it.