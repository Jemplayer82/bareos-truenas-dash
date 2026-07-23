"""Thin, stateless wrapper around ``bareos.bsock.DirectorConsoleJson``.

All configuration is read from ``os.environ`` AT CALL TIME (never import time).
``python-dotenv`` is deliberately not used. The defaults below mirror
``.env.example`` for bare local development; in production, gunicorn (the
Docker CMD) / the TrueNAS app injects the real values via the container
environment.
"""

from __future__ import annotations

import os
import re
from typing import Any

import bareos.exceptions
from bareos.bsock import DirectorConsoleJson


class BareosError(Exception):
    """Base class for errors originating from this module."""


class BareosUnavailable(BareosError):
    """Raised when the Bareos Director cannot be reached or returns a transport/JSON-RPC error."""


class BareosAuthFailed(BareosError):
    """Raised when authentication against the Bareos Director fails."""


def _config() -> tuple[str, int, str, str]:
    """Return fresh Bareos connection settings from the process environment."""
    host = os.environ.get("BAREOS_HOST", "192.168.1.41")
    port = int(os.environ.get("BAREOS_PORT", "9101"))
    name = os.environ.get("BAREOS_CONSOLE_NAME", "dashboard")
    password = os.environ.get("BAREOS_CONSOLE_PASSWORD", "changeme")
    return host, port, name, password


def _connect() -> DirectorConsoleJson:
    """Connect and authenticate to the Bareos Director.

    Authentication failures are mapped to :class:`BareosAuthFailed` first,
    because ``AuthenticationError`` subclasses ``ConnectionError`` which
    subclasses ``bareos.exceptions.Error``.
    """
    host, port, name, password = _config()
    try:
        return DirectorConsoleJson(
            address=host,
            port=port,
            name=name,
            password=password,
            tls_psk_enable=False,
            timeout=10,
        )
    except bareos.exceptions.AuthenticationError as e:
        raise BareosAuthFailed(str(e)) from e
    except (bareos.exceptions.Error, OSError) as e:
        raise BareosUnavailable(str(e)) from e


def _call(command: str) -> dict[str, Any]:
    """Execute a single Bareos console command and return the parsed JSON result."""
    conn = _connect()
    try:
        try:
            result = conn.call(command)
        except bareos.exceptions.AuthenticationError as e:
            raise BareosAuthFailed(str(e)) from e
        except (bareos.exceptions.Error, OSError) as e:
            raise BareosUnavailable(str(e)) from e
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not isinstance(result, dict):
        return {}
    return result


def get_status() -> dict[str, Any]:
    """Return a lightweight connectivity/version indicator.

    This function never returns ``connected=False``; failure is communicated
    by raising :class:`BareosUnavailable` or :class:`BareosAuthFailed`.
    """
    data = _call("version")
    v = data.get("version", "")
    version = str(v.get("version", "")) if isinstance(v, dict) else str(v)
    return {"connected": True, "version": version}


def list_defined_jobs() -> list[str]:
    """Return the sorted list of job names defined in the Director."""
    data = _call(".jobs")
    rows = data.get("jobs", [])
    names = [
        str(row["name"])
        for row in rows
        if isinstance(row, dict) and "name" in row
    ]
    return sorted(names)


def list_recent_runs(limit: int = 25) -> list[dict[str, Any]]:
    """Return recent job run rows, newest first by numeric jobid."""
    data = _call(f"list jobs last limit={int(limit)}")
    rows = data.get("jobs", [])

    def _jobid_key(row: Any) -> int:
        try:
            return int(row.get("jobid", 0))  # type: ignore[union-attr]
        except Exception:
            return 0

    return sorted(rows, key=_jobid_key, reverse=True)


def list_media() -> list[dict[str, Any]]:
    """Return a flat list of volume/media records.

    The Director may return media as a flat list under ``media`` or
    ``volumes``, or as a dict under ``volumes`` keyed by pool name. The latter
    is flattened and each volume is annotated with its pool unless it already
    has one.
    """
    data = _call("list media")
    raw: Any = data.get("media") or data.get("volumes") or []

    if isinstance(raw, dict):
        flat: list[dict[str, Any]] = []
        for pool, volumes in raw.items():
            for volume in volumes:
                if isinstance(volume, dict):
                    volume.setdefault("pool", pool)
                    flat.append(volume)
        return flat
    elif isinstance(raw, list):
        return raw
    return []


def run_job(name: str) -> int:
    """Start a Bareos job by name and return its assigned jobid.

    The HTTP layer also validates the name against :func:`list_defined_jobs`
    before calling this function; the regex below is a second, defense-in-depth
    layer that blocks console-command injection.
    """
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.\- ]+", name):
        raise ValueError("invalid job name")

    data = _call(f"run job={name} yes")
    jobid = data.get("run", {}).get("jobid")
    if jobid is None:
        raise BareosUnavailable(f"no jobid in run response: {data!r}")
    return int(jobid)
