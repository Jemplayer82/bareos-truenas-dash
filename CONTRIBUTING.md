# Contributing

Personal-infra project, but the standards still apply.

## Setup

```bash
uv sync
cp .env.example .env   # fill in the real Bareos console credential
uv run flask --app app run --debug
```

## Standards

- **Branches:** `feature/<slug>`, `fix/<slug>`; pipeline-authored work lands on `pipeline/<slug>`.
- **Commits:** Conventional-ish, imperative mood. Pipeline commits carry an `Authored-By-Model:` trailer.
- **Secrets never get committed.** Real values live only in the gitignored `.env`. The CI gitleaks
  gate and the local `secret-scan-guard.js` hook are backstops, not an excuse to be sloppy.
- **Tests:** `uv run pytest` must be green before any push to `master`.
- `/close-out` runs before the project is considered done.
