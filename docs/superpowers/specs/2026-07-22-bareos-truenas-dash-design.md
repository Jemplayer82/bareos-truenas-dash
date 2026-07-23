# bareos-truenas-dash — design

**Date:** 2026-07-22 · **Status:** approved (interactive brainstorm with Landon; final autonomy
delegated for build decisions)

## Problem

Bareos (tape backup) runs in its own VM (`Bare_OS`, 192.168.1.41) under TrueNAS SCALE 25.04 —
TrueNAS can't host the Director natively. Landon wants to run and monitor tape backups *from the
TrueNAS interface* instead of opening bareos-webui separately. A literal new TrueNAS nav tab isn't
achievable without hacking iX's closed Angular frontend (fragile, update-hostile — rejected), so
the chosen integration is a **TrueNAS SCALE Custom App**: a containerized dashboard that appears
in TrueNAS's own Apps section.

## Decisions (locked during brainstorm)

- **Integration point:** TrueNAS Apps entry (custom app), not a nav-tab hack, not just-a-URL.
- **Scope:** all of it — trigger jobs on demand, job status/history, tape/media status, director
  health. "Essentially run Bareos from inside TrueNAS."
- **Transport:** direct to the Director's console protocol on 9101 via `python-bareos`
  (confirmed reachable from the LAN; probe validated auth + JSON API against the live Director).
  Not scraping bareos-webui.
- **Credential:** dedicated named console `dashboard` on the Director, `Profile = operator`
  (stock profile: run/status/list allowed; delete/purge/prune/configure denied), `TlsEnable = false`
  following the existing console precedent on this Director (LAN-only). Password is generated,
  lives in the Director config + the app's `.env` / TrueNAS app env — never committed.
- **Stack:** Flask + python-bareos + gunicorn, uv/pyproject, mirroring the `stats` repo's proven
  patterns (env-driven config, `/api/*` JSON endpoints returning HTTP 200 with an `error` sentinel
  field, per-card async polling frontend). Branding via the Fathom Works design system (sonar-cyan,
  JetBrains Mono, `[ panel ]` titles) — NOT stats' generic purple CSS.
- **Build method:** dev-pipeline (Claude plans/verifies, Kimi K2 authors all code).
- **Auth posture:** LAN-trust, no app-level login — consistent with the rest of the homelab. The
  restricted console ACL is the blast-radius limiter: worst case is an unwanted backup run, never
  a delete/purge/restore.

## Architecture

```
TrueNAS Apps (custom app container)
  └─ Flask app (gunicorn :5000)
       ├─ GET  /              dashboard page
       ├─ GET  /healthz       liveness (no Bareos call)
       ├─ GET  /api/status    director version + connection state
       ├─ GET  /api/jobs      defined jobs + last run per job (status badge, when)
       ├─ GET  /api/history   recent runs (list jobs last, newest first)
       ├─ GET  /api/media     volumes: name, pool, status, bytes, last written, in-changer
       └─ POST /api/run       {job: <name>} → "run job=<name> yes" → returns queued jobid
            └─ bareos_client.py — thin wrapper over bareos.bsock.DirectorConsoleJson
                 (connect per request, tls_psk_enable=False, timeouts, error mapping)
```

- One page, no SPA framework — vanilla JS polling (`async load*()` + `setInterval`), matching
  `stats`. Jobs/status poll ~15s; media ~60s.
- `POST /api/run` validates the job name against the Director's own `.jobs` list before running —
  no arbitrary command strings from the browser reach the console.
- Frontend renders four panels: Jobs (Run button + last-run badge), Running/History, Media/Tapes,
  Director status. Failed jobs (e.g. status `f`) show red; the dashboard's job is to make a bad
  backup impossible to miss.

## Error handling

- Director unreachable → `/api/*` return `{error: "director_unreachable", details}` with HTTP 200;
  cards show the error state without breaking the page (stats convention).
- Console auth rejected → `{error: "auth_failed"}` — distinct from unreachable so the fix is obvious.
- `POST /api/run` with unknown job → `{error: "unknown_job"}`, 200, nothing sent to the Director.
- Per-request Director connections: no long-lived socket to go stale; connect failures are cheap
  and reported per poll cycle.

## Testing

- Unit tests mock the bareos client layer (no live Director in CI): API shape, error sentinels,
  run-validation logic, job-name validation.
- Live verification (manual/local): run against the real Director, confirm real jobs/media render,
  browser check. Live tape-job firing is deliberately NOT part of automated verification.

## Deployment

- CI (GitHub Actions): gitleaks gate → docker build → push `ghcr.io/jemplayer82/bareos-truenas-dash`
  `:latest` + `:sha`.
- TrueNAS: Apps → Custom App, image above, env vars from `.env.example`, port 5000. First deploy
  may be manual via UI; API-driven deploy (`app.create` with custom compose) attempted when
  credentials allow.
- Rollback: previous `:sha` tag.

## Accepted risks

- LAN-trust (no login) on an endpoint that can trigger real tape jobs — accepted; ACL-restricted
  console bounds the damage. Revisit with a bearer token if it ever leaves the LAN.
- `TlsEnable = false` on the console credential — console auth (MD5 challenge) + LAN-only.
  Matches existing consoles on this Director; revisit if Bareos hardening becomes a priority.
- The Director currently defines 3 jobs and only File-storage volumes are labeled; tape.conf
  storage exists but no tapes labeled yet. Dashboard shows whatever the catalog reports — no
  tape-specific assumptions baked in.
