from pathlib import Path

import pytest

from pdxhackerspace_potluck.config import ConfigError, Settings

URL = "postgresql://u:p@localhost/db"  # not-a-secret


def test_defaults() -> None:
    settings = Settings.from_env({"DATABASE_URL": URL})
    assert settings == Settings(database_url=URL)
    assert settings.port == 8080
    assert settings.example_name == "Jack Hacksman"


def test_reads_environment() -> None:
    env = {
        "DATABASE_URL": URL,
        "HOST": "0.0.0.0",  # noqa: S104
        "PORT": "9000",
        "LOG_LEVEL": "debug",
        "POTLUCK_TITLE": "Spring Potluck",
        "POTLUCK_DATE": "Sat",
        "POTLUCK_LOCATION": "Hall",
        "POTLUCK_DESCRIPTION": "Come!",
        "POTLUCK_EXAMPLE_NAME": " Ada ",
        "POTLUCK_GITHUB_REPO": "https://example.com/repo",
        "POTLUCK_BANNER": "/data/banner.png",
        "POTLUCK_DATA_DIR": "/data",
        "POTLUCK_CATEGORIES": "Mains,Sides",
    }
    settings = Settings.from_env(env)
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.title == "Spring Potluck"
    assert settings.example_name == "Ada"
    assert settings.data_dir == Path("/data")
    assert [c.id for c in settings.categories] == ["mains", "sides"]


def test_blank_example_name_uses_default() -> None:
    env = {"DATABASE_URL": URL, "POTLUCK_EXAMPLE_NAME": "  "}
    assert Settings.from_env(env).example_name == "Jack Hacksman"


def test_requires_database_url() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL is required"):
        Settings.from_env({})


def test_rejects_non_postgres_url() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL must start"):
        Settings.from_env({"DATABASE_URL": "sqlite:///x.db"})


@pytest.mark.parametrize("port", ["eighty", "0", "65536"])
def test_rejects_bad_port(port: str) -> None:
    with pytest.raises(ConfigError, match="PORT"):
        Settings.from_env({"DATABASE_URL": URL, "PORT": port})


def test_rejects_bad_log_level() -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.from_env({"DATABASE_URL": URL, "LOG_LEVEL": "loud"})
