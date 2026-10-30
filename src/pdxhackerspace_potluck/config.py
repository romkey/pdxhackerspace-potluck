"""Settings, read once at startup from environment variables.

Every variable is documented in docs/configuration.md and listed, with a
safe example value, in .env.example.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pdxhackerspace_potluck.categories import Category, load_categories


class ConfigError(ValueError):
    """An environment variable is missing or set to something unusable."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    title: str = "Our Potluck"
    event_date: str = ""
    location: str = ""
    description: str = "Let us know you're coming and what you'll bring."
    example_name: str = "Jack Hacksman"
    github_repo: str = ""
    banner: str = ""
    data_dir: Path = Path("data")
    categories: tuple[Category, ...] = load_categories(None)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        database_url = env.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError("DATABASE_URL is required")
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ConfigError("DATABASE_URL must start with postgresql://")

        port_text = env.get("PORT", str(cls.port))
        try:
            port = int(port_text)
        except ValueError:
            raise ConfigError(f"PORT must be a number, not {port_text!r}") from None
        if not 0 < port < 65536:
            raise ConfigError(f"PORT must be 1-65535, not {port}")

        log_level = env.get("LOG_LEVEL", cls.log_level).upper()
        if log_level not in logging.getLevelNamesMapping():
            raise ConfigError(f"LOG_LEVEL {log_level!r} is not a logging level")

        return cls(
            database_url=database_url,
            host=env.get("HOST", cls.host),
            port=port,
            log_level=log_level,
            title=env.get("POTLUCK_TITLE", cls.title),
            event_date=env.get("POTLUCK_DATE", cls.event_date),
            location=env.get("POTLUCK_LOCATION", cls.location),
            description=env.get("POTLUCK_DESCRIPTION", cls.description),
            example_name=env.get("POTLUCK_EXAMPLE_NAME", "").strip()
            or cls.example_name,
            github_repo=env.get("POTLUCK_GITHUB_REPO", "").strip(),
            banner=env.get("POTLUCK_BANNER", "").strip(),
            data_dir=Path(env.get("POTLUCK_DATA_DIR", str(cls.data_dir))),
            categories=load_categories(env.get("POTLUCK_CATEGORIES")),
        )
