import os
from collections.abc import Iterator

import pytest

from pdxhackerspace_potluck import db
from pdxhackerspace_potluck.config import Settings


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail("DATABASE_URL must point at a test PostgreSQL (see README)")
    db.migrate(url)
    return url


@pytest.fixture
def settings(database_url: str, tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return Settings(database_url=database_url, data_dir=tmp_path_factory.mktemp("data"))


@pytest.fixture
def conn(database_url: str) -> Iterator[db.Conn]:
    """A connection to an empty database."""
    connection = db.connect(database_url)
    connection.execute("TRUNCATE rsvps RESTART IDENTITY CASCADE")
    connection.commit()
    yield connection
    connection.close()
