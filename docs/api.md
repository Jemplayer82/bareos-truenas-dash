# API reference

The dashboard page is a thin layer over these endpoints.

- `GET /healthz` — liveness, never touches the Director
- `GET /api/status`
- `GET /api/jobs` — defined jobs + newest run each
- `GET /api/history?limit=25`
- `GET /api/media`
- `POST /api/run` with body `{"job": "<name>"}` — validated against the Director's own job list before anything is sent

All `/api/*` endpoints always return HTTP 200, with an `error` sentinel field on failure (`director_unreachable`, `auth_failed`, `unknown_job`) plus a `details` string, so the dashboard polls straight through outages.
