# 🎞️ bareos-truenas-dash

**Run your Bareos tape backups from inside TrueNAS.** A single-page dashboard that talks straight
to the Bareos Director and deploys as a TrueNAS SCALE custom app — jobs, history, and tape/media
status without opening bareos-webui.

## ✨ Features

- **Run backups on demand** — one button per configured job, straight to the Director
- **Job status & history** — recent runs, live running jobs, last-good-backup per job
- **Tape / media view** — volumes, pool, status (Append/Full/Error), last written
- **Director health** — director + storage daemon status at a glance

> [!NOTE]
> Bareos itself runs in its own VM (TrueNAS can't host the Director natively). This dashboard is
> the TrueNAS-side control surface, deployed via **Apps → Custom App** so it lives in the TrueNAS
> UI. It talks to the Director's console port (9101) using a dedicated, ACL-restricted console
> credential — it can run and inspect, it cannot delete, purge, or prune.

## 🚀 Quick Start

```bash
uv sync
cp .env.example .env   # fill in the Bareos console credential
uv run flask --app app run --debug
```

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
