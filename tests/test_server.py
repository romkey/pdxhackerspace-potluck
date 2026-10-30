import json
import threading
import urllib.request
from collections.abc import Iterator

import pytest

from pdxhackerspace_potluck import __version__
from pdxhackerspace_potluck.config import Settings
from pdxhackerspace_potluck.server import make_app_server


@pytest.fixture
def base_url() -> Iterator[str]:
    settings = Settings(database_url="postgresql://unused/unused", port=0)
    server = make_app_server(settings)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_healthz_over_http_needs_no_database(base_url: str) -> None:
    with urllib.request.urlopen(f"{base_url}/healthz", timeout=5) as response:  # noqa: S310
        assert json.load(response) == {"status": "ok", "version": __version__}
