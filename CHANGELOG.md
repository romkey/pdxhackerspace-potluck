# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.0.3] - 2026-10-30

### Added

- `GET /healthz`, the `migrate` command, and `POTLUCK_DATA_DIR` (where
  banner images are looked for).
- Tests (99% coverage), strict mypy, ruff, pre-commit and CI/Lint/Release
  workflows, following python-ai-rules.
- MIT license.

### Changed

- Updated tooling pins: uv 0.13.6, setup-uv v10.3.3, ruff v0.17.3, shellcheck-py v0.11.0.1-1.
- **Breaking:** the app now stores RSVPs in PostgreSQL. `DATABASE_URL` is
  required and `POTLUCK_DB` is gone. Existing SQLite data is not migrated;
  the database starts empty.
- **Breaking:** the single `app.py` is now an installable package
  (`pdxhackerspace-potluck` command, `src/` layout) managed with uv, served
  by werkzeug's threaded server instead of gunicorn. The image listens on
  8080 as before; `PORT` now applies to the image too.
- Compose files are now `docker-compose.yaml`, `.test`, `.lint` and `.prod`;
  images are published by the Release workflow to `ghcr.io/romkey/pdxhackerspace-potluck`.

### Removed

- `requirements.txt`, the old `Dockerfile` and `publish-image.yml`.
