from __future__ import annotations

import functools
import os
from typing import Any, Callable

import bareos_client
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)


def badge_for(code: str | None) -> dict[str, str]:
    """Map a Bareos jobstatus code to a UI badge {label, klass}."""
    mapping: dict[str, tuple[str, str]] = {
        "T": ("ok", "ok"),          # terminated normally -> green
        "W": ("warnings", "warn"),  # terminated with warnings -> amber
        "f": ("failed", "fail"),    # fatal error -> red
        "F": ("failed", "fail"),
        "E": ("failed", "fail"),    # terminated with errors -> red
        "A": ("aborted", "fail"),   # canceled/aborted -> red
        "R": ("running", "running"),# running -> amber pulse
    }
    label, klass = mapping.get(code or "", (code or "?", "unknown"))
    return {"label": label, "klass": klass}


def api_guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Catch expected Bareos client errors and turn them into 200 sentinel JSON."""
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> Any:
        try:
            return fn(*args, **kwargs)
        except bareos_client.BareosAuthFailed as e:
            return jsonify({"error": "auth_failed", "details": str(e)})
        except bareos_client.BareosError as e:
            return jsonify({"error": "director_unreachable", "details": str(e)})
    return wrapper


def _to_int(value: object) -> int:
    """Coerce a Bareos numeric string (possibly with commas) to int."""
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return 0


def _flag(value: object) -> bool:
    """Coerce Bareos-ish boolean flags to Python bool."""
    return str(value).strip().lower() in {"1", "yes", "true"}


@app.route("/")
def index() -> Any:
    return render_template("index.html")


@app.route("/healthz")
def healthz() -> tuple[str, int, dict[str, str]]:
    """Lightweight liveness probe; must never touch the Bareos client."""
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/api/status")
@api_guard
def status() -> Any:
    return jsonify(bareos_client.get_status())


@app.route("/api/jobs")
@api_guard
def jobs() -> Any:
    defined = bareos_client.list_defined_jobs()
    runs = bareos_client.list_recent_runs(100)
    result: list[dict[str, Any]] = []

    for name in defined:
        last_run: dict[str, Any] | None = None
        for row in runs:
            if row.get("name") == name:
                last_run = {**row, "badge": badge_for(row.get("jobstatus"))}
                break
        result.append({"name": name, "last_run": last_run})

    return jsonify({"jobs": result})


@app.route("/api/history")
@api_guard
def history() -> Any:
    raw_limit = request.args.get("limit", "25")
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 25

    if limit < 1:
        limit = 1
    elif limit > 500:
        limit = 500

    rows = bareos_client.list_recent_runs(limit)
    return jsonify(
        {"runs": [{**row, "badge": badge_for(row.get("jobstatus"))} for row in rows]}
    )


@app.route("/api/media")
@api_guard
def media() -> Any:
    rows = bareos_client.list_media()
    normalized: list[dict[str, Any]] = []

    for row in rows:
        normalized.append(
            {
                "volume": row.get("volumename") or row.get("volume") or "",
                "pool": row.get("pool", ""),
                "status": row.get("volstatus", ""),
                "bytes": _to_int(row.get("volbytes")),
                "lastwritten": row.get("lastwritten") or "",
                "inchanger": _flag(row.get("inchanger")),
            }
        )

    return jsonify({"media": normalized})


@app.route("/api/run", methods=["POST"])
@api_guard
def run() -> Any:
    body = request.get_json(silent=True)
    name = body.get("job") if isinstance(body, dict) else None

    if not isinstance(name, str) or not name.strip():
        return jsonify(
            {
                "error": "unknown_job",
                "details": "missing or invalid 'job' in request body",
            }
        )

    name = name.strip()
    defined = bareos_client.list_defined_jobs()

    if name not in defined:
        return jsonify(
            {
                "error": "unknown_job",
                "details": f"job '{name}' is not defined on the director",
            }
        )

    try:
        jobid = bareos_client.run_job(name)
    except ValueError as e:
        return jsonify({"error": "unknown_job", "details": str(e)})

    return jsonify({"jobid": jobid, "job": name})


if __name__ == "__main__":
    # Production runs under gunicorn (Dockerfile CMD) with env injected by the container.
    app.run(host="0.0.0.0", port=int(os.environ.get("DASH_PORT", "5000")))
