# 🎞️ bareos-truenas-dash

**Run your Bareos tape backups from inside TrueNAS.** A single-page dashboard that talks straight
to the Bareos Director and deploys as a TrueNAS SCALE custom app — jobs, history, and tape/media
status without opening bareos-webui.

## ✨ Features

- **Run backups on demand** — one button per configured job, straight to the Director
- **Job status & history** — recent runs, live running jobs, last-good-backup per job
- **Tape / media view** — volumes, pool, status (Append/Full/Error), last written
- **Director health** — Director version and console connection state at a glance

> [!NOTE]
> Bareos itself runs in its own VM (TrueNAS can't host the Director natively). This dashboard is
> the TrueNAS-side control surface, deployed via **Apps → Custom App** so it lives in the TrueNAS
> UI. It talks to the Director's console port (9101) using a dedicated, ACL-restricted console
> credential — it can run and inspect, it cannot delete, purge, or prune.

## 🚀 Quick Start

```bash
uv sync
cp .env.example .env   # fill in the Bareos console credential
uv run --env-file .env flask --app app run --debug
```

`python-dotenv` is not used — the app reads `os.environ` directly (defaults match `.env.example`; gunicorn/TrueNAS inject real values in production).

## 🔌 API

- `GET /healthz` — liveness, never touches the Director
- `GET /api/status`
- `GET /api/jobs` — defined jobs + newest run each
- `GET /api/history?limit=25`
- `GET /api/media`
- `POST /api/run` with body `{"job": "<name>"}` — validated against the Director's own job list before anything is sent

All `/api/*` endpoints always return HTTP 200, with an `error` sentinel field on failure (`director_unreachable`, `auth_failed`, `unknown_job`) plus a `details` string, so the dashboard polls straight through outages.

## ⚙️ Configuration

All via environment (see [`.env.example`](.env.example)):

| Variable | Meaning |
|---|---|
| `BAREOS_HOST` / `BAREOS_PORT` | Director address (console port, default 9101) |
| `BAREOS_CONSOLE_NAME` / `BAREOS_CONSOLE_PASSWORD` | The dedicated restricted console |
| `DASH_PORT` | Dashboard listen port |

## 📦 Deploy

CI builds `ghcr.io/jemplayer82/bareos-truenas-dash` (`:latest` + `:sha`) on every push to
`master`, gated by a gitleaks secret scan. On TrueNAS: **Apps → Discover Apps → Custom App**,
point it at the image, pass the env vars above.

> [!IMPORTANT]
> Never `build: .` in compose — the image is always pulled pre-built from ghcr.

## 📄 License

Apache 2.0 — see [`LICENSE`](LICENSE).
