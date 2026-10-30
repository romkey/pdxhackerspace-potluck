# Configuration

The app reads these environment variables at startup. Put them in `.env`
(copy `.env.example`); compose passes it to the container. An invalid
value stops the app with a message naming the variable.

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATABASE_URL` | *(required)* | PostgreSQL URL, `postgresql://user:password@host:5432/dbname` |
| `HOST` | `127.0.0.1` (`0.0.0.0` in the image) | Address to listen on |
| `PORT` | `8080` | Port to listen on |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `POTLUCK_TITLE` | `Our Potluck` | Event name shown as the heading |
| `POTLUCK_DATE` | *(hidden)* | Free-text date/time line |
| `POTLUCK_LOCATION` | *(hidden)* | Free-text location line |
| `POTLUCK_DESCRIPTION` | `Let us know you're coming and what you'll bring.` | Short blurb under the title |
| `POTLUCK_CATEGORIES` | Meat, Vegetables, Carbs, Appetizers, Desserts, Drinks, Other | Comma-separated dish category labels. Labels become stable lowercase ids, so renaming one moves existing dishes to "Other". |
| `POTLUCK_EXAMPLE_NAME` | `Jack Hacksman` | Example name in the form's name field |
| `POTLUCK_DATA_DIR` | `data` (`/data` in production compose) | Directory searched for `banner.png`, `.jpg`, `.jpeg`, `.webp` or `.gif` |
| `POTLUCK_BANNER` | *(auto-detect)* | Banner image: a file path or an `http(s)` URL. Overrides `POTLUCK_DATA_DIR`. |
| `POTLUCK_GITHUB_REPO` | *(hidden)* | URL for the footer link to the source |

## Database container (production compose; not read by the app)

| Variable | Meaning |
|----------|---------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Credentials and database name the `db` service creates. `DATABASE_URL` must match them, with host `db`. |

## Publishing (not read by the app)

| Variable | Meaning |
|----------|---------|
| `UV_PUBLISH_TOKEN` | PyPI API token, only for publishing by hand with `uv publish`. Releases from GitHub don't need it. |
