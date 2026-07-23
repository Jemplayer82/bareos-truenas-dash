from __future__ import annotations

import app as app_module
import bareos_client
import pytest


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def tripwire(*a, **k):
    raise AssertionError("client touched")


def test_healthz_never_touches_client(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "get_status", tripwire)
    monkeypatch.setattr(bareos_client, "list_defined_jobs", tripwire)
    monkeypatch.setattr(bareos_client, "list_recent_runs", tripwire)
    monkeypatch.setattr(bareos_client, "list_media", tripwire)
    monkeypatch.setattr(bareos_client, "run_job", tripwire)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.data == b"ok"
    assert resp.content_type.startswith("text/plain")


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


def test_status_happy(client, monkeypatch):
    monkeypatch.setattr(
        bareos_client, "get_status", lambda: {"connected": True, "version": "23.0.4"}
    )
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"connected": True, "version": "23.0.4"}
    assert "error" not in data


def test_status_unreachable(client, monkeypatch):
    def boom():
        raise bareos_client.BareosUnavailable("conn refused")

    monkeypatch.setattr(bareos_client, "get_status", boom)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "error": "director_unreachable",
        "details": "conn refused",
    }


def test_status_auth_failed(client, monkeypatch):
    def boom():
        raise bareos_client.BareosAuthFailed("bad md5")

    monkeypatch.setattr(bareos_client, "get_status", boom)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"error": "auth_failed", "details": "bad md5"}


@pytest.mark.parametrize(
    "code,label,klass",
    [
        ("T", "ok", "ok"),
        ("W", "warnings", "warn"),
        ("f", "failed", "fail"),
        ("F", "failed", "fail"),
        ("E", "failed", "fail"),
        ("A", "aborted", "fail"),
        ("R", "running", "running"),
        ("Z", "Z", "unknown"),
        (None, "?", "unknown"),
    ],
)
def test_badge_for_table(code, label, klass):
    assert app_module.badge_for(code) == {"label": label, "klass": klass}


def test_jobs_merge(client, monkeypatch):
    monkeypatch.setattr(
        bareos_client, "list_defined_jobs", lambda: ["Catalog", "Nightly", "NeverRan"]
    )

    seen_limits = []

    def fake_recent_runs(limit=25):
        seen_limits.append(limit)
        return [
            {
                "jobid": "9",
                "name": "Nightly",
                "jobstatus": "T",
                "starttime": "2026-07-22 01:00:00",
            },
            {
                "jobid": "8",
                "name": "Nightly",
                "jobstatus": "f",
                "starttime": "2026-07-21 01:00:00",
            },
            {"jobid": "7", "name": "Ghost", "jobstatus": "T", "starttime": "x"},
        ]

    monkeypatch.setattr(bareos_client, "list_recent_runs", fake_recent_runs)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    jobs = data["jobs"]
    assert len(jobs) == 3

    assert jobs[0]["name"] == "Catalog"
    assert jobs[0]["last_run"] is None

    assert jobs[1]["name"] == "Nightly"
    assert jobs[1]["last_run"]["jobid"] == "9"
    assert jobs[1]["last_run"]["badge"] == {"label": "ok", "klass": "ok"}

    assert jobs[2]["name"] == "NeverRan"
    assert jobs[2]["last_run"] is None

    names = [j["name"] for j in jobs]
    assert "Ghost" not in names

    assert seen_limits == [100]


def test_jobs_unreachable(client, monkeypatch):
    def boom():
        raise bareos_client.BareosUnavailable("down")

    monkeypatch.setattr(bareos_client, "list_defined_jobs", boom)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.get_json() == {"error": "director_unreachable", "details": "down"}


def test_history_limits(client, monkeypatch):
    seen_limits = []

    def fake_recent_runs(limit=25):
        seen_limits.append(limit)
        return [{"jobid": "5", "name": "N", "jobstatus": "R", "jobbytes": "123"}]

    monkeypatch.setattr(bareos_client, "list_recent_runs", fake_recent_runs)

    resp = client.get("/api/history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["runs"][0]["badge"] == {"label": "running", "klass": "running"}
    assert data["runs"][0]["jobbytes"] == "123"

    client.get("/api/history?limit=5")
    client.get("/api/history?limit=abc")
    client.get("/api/history?limit=9999")
    client.get("/api/history?limit=0")

    assert seen_limits == [25, 5, 25, 500, 1]


def test_history_auth_failed(client, monkeypatch):
    def boom(limit=25):
        raise bareos_client.BareosAuthFailed("rejected")

    monkeypatch.setattr(bareos_client, "list_recent_runs", boom)
    resp = client.get("/api/history")
    assert resp.status_code == 200
    assert resp.get_json()["error"] == "auth_failed"


def test_media_normalization(client, monkeypatch):
    monkeypatch.setattr(
        bareos_client,
        "list_media",
        lambda: [
            {
                "volumename": "Vol1",
                "pool": "Full",
                "volstatus": "Append",
                "volbytes": "123,456,789",
                "lastwritten": "2026-07-21 22:00:00",
                "inchanger": "1",
            },
            {
                "volumename": "Vol2",
                "pool": "Full",
                "volstatus": "Full",
                "volbytes": None,
                "lastwritten": None,
                "inchanger": "0",
            },
        ],
    )

    resp = client.get("/api/media")
    assert resp.status_code == 200
    media = resp.get_json()["media"]

    assert media[0] == {
        "volume": "Vol1",
        "pool": "Full",
        "status": "Append",
        "bytes": 123456789,
        "lastwritten": "2026-07-21 22:00:00",
        "inchanger": True,
    }

    assert media[1] == {
        "volume": "Vol2",
        "pool": "Full",
        "status": "Full",
        "bytes": 0,
        "lastwritten": "",
        "inchanger": False,
    }


def test_media_unreachable(client, monkeypatch):
    def boom():
        raise bareos_client.BareosUnavailable("boom")

    monkeypatch.setattr(bareos_client, "list_media", boom)
    resp = client.get("/api/media")
    assert resp.status_code == 200
    assert resp.get_json()["error"] == "director_unreachable"


def test_run_happy(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "list_defined_jobs", lambda: ["Catalog", "Nightly"])
    called = []

    def fake_run(name):
        called.append(name)
        return 42

    monkeypatch.setattr(bareos_client, "run_job", fake_run)

    resp = client.post("/api/run", json={"job": "Nightly"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"jobid": 42, "job": "Nightly"}
    assert "error" not in data
    assert called == ["Nightly"]


def test_run_unknown_job(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "list_defined_jobs", lambda: ["Nightly"])
    monkeypatch.setattr(bareos_client, "run_job", tripwire)

    resp = client.post("/api/run", json={"job": "Evil; delete volume"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["error"] == "unknown_job"


def test_run_missing_or_invalid_body(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "list_defined_jobs", tripwire)
    monkeypatch.setattr(bareos_client, "run_job", tripwire)

    resp = client.post("/api/run", data="x", content_type="text/plain")
    assert resp.status_code == 200
    assert resp.get_json()["error"] == "unknown_job"

    resp = client.post("/api/run", json={"job": ""})
    assert resp.status_code == 200
    assert resp.get_json()["error"] == "unknown_job"

    resp = client.post("/api/run", json={"job": 5})
    assert resp.status_code == 200
    assert resp.get_json()["error"] == "unknown_job"


def test_run_director_down_during_validation(client, monkeypatch):
    def boom():
        raise bareos_client.BareosUnavailable("down")

    monkeypatch.setattr(bareos_client, "list_defined_jobs", boom)
    monkeypatch.setattr(bareos_client, "run_job", tripwire)

    resp = client.post("/api/run", json={"job": "Nightly"})
    assert resp.status_code == 200
    assert resp.get_json() == {"error": "director_unreachable", "details": "down"}


def test_run_auth_failed_on_run(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "list_defined_jobs", lambda: ["Nightly"])

    def boom(name):
        raise bareos_client.BareosAuthFailed("denied")

    monkeypatch.setattr(bareos_client, "run_job", boom)

    resp = client.post("/api/run", json={"job": "Nightly"})
    assert resp.status_code == 200
    assert resp.get_json() == {"error": "auth_failed", "details": "denied"}


def test_run_valueerror_maps_to_unknown_job(client, monkeypatch):
    monkeypatch.setattr(bareos_client, "list_defined_jobs", lambda: ["Nightly"])

    def boom(name):
        raise ValueError("invalid job name")

    monkeypatch.setattr(bareos_client, "run_job", boom)

    resp = client.post("/api/run", json={"job": "Nightly"})
    assert resp.status_code == 200
    assert resp.get_json() == {"error": "unknown_job", "details": "invalid job name"}


from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def test_index_panels_and_ids(client):
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    for title in ("[ jobs ]", "[ history ]", "[ media ]", "[ director ]"):
        assert title in body
    for pid in (
        "jobs-body",
        "history-body",
        "media-body",
        "director-body",
        "jobs-stamp",
        "history-stamp",
        "media-stamp",
        "director-stamp",
        "jobs-error",
        "history-error",
        "media-error",
        "director-error",
        "director-dot",
        "director-version",
    ):
        assert pid in body
    assert "/static/app.js" in body
    assert "/static/style.css" in body


def test_index_external_refs_google_fonts_only():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    urls = re.findall(r'https?://[^\s"\'<>]+', html)
    assert urls
    for url in urls:
        assert url.startswith("https://fonts.googleapis.com") or url.startswith("https://fonts.gstatic.com")


def test_style_css_palette_and_self_contained():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    for token in (
        "#030d14",
        "#0a1a24",
        "#16303f",
        "#6cd5e6",
        "#00b4d8",
        "#10b981",
        "#f59e0b",
        "#ef4444",
        "JetBrains Mono",
    ):
        assert token in css
    assert "http" not in css.lower()
    for sel in (".badge.ok", ".badge.warn", ".badge.fail", ".badge.running", ".dot", ".panel"):
        assert sel in css


def test_appjs_structure():
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for fn in (
        "async function loadStatus",
        "async function loadJobs",
        "async function loadHistory",
        "async function loadMedia",
    ):
        assert fn in js
    assert "setInterval" in js
    assert "15000" in js
    assert "60000" in js
    assert "confirm(" in js
    for endpoint in ("/api/status", "/api/jobs", "/api/history", "/api/media", "/api/run"):
        assert endpoint in js
    assert "POST" in js
    assert re.findall(r"https?://", js) == []
    assert "innerHTML" not in js
    assert "refreshed " in js
