import signal
import threading
from collections.abc import Callable
from types import TracebackType

import pytest

from pdxhackerspace_potluck import __main__ as cli
from pdxhackerspace_potluck import __version__, db

URL = "postgresql://u:p@localhost/db"  # not-a-secret


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"pdxhackerspace-potluck {__version__}\n"


def test_missing_database_url_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert exit_info.value.code == 2
    assert "DATABASE_URL is required" in capsys.readouterr().err


def test_migrate_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    calls: list[str] = []

    def fake_migrate(url: str) -> list[str]:
        calls.append(url)
        return []

    monkeypatch.setattr(db, "migrate", fake_migrate)
    assert cli.main(["migrate"]) == 0
    assert calls == [URL]


class InlineThread:
    """Runs its target when started, so the test needn't wait for it."""

    def __init__(self, target: Callable[[], None]) -> None:
        self.target = target

    def start(self) -> None:
        self.target()


class FakeServer:
    """Stands in for the HTTP server: serves until 'interrupted'."""

    server_port = 1234

    def __init__(self) -> None:
        self.shut_down = False

    def __enter__(self) -> FakeServer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def serve_forever(self) -> None:
        raise KeyboardInterrupt

    def shutdown(self) -> None:
        self.shut_down = True


def test_serves_until_interrupted_and_handles_sigterm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer()
    handlers: dict[int, object] = {}
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(cli, "make_app_server", lambda settings: server)
    monkeypatch.setattr(signal, "signal", handlers.__setitem__)
    monkeypatch.setattr(threading, "Thread", InlineThread)

    assert cli.main([]) == 0

    handler = handlers[signal.SIGTERM]
    assert callable(handler)
    handler(signal.SIGTERM, None)
    assert server.shut_down
