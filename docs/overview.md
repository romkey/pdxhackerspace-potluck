# pdxhackerspace-potluck overview

**What:** a tiny self-hosted RSVP app for potluck dinners. No accounts: each
guest gets a private, bookmarkable `/r/<token>` link to edit their RSVP.
**Runs as:** HTTP service on port 8080 (Flask on werkzeug's threaded server).
**Talks to:** PostgreSQL (`DATABASE_URL`).

## Files

- `src/pdxhackerspace_potluck/__main__.py`: command line (`serve`, `migrate`),
  logging, SIGTERM handling.
- `config.py`: `Settings` from environment variables.
- `categories.py`: dish categories (built-in or from `POTLUCK_CATEGORIES`).
- `db.py`: psycopg 3 queries and the migration runner.
- `migrations/`: numbered `.sql` files, tracked in `schema_migrations`.
- `web.py`: Flask app: page, JSON API (`/api/rsvp`), `/banner`, `/healthz`.
- `server.py`: builds the threaded WSGI server.
- `templates/page.html`: the whole UI (inline CSS and JS).
- `tests/`: pytest; one file per module; needs PostgreSQL.
- `Dockerfile`: `dev` and `production` stages.
- `docker-compose.yaml` (dev), `.test`, `.lint`, `.prod`.

## Conventions

- All configuration from environment variables; see docs/configuration.md.
- Edit rights come from the secret token in the guest's link; there is no
  other authentication.
- Rules: https://github.com/romkey/python-ai-rules/blob/main/RULES.md
