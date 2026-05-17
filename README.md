# Potluck RSVP

A tiny self-hosted RSVP app for potluck dinners. **No accounts, no logins** —
anyone with the link can confirm they're coming and say what they're bringing.

- One person, one form: name, party size, and as many dishes as they like
- Each dish has a configurable category; defaults are Meat, Vegetables, Carbs,
  Appetizers, Desserts, Drinks, Other
- A live "what's on the table" summary so the host can spot gaps
- On submitting, each guest gets a **personal bookmarkable link** that lets
  them come back and edit their RSVP from any device
- Optional **1200x400 banner image** at the top of the page
- **Dark mode** automatically, following the visitor's system setting
- Single Python file + SQLite — nothing else to run

Written by Claude/Cursor.

## Quick start (Docker)

1. Copy the example environment and edit it for your event:

   ```bash
   cp .env.example .env
   ```

2. Build and start it:

   ```bash
   docker compose up -d --build
   ```

3. Open `http://your-server:8080` and share that link with your guests.

The RSVP database is stored in `./data/potluck.db` (a Docker volume), so it
survives restarts and rebuilds. To stop: `docker compose down`.

## Run without Docker

```bash
pip install -r requirements.txt
python app.py          # serves on http://localhost:8080
```

Configure the event with environment variables, e.g.:

```bash
POTLUCK_TITLE="Spring Potluck" \
POTLUCK_DATE="Sat, May 30 · 6 PM" \
POTLUCK_LOCATION="The community hall" \
python app.py
```

For something longer-lived than the dev server, use gunicorn:

```bash
gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 app:app
```

## Configuration

| Variable              | What it does                          | Default                |
|-----------------------|----------------------------------------|------------------------|
| `POTLUCK_TITLE`       | Event name shown as the heading        | `Our Potluck`          |
| `POTLUCK_DATE`        | Free-text date/time line               | *(hidden if empty)*    |
| `POTLUCK_LOCATION`    | Free-text location line                | *(hidden if empty)*    |
| `POTLUCK_DESCRIPTION` | Short blurb under the title            | a generic invite line  |
| `POTLUCK_CATEGORIES`  | Comma-separated dish category labels   | current built-ins      |
| `POTLUCK_EXAMPLE_NAME` | Example name shown in the RSVP form   | `Jack Hacksman`        |
| `POTLUCK_DB`          | Path to the SQLite file                | `./data/potluck.db`    |
| `POTLUCK_BANNER`      | Banner image — a file path or a URL    | *(auto-detect, below)* |
| `POTLUCK_GITHUB_REPO` | Optional footer link to the source repo | *(hidden if empty)*   |
| `PORT`                | Port for `python app.py` dev server    | `8080`                 |

Set `POTLUCK_CATEGORIES` as a comma-separated list, for example:

```bash
POTLUCK_CATEGORIES="Mains,Sides,Desserts,Drinks"
```

Configured category labels are turned into stable lowercase IDs, so changing
the labels later can affect where existing RSVP dishes appear.

## Banner image

To show a graphical banner across the top of the page, use a **1200x400**
image (any 3:1 ratio works — it's scaled to fit). There are two ways to add
one:

- **Easiest:** drop a file named `banner.png` (or `.jpg` / `.jpeg` / `.webp`
  / `.gif`) into the `data/` folder, next to the database. It's picked up
  automatically — no restart needed.
- **Or** set `POTLUCK_BANNER` to a file path (e.g. `/data/banner.png`) or to
  a full image URL (e.g. `https://.../banner.png`).

Leave it unset and the page simply shows the plain text header.

## Dark mode

Dark mode is automatic — the page follows each visitor's operating system or
browser setting (`prefers-color-scheme`). There's no toggle and nothing to
configure; light and dark palettes are both built in.

## Publishing a container image

The GitHub Actions workflow in `.github/workflows/publish-image.yml` builds and
publishes the Docker image to GitHub Container Registry as
`ghcr.io/<owner>/<repo>`.

It runs on pushes to `main`, version tags like `v1.0.0`, and manual
`workflow_dispatch` runs. The workflow uses the repository `GITHUB_TOKEN` with
`packages: write` permission.

## How "no login" editing works

There are no accounts. When someone submits an RSVP, the app gives it a
private random token and sends them to their **personal link**,
`http://your-server:8080/r/<token>`. Bookmarking that page lets them return —
on any device — to change their RSVP, add or drop dishes, or remove
themselves entirely. Anyone without the link just sees the entry as
read-only.

As a convenience, the browser that created an RSVP also remembers it (in
`localStorage`), so revisiting the main page shows an "Edit your RSVP" link
on those entries. Losing that browser state just means using the bookmarked
link instead — the RSVP itself is unaffected.

## Upgrading from an earlier version

If you ran an older single-dish version, the database is migrated
automatically on first start: every existing RSVP becomes a guest with one
dish, and personal links keep working. No manual steps needed — but back up
`data/potluck.db` first if you want to be safe.

## Notes

- Runtime configuration lives in `.env.example`; copy it to `.env` for local
  Docker Compose runs.
- This app has no spam protection — it's meant for sharing a private link with
  a known group, not posting publicly. Put it behind a reverse proxy with
  HTTPS (and a basic-auth gate if you want) for anything beyond a friendly
  guest list.
