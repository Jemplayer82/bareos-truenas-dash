import pytest

import bareos_client
import bareos.exceptions


class FakeConsole:
    def __init__(self, responses: dict[str, dict[str, object]]):
        self.responses = responses
        self.commands: list[str] = []

    def call(self, command: str) -> dict[str, object]:
        self.commands.append(command)
        return self.responses[command]

    def close(self) -> None:
        pass


def install(monkeypatch, responses: dict[str, dict[str, object]]):
    fake = FakeConsole(responses)
    kwargs_seen: dict[str, object] = {}
    calls = {"count": 0}

    def factory(**kwargs: object) -> FakeConsole:
        calls["count"] += 1
        kwargs_seen.update(kwargs)
        return fake

    monkeypatch.setattr(bareos_client, "DirectorConsoleJson", factory)
    return fake, kwargs_seen, calls


def test_connect_kwargs(monkeypatch):
    monkeypatch.setenv("BAREOS_HOST", "h1")
    monkeypatch.setenv("BAREOS_PORT", "9999")
    monkeypatch.setenv("BAREOS_CONSOLE_NAME", "nm")
    monkeypatch.setenv("BAREOS_CONSOLE_PASSWORD", "pw")

    fake, kwargs_seen, _ = install(monkeypatch, {".jobs": {"jobs": []}})
    bareos_client.list_defined_jobs()

    assert kwargs_seen["address"] == "h1"
    assert kwargs_seen["port"] == 9999
    assert kwargs_seen["name"] == "nm"
    assert kwargs_seen["password"] == "pw"
    assert kwargs_seen["tls_psk_enable"] is False


def test_env_defaults(monkeypatch):
    monkeypatch.delenv("BAREOS_HOST", raising=False)
    monkeypatch.delenv("BAREOS_PORT", raising=False)
    monkeypatch.delenv("BAREOS_CONSOLE_NAME", raising=False)
    monkeypatch.delenv("BAREOS_CONSOLE_PASSWORD", raising=False)

    fake, kwargs_seen, _ = install(monkeypatch, {".jobs": {"jobs": []}})
    bareos_client.list_defined_jobs()

    assert kwargs_seen["address"] == "192.168.1.41"
    assert kwargs_seen["port"] == 9101
    assert kwargs_seen["name"] == "dashboard"
    assert kwargs_seen["password"] == "changeme"


def test_get_status(monkeypatch):
    fake, _, _ = install(monkeypatch, {"version": {"version": {"version": "23.0.4"}}})
    assert bareos_client.get_status() == {"connected": True, "version": "23.0.4"}
    assert fake.commands == ["version"]


def test_list_defined_jobs_sorted(monkeypatch):
    fake, _, _ = install(
        monkeypatch,
        {".jobs": {"jobs": [{"name": "Nightly"}, {"name": "Catalog"}]}},
    )
    assert bareos_client.list_defined_jobs() == ["Catalog", "Nightly"]


def test_list_recent_runs_command_and_numeric_order(monkeypatch):
    fake, _, _ = install(
        monkeypatch,
        {
            "list jobs last limit=5": {
                "jobs": [{"jobid": "2"}, {"jobid": "10"}, {"jobid": "1"}]
            }
        },
    )
    result = bareos_client.list_recent_runs(5)
    assert [row["jobid"] for row in result] == ["10", "2", "1"]
    assert fake.commands == ["list jobs last limit=5"]


def test_list_media_flattens_pool_dict(monkeypatch):
    fake, _, _ = install(
        monkeypatch,
        {
            "list media": {
                "volumes": {
                    "Full": [{"volumename": "v1"}],
                    "Incr": [{"volumename": "v2", "pool": "Keep"}],
                }
            }
        },
    )
    rows = bareos_client.list_media()
    assert len(rows) == 2
    assert rows[0]["volumename"] == "v1"
    assert rows[0]["pool"] == "Full"
    assert rows[1]["volumename"] == "v2"
    assert rows[1]["pool"] == "Keep"
    assert fake.commands == ["list media"]


def test_list_media_flat_passthrough(monkeypatch):
    fake, _, _ = install(
        monkeypatch,
        {"list media": {"media": [{"volumename": "V"}]}},
    )
    assert bareos_client.list_media() == [{"volumename": "V"}]


def test_run_job_command_and_jobid(monkeypatch):
    fake, _, _ = install(
        monkeypatch,
        {"run job=Nightly yes": {"run": {"jobid": "42"}}},
    )
    assert bareos_client.run_job("Nightly") == 42
    assert fake.commands == ["run job=Nightly yes"]


def test_run_job_missing_jobid_raises(monkeypatch):
    install(monkeypatch, {"run job=Nightly yes": {"run": {}}})
    with pytest.raises(bareos_client.BareosUnavailable):
        bareos_client.run_job("Nightly")


def test_run_job_rejects_injection(monkeypatch):
    _, _, calls = install(monkeypatch, {})

    with pytest.raises(ValueError, match="invalid job name"):
        bareos_client.run_job("x yes\ndelete volume")
    assert calls["count"] == 0

    with pytest.raises(ValueError, match="invalid job name"):
        bareos_client.run_job("")
    assert calls["count"] == 0


def test_auth_error_maps_first(monkeypatch):
    def factory(**kwargs: object) -> FakeConsole:
        raise bareos.exceptions.AuthenticationError("bad")

    monkeypatch.setattr(bareos_client, "DirectorConsoleJson", factory)

    with pytest.raises(bareos_client.BareosAuthFailed) as exc_info:
        bareos_client.get_status()

    assert not isinstance(exc_info.value, bareos_client.BareosUnavailable)


def test_connection_error_maps(monkeypatch):
    def connection_error_factory(**kwargs: object) -> FakeConsole:
        raise bareos.exceptions.ConnectionError("down")

    monkeypatch.setattr(bareos_client, "DirectorConsoleJson", connection_error_factory)

    with pytest.raises(bareos_client.BareosUnavailable):
        bareos_client.get_status()

    def os_error_factory(**kwargs: object) -> FakeConsole:
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(bareos_client, "DirectorConsoleJson", os_error_factory)

    with pytest.raises(bareos_client.BareosUnavailable):
        bareos_client.get_status()


def test_call_failure_maps(monkeypatch):
    class FailingFake(FakeConsole):
        def __init__(self, responses: dict[str, dict[str, object]]):
            super().__init__(responses)
            self.close_count = 0

        def call(self, command: str) -> dict[str, object]:
            raise bareos.exceptions.ConnectionLostError("lost")

        def close(self) -> None:
            self.close_count += 1

    fake = FailingFake({".jobs": {"jobs": []}})
    monkeypatch.setattr(
        bareos_client,
        "DirectorConsoleJson",
        lambda **kwargs: fake,
    )

    with pytest.raises(bareos_client.BareosUnavailable):
        bareos_client.list_defined_jobs()

    assert fake.close_count == 1


def test_invalid_bareos_port_raises_bareos_unavailable(monkeypatch):
    monkeypatch.setenv("BAREOS_PORT", "9101a")
    _, _, calls = install(monkeypatch, {})

    with pytest.raises(bareos_client.BareosUnavailable, match="BAREOS_PORT") as exc_info:
        bareos_client.get_status()

    assert "9101a" in str(exc_info.value)
    assert calls["count"] == 0
