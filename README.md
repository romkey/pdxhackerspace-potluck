# Potluck RSVP

[![CI](https://github.com/romkey/pdxhackerspace-potluck/actions/workflows/ci.yaml/badge.svg)](https://github.com/romkey/pdxhackerspace-potluck/actions/workflows/ci.yaml)
[![Lint](https://github.com/romkey/pdxhackerspace-potluck/actions/workflows/lint.yaml/badge.svg)](https://github.com/romkey/pdxhackerspace-potluck/actions/workflows/lint.yaml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A tiny self-hosted RSVP app for potluck dinners. **No accounts, no logins**:
anyone with the link can confirm they're coming and say what they're
bringing, and gets a personal link to edit their RSVP later.

> **AI disclosure:** This project was written by AI under human oversight,
> following [these rules](https://github.com/romkey/python-ai-rules/blob/main/RULES.md).

## What's here

| Path | What it is |
|------|------------|
| `src/pdxhackerspace_potluck/` | The app: `config.py` reads settings from the environment, `db.py` and `migrations/` hold the PostgreSQL access and schema, `web.py` is the Flask app, `templates/page.html` is the UI |
| `tests/` | pytest tests (they need PostgreSQL; the test compose file provides it) |
| `docs/configuration.md` | Every environment variable |

## Features

- One person, one form: name, party size, and as many dishes as they like
- Configurable dish categories; defaults are Meat, Vegetables, Carbs,
  Appetizers, Desserts, Drinks, Other
- A live "what's on the table" summary so the host can spot gaps
- A **personal bookmarkable link** for each guest to edit or remove their
  RSVP from any device
- Optional **1200x400 banner image** at the top of the page
- **Dark mode**, following the visitor's system setting

## Technical details

Flask on werkzeug's threaded server, PostgreSQL through psycopg 3. The
schema is versioned in `src/pdxhackerspace_potluck/migrations/` and applied
by `pdxhackerspace-potluck migrate` (the production compose file runs it
before the app starts).

| Endpoint | |
|----------|-|
| `GET /` | The RSVP page and what everyone is bringing |
| `GET /r/<token>` | A guest's personal page for editing their RSVP |
| `POST /api/rsvp` | Create an RSVP; returns `id` and `token` |
| `PUT /api/rsvp/<id>` | Update an RSVP (JSON body includes its `token`) |
| `DELETE /api/rsvp/<id>` | Remove an RSVP (JSON body includes its `token`) |
| `GET /banner` | The configured banner image, if it's a local file |
| `GET /healthz` | Health check: `{"status": "ok", "version": ...}` |

There are no accounts: each RSVP has a private random token, and the
personal link `/r/<token>` carries it. Anyone without the link sees the
entry read-only. The browser that created an RSVP also remembers it in
`localStorage`, so the main page shows an "Edit your RSVP" link there.

This app has no spam protection. It's meant for sharing a private link with
a known group; for anything wider, put it behind a reverse proxy with HTTPS
(and basic auth if you like).

### Banner image

Use a **1200x400** image (any 3:1 ratio works). Either drop `banner.png`
(or `.jpg`, `.jpeg`, `.webp`, `.gif`) into the `data/` folder (picked up
without a restart), or set `POTLUCK_BANNER` to a file path or an image URL.

## Running it

Requires Docker. Configuration comes from environment variables, kept in
`.env` (see [docs/configuration.md](docs/configuration.md)):

```bash
cp .env.example .env   # then edit it: event details, and the database password
docker compose -f docker-compose.prod.yaml up -d
```

That runs the latest release from `ghcr.io/romkey/pdxhackerspace-potluck` with a PostgreSQL
container (data in the `db-data` volume); set `APP_VERSION=X.Y.Z` to pin a
release. The app answers on http://localhost:8080. Put `DATABASE_URL`'s
password and `POSTGRES_PASSWORD` in `.env` and keep them the same.

### With pip

Needs Python 3.14 or newer and a PostgreSQL database. Install into a
virtual environment, from a release's wheel:

```bash
python3 -m venv ~/.venvs/pdxhackerspace-potluck
~/.venvs/pdxhackerspace-potluck/bin/pip install https://github.com/romkey/pdxhackerspace-potluck/releases/download/vX.Y.Z/pdxhackerspace_potluck-X.Y.Z-py3-none-any.whl
~/.venvs/pdxhackerspace-potluck/bin/pdxhackerspace-potluck --version
```

Set its environment variables yourself (see
[docs/configuration.md](docs/configuration.md)); it doesn't read `.env`.
Run `pdxhackerspace-potluck migrate` once, then `pdxhackerspace-potluck`.

## Development

With Docker, nothing else to install:

```bash
docker compose up --build                                  # run from the working tree, with PostgreSQL
docker compose -f docker-compose.test.yaml run --rm test   # tests with coverage
docker compose -f docker-compose.lint.yaml run --rm lint   # every lint check, as CI runs them
```

With [uv](https://docs.astral.sh/uv/), which installs the exact versions
CI tests (`uv.lock`). Point `DATABASE_URL` at a PostgreSQL, for example the
one from `docker compose up db`:

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/app  # not-a-secret
uv sync
uv run pytest
uv run mypy
uv run pdxhackerspace-potluck migrate && uv run pdxhackerspace-potluck
```

With pip (25.1 or newer, for `--group`). pip doesn't read `uv.lock`, so it
may pick newer dependency versions than CI tested:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e . --group dev
pytest
mypy
pdxhackerspace-potluck migrate && pdxhackerspace-potluck
```

Either way, `uvx pre-commit install` (or `pip install pre-commit &&
pre-commit install`) runs the lint checks on every commit.

## License

[MIT](LICENSE)
