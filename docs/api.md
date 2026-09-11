# API reference

All endpoints (except `POST /api/login`) require an authenticated session.
Authentication is cookie-session based; see [Development](development.md).

| Method | Path                              | Roles     | Description                              |
|--------|-----------------------------------|-----------|------------------------------------------|
| GET    | `/api/me`                         | any       | Current session: `{user, role}`          |
| POST   | `/api/login`                      | public    | Start a session                          |
| POST   | `/api/logout`                     | any       | End the session                          |
| GET    | `/api/jobs`                       | any       | Jobs, counts, slots, server alive state  |
| GET    | `/api/info`                       | any       | tsp binary, slots, version, alive flag   |
| GET    | `/api/server/status`              | any       | `{server_alive}` (healthcheck)           |
| GET    | `/api/jobs/<id>/info`             | any       | `tsp -i <id>` detail                     |
| GET    | `/api/jobs/<id>/output`           | any       | `tsp -c <id>` output (tail, capped)      |
| POST   | `/api/jobs/<id>/cancel`           | admin     | `{action: kill\|remove}` (`-k`/`-r`)     |
| POST   | `/api/jobs/<id>/bump`             | admin     | `tsp -u <id>` — front of queue           |
| POST   | `/api/jobs/swap`                  | admin     | `{a, b}` — `tsp -U a-b`                  |
| POST   | `/api/slots`                      | admin     | `{slots}` — `tsp -S <n>`                 |
| POST   | `/api/kill-all`                   | admin     | `tsp -T`                                 |
| POST   | `/api/clear`                      | admin     | `tsp -C`                                 |
| POST   | `/api/server/kill`                | admin     | `tsp -K` — stop the daemon               |

## Static / assets

| Method | Path                          | Description                          |
|--------|-------------------------------|--------------------------------------|
| GET    | `/`                           | Serves the single-page frontend      |
| GET    | `/images/<path:filename>`     | Branded assets (SVG logos)           |
| GET    | `/static/<path:filename>`     | Static frontend assets (Flask)       |

## Headers

Every response is annotated with `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.