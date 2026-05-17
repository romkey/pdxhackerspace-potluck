"""
Potluck RSVP — a tiny self-hosted RSVP app for potluck dinners.

No accounts, no logins. Anyone with the link can confirm they're coming and
list what they're bringing. Each guest may bring more than one dish, and on
submitting they get a unique bookmarkable link (/r/<token>) that lets them
come back and edit their RSVP from any device.

Configure the event with environment variables (see .env.example):
  POTLUCK_TITLE, POTLUCK_DATE, POTLUCK_LOCATION, POTLUCK_DESCRIPTION,
  POTLUCK_CATEGORIES, POTLUCK_EXAMPLE_NAME, POTLUCK_GITHUB_REPO, POTLUCK_DB
"""

import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from flask import (Flask, abort, g, jsonify, redirect,
                   render_template_string, request, send_file, url_for)

# --------------------------------------------------------------------------
# Configuration — override any of these with environment variables.
# --------------------------------------------------------------------------
TITLE = os.environ.get("POTLUCK_TITLE", "Our Potluck")
EVENT_DATE = os.environ.get("POTLUCK_DATE", "")
LOCATION = os.environ.get("POTLUCK_LOCATION", "")
DESCRIPTION = os.environ.get(
    "POTLUCK_DESCRIPTION",
    "Let us know you're coming and what you'll bring.",
)
EXAMPLE_NAME = os.environ.get("POTLUCK_EXAMPLE_NAME", "Jack Hacksman").strip() or "Jack Hacksman"
GITHUB_REPO = os.environ.get("POTLUCK_GITHUB_REPO", "").strip()

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "potluck.db")
DB_PATH = os.environ.get("POTLUCK_DB", _DEFAULT_DB)

# Optional 1200x400 banner image shown at the top of the page. You can either
# set POTLUCK_BANNER to a URL or a file path, or simply drop a file named
# banner.png / banner.jpg / banner.webp into the same folder as the database.
BANNER = os.environ.get("POTLUCK_BANNER", "").strip()
_BANNER_NAMES = ("banner.png", "banner.jpg", "banner.jpeg", "banner.webp", "banner.gif")

# Dish categories. Override with POTLUCK_CATEGORIES="Meat,Vegetables,...".
_DEFAULT_CATEGORIES = [
    {"id": "meat",       "label": "Meat",       "emoji": "\U0001F356", "color": "#b5462f"},
    {"id": "vegetables", "label": "Vegetables", "emoji": "\U0001F957", "color": "#5a8a4a"},
    {"id": "carbs",      "label": "Carbs",      "emoji": "\U0001F35E", "color": "#c2913c"},
    {"id": "appetizers", "label": "Appetizers", "emoji": "\U0001F968", "color": "#d27d3a"},
    {"id": "desserts",   "label": "Desserts",   "emoji": "\U0001F370", "color": "#c96d8f"},
    {"id": "drinks",     "label": "Drinks",     "emoji": "\U0001F964", "color": "#5b8aa6"},
    {"id": "other",      "label": "Other",      "emoji": "\U0001F37D", "color": "#8a7d6b"},
]
CATEGORY_COLORS = [c["color"] for c in _DEFAULT_CATEGORIES]
CATEGORY_FALLBACK = {"id": "other", "label": "Other", "emoji": "\U0001F37D", "color": "#8a7d6b"}


def category_id(label):
    """Turn a configured category label into a stable form value."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "other"


def load_categories(value):
    labels = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not labels:
        return [dict(c) for c in _DEFAULT_CATEGORIES]

    categories = []
    seen = set()
    for index, label in enumerate(labels):
        base_id = category_id(label)
        cat_id = base_id
        suffix = 2
        while cat_id in seen:
            cat_id = f"{base_id}-{suffix}"
            suffix += 1
        seen.add(cat_id)
        categories.append({
            "id": cat_id,
            "label": label[:40],
            "emoji": CATEGORY_FALLBACK["emoji"],
            "color": CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
        })
    return categories


CATEGORIES = load_categories(os.environ.get("POTLUCK_CATEGORIES"))
CATEGORY_IDS = {c["id"] for c in CATEGORIES}
MAX_DISHES = 20

app = Flask(__name__)


# --------------------------------------------------------------------------
# Database helpers (SQLite — a single file, no server needed).
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the data dir / tables, and migrate older databases if needed."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.row_factory = sqlite3.Row

        # Older versions kept category + dish as columns on the rsvps table.
        # If we find that schema, migrate each old row to one rsvp + one dish.
        cols = {r["name"] for r in db.execute("PRAGMA table_info(rsvps)").fetchall()}
        if cols and "category" in cols:
            _migrate_v1_to_v2(db)

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS rsvps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                party_size  INTEGER NOT NULL DEFAULT 1,
                note        TEXT    NOT NULL DEFAULT '',
                token       TEXT    NOT NULL UNIQUE,
                created_at  TEXT    NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS dishes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                rsvp_id   INTEGER NOT NULL REFERENCES rsvps(id) ON DELETE CASCADE,
                category  TEXT    NOT NULL,
                dish      TEXT    NOT NULL DEFAULT ''
            )
            """
        )
        db.commit()


def _migrate_v1_to_v2(db):
    """Convert the old single-table schema into rsvps + dishes."""
    db.execute("ALTER TABLE rsvps RENAME TO rsvps_old")
    db.execute(
        "CREATE TABLE rsvps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
        " party_size INTEGER NOT NULL DEFAULT 1, note TEXT NOT NULL DEFAULT '',"
        " token TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE dishes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " rsvp_id INTEGER NOT NULL REFERENCES rsvps(id) ON DELETE CASCADE,"
        " category TEXT NOT NULL, dish TEXT NOT NULL DEFAULT '')"
    )
    for row in db.execute("SELECT * FROM rsvps_old").fetchall():
        cur = db.execute(
            "INSERT INTO rsvps (name, party_size, note, token, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (row["name"], row["party_size"], row["note"] or "",
             row["token"], row["created_at"]),
        )
        db.execute(
            "INSERT INTO dishes (rsvp_id, category, dish) VALUES (?, ?, ?)",
            (cur.lastrowid, row["category"], row["dish"] or ""),
        )
    db.execute("DROP TABLE rsvps_old")


def clean_rsvp(data):
    """Validate and normalise submitted RSVP data. Returns (clean_dict, error)."""
    name = (data.get("name") or "").strip()
    note = (data.get("note") or "").strip()
    try:
        party_size = int(data.get("party_size") or 1)
    except (ValueError, TypeError):
        party_size = 1
    party_size = max(1, min(party_size, 50))

    dishes = []
    for raw in (data.get("dishes") or []):
        if not isinstance(raw, dict):
            continue
        category = (raw.get("category") or "").strip()
        if category not in CATEGORY_IDS:
            continue
        dishes.append({"category": category,
                       "dish": (raw.get("dish") or "").strip()[:200]})

    if not name:
        return None, "Please add your name."
    if not dishes:
        return None, "Please add at least one dish (just pick a category)."

    return {
        "name": name[:80],
        "party_size": party_size,
        "note": note[:300],
        "dishes": dishes[:MAX_DISHES],
    }, None


def fetch_rsvp(rsvp_id):
    return get_db().execute("SELECT * FROM rsvps WHERE id = ?", (rsvp_id,)).fetchone()


def write_dishes(db, rsvp_id, dishes):
    db.execute("DELETE FROM dishes WHERE rsvp_id = ?", (rsvp_id,))
    db.executemany(
        "INSERT INTO dishes (rsvp_id, category, dish) VALUES (?, ?, ?)",
        [(rsvp_id, d["category"], d["dish"]) for d in dishes],
    )


# --------------------------------------------------------------------------
# Banner image
# --------------------------------------------------------------------------
def resolve_banner():
    """Return ('url', value) | ('file', abspath) | (None, None).

    Resolved on each request so a banner can be dropped in without a restart.
    """
    if BANNER:
        if BANNER.startswith(("http://", "https://")):
            return "url", BANNER
        if os.path.isfile(BANNER):
            return "file", os.path.abspath(BANNER)
        return None, None
    # Nothing configured — look for a banner file next to the database.
    data_dir = os.path.dirname(os.path.abspath(DB_PATH))
    for name in _BANNER_NAMES:
        candidate = os.path.join(data_dir, name)
        if os.path.isfile(candidate):
            return "file", candidate
    return None, None


# --------------------------------------------------------------------------
# Page rendering
# --------------------------------------------------------------------------
def render_page(editing=None, link_error=False):
    db = get_db()
    rsvps = db.execute("SELECT * FROM rsvps ORDER BY created_at").fetchall()
    dishes = db.execute("SELECT * FROM dishes ORDER BY id").fetchall()

    by_id = {r["id"]: r for r in rsvps}

    # Flatten into per-dish entries, then group those by category.
    grouped = {c["id"]: [] for c in CATEGORIES}
    uncategorized = []
    for d in dishes:
        host = by_id.get(d["rsvp_id"])
        if host is None:
            continue
        entries = grouped.get(d["category"])
        if entries is None:
            entries = grouped["other"] if "other" in grouped else uncategorized
        entries.append({
            "rsvp_id": host["id"],
            "name": host["name"],
            "party_size": host["party_size"],
            "note": host["note"],
            "dish": d["dish"],
        })

    sections = [
        {**c, "entries": grouped[c["id"]], "count": len(grouped[c["id"]])}
        for c in CATEGORIES
    ]
    if uncategorized:
        sections.append({
            **CATEGORY_FALLBACK,
            "entries": uncategorized,
            "count": len(uncategorized),
        })

    kind, value = resolve_banner()
    banner_src = value if kind == "url" else ("/banner" if kind == "file" else None)

    return render_template_string(
        PAGE,
        title=TITLE,
        event_date=EVENT_DATE,
        location=LOCATION,
        description=DESCRIPTION,
        example_name=EXAMPLE_NAME,
        github_repo=GITHUB_REPO,
        banner_src=banner_src,
        categories=CATEGORIES,
        categories_json=json.dumps(CATEGORIES),
        sections=sections,
        rsvp_count=len(rsvps),
        head_count=sum(r["party_size"] for r in rsvps),
        dish_count=len(dishes),
        editing_json=json.dumps(editing),
        link_error=link_error,
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_page(link_error=request.args.get("notfound") == "1")


@app.route("/banner")
def banner():
    """Serve the configured banner image (local files only)."""
    kind, value = resolve_banner()
    if kind == "file":
        return send_file(value, max_age=3600)
    abort(404)


@app.route("/r/<token>")
def edit_link(token):
    """A guest's personal, bookmarkable RSVP page."""
    row = get_db().execute(
        "SELECT * FROM rsvps WHERE token = ?", (token,)).fetchone()
    if row is None:
        return redirect(url_for("index", notfound=1))

    dishes = get_db().execute(
        "SELECT category, dish FROM dishes WHERE rsvp_id = ? ORDER BY id",
        (row["id"],)).fetchall()

    editing = {
        "id": row["id"],
        "token": row["token"],
        "name": row["name"],
        "party_size": row["party_size"],
        "note": row["note"],
        "dishes": [{"category": d["category"], "dish": d["dish"]} for d in dishes],
    }
    return render_page(editing=editing)


@app.route("/api/rsvp", methods=["POST"])
def create_rsvp():
    data, error = clean_rsvp(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400

    token = secrets.token_urlsafe(16)
    db = get_db()
    cur = db.execute(
        "INSERT INTO rsvps (name, party_size, note, token, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (data["name"], data["party_size"], data["note"], token,
         datetime.now(timezone.utc).isoformat()),
    )
    write_dishes(db, cur.lastrowid, data["dishes"])
    db.commit()
    return jsonify(id=cur.lastrowid, token=token)


@app.route("/api/rsvp/<int:rsvp_id>", methods=["PUT"])
def update_rsvp(rsvp_id):
    payload = request.get_json(silent=True) or {}
    row = fetch_rsvp(rsvp_id)
    if row is None:
        return jsonify(error="That RSVP no longer exists."), 404
    if payload.get("token") != row["token"]:
        return jsonify(error="You can only edit your own RSVP."), 403

    data, error = clean_rsvp(payload)
    if error:
        return jsonify(error=error), 400

    db = get_db()
    db.execute(
        "UPDATE rsvps SET name = ?, party_size = ?, note = ? WHERE id = ?",
        (data["name"], data["party_size"], data["note"], rsvp_id),
    )
    write_dishes(db, rsvp_id, data["dishes"])
    db.commit()
    return jsonify(ok=True)


@app.route("/api/rsvp/<int:rsvp_id>", methods=["DELETE"])
def delete_rsvp(rsvp_id):
    payload = request.get_json(silent=True) or {}
    row = fetch_rsvp(rsvp_id)
    if row is None:
        return jsonify(ok=True)  # already gone
    if payload.get("token") != row["token"]:
        return jsonify(error="You can only remove your own RSVP."), 403

    db = get_db()
    db.execute("DELETE FROM dishes WHERE rsvp_id = ?", (rsvp_id,))
    db.execute("DELETE FROM rsvps WHERE id = ?", (rsvp_id,))
    db.commit()
    return jsonify(ok=True)


# Initialise the database as soon as the module is imported (works under
# gunicorn as well as the built-in dev server).
init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)


# --------------------------------------------------------------------------
# The page template. Kept inline so the whole app is a single file to deploy.
# --------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — RSVP</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: light dark;
    --paper:   #f7f1e3;
    --card:    #fffdf8;
    --ink:     #2c2820;
    --muted:   #7d7361;
    --line:    #ddd2ba;
    --accent:  #b5462f;
    --accent-d:#963a27;
    --soft:    #fbf4e6;
    --ok:      #5a8a4a;
    --mine-bg: rgba(181,70,47,.05);
    --glow-a:  rgba(181,70,47,.06);
    --glow-b:  rgba(90,138,74,.07);
    --shadow:  rgba(44,40,32,.5);
  }
  /* Dark mode — follows the operating system / browser setting. */
  @media (prefers-color-scheme: dark) {
    :root {
      --paper:   #1b1915;
      --card:    #262219;
      --ink:     #ece3d0;
      --muted:   #a09684;
      --line:    #3c372c;
      --accent:  #e07a5f;
      --accent-d:#ee8d74;
      --soft:    #2f2a20;
      --ok:      #84b06f;
      --mine-bg: rgba(224,122,95,.12);
      --glow-a:  rgba(224,122,95,.10);
      --glow-b:  rgba(132,176,111,.09);
      --shadow:  rgba(0,0,0,.55);
    }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: 'Hanken Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--ink);
    background-color: var(--paper);
    background-image:
      radial-gradient(circle at 12% 18%, var(--glow-a) 0, transparent 38%),
      radial-gradient(circle at 88% 82%, var(--glow-b) 0, transparent 42%);
    line-height: 1.55;
    -webkit-text-size-adjust: 100%;
  }
  .wrap { max-width: 680px; margin: 0 auto; padding: 38px 20px 80px; }

  /* ---- Banner image (optional) ---- */
  .banner-hero {
    margin-bottom: 26px;
    border: 1px solid var(--line);
    border-radius: 16px;
    overflow: hidden;
    aspect-ratio: 3 / 1;            /* matches a 1200x400 image */
    background: var(--card);
    box-shadow: 0 1px 0 rgba(0,0,0,.02), 0 16px 34px -24px var(--shadow);
  }
  .banner-hero img {
    display: block; width: 100%; height: 100%; object-fit: cover;
  }

  /* ---- Header ---- */
  header { text-align: center; margin-bottom: 30px; }
  .kicker {
    font-size: 12px; letter-spacing: .22em; text-transform: uppercase;
    color: var(--accent); font-weight: 600; margin-bottom: 10px;
  }
  h1 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600; font-size: clamp(2.3rem, 7vw, 3.4rem);
    line-height: 1.04; margin: 0 0 14px; letter-spacing: -.01em;
  }
  .meta {
    display: flex; flex-wrap: wrap; gap: 6px 18px;
    justify-content: center; color: var(--muted);
    font-size: 15px; margin-bottom: 12px;
  }
  .meta span { white-space: nowrap; }
  .desc { color: var(--muted); max-width: 460px; margin: 0 auto; font-size: 15.5px; }

  /* ---- Cards ---- */
  .card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 22px 22px 24px;
    margin-bottom: 22px;
    box-shadow: 0 1px 0 rgba(0,0,0,.02), 0 14px 30px -22px var(--shadow);
  }
  .card h2 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600; font-size: 1.32rem; margin: 0 0 4px;
  }
  .card .sub { color: var(--muted); font-size: 14px; margin-bottom: 16px; }

  /* ---- Coverage strip ---- */
  .coverage { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid var(--line); border-radius: 999px;
    padding: 5px 12px; font-size: 13px; background: var(--card);
  }
  .pill .n { font-weight: 600; }
  .pill.empty { opacity: .42; }
  .tally {
    font-family: 'Fraunces', Georgia, serif;
    font-size: 15px; color: var(--muted); margin-top: 14px;
  }
  .tally b { color: var(--ink); }

  /* ---- Bookmark banner (edit mode) ---- */
  .bookmark {
    border: 1px solid var(--line);
    border-left: 4px solid var(--accent);
    background: var(--soft);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 22px;
  }
  .bookmark .bk-title {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600; font-size: 1.05rem; margin-bottom: 3px;
  }
  .bookmark .bk-sub { color: var(--muted); font-size: 14px; margin-bottom: 11px; }
  .bk-row { display: flex; gap: 8px; }
  .bk-row input {
    flex: 1; min-width: 0; font: inherit; font-size: 13.5px;
    padding: 9px 11px; color: var(--muted);
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  }
  .bk-copy {
    font: inherit; font-weight: 600; font-size: 14px; cursor: pointer;
    white-space: nowrap; border: 1px solid var(--accent);
    background: var(--card); color: var(--accent);
    border-radius: 8px; padding: 9px 15px; transition: background .15s, color .15s;
  }
  .bk-copy:hover { background: var(--accent); color: #fff; }
  .saved-flag {
    display: inline-block; font-size: 12px; font-weight: 600;
    letter-spacing: .04em; text-transform: uppercase;
    color: var(--ok); margin-bottom: 6px;
  }

  /* ---- Form ---- */
  .field { margin-bottom: 14px; }
  .row { display: flex; gap: 12px; }
  .row .field { flex: 1; }
  .row .field.small { flex: 0 0 130px; }
  label {
    display: block; font-size: 13px; font-weight: 600;
    margin-bottom: 5px; color: var(--ink);
  }
  label .opt { color: var(--muted); font-weight: 400; }
  input, select, textarea {
    width: 100%; font: inherit; font-size: 15px;
    padding: 10px 12px; color: var(--ink);
    background: var(--paper);
    border: 1px solid var(--line); border-radius: 9px;
    transition: border-color .15s, box-shadow .15s;
  }
  textarea { resize: vertical; min-height: 52px; }
  input:focus, select:focus, textarea:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(181,70,47,.13);
  }

  /* ---- Dish rows ---- */
  .dish-row {
    display: flex; gap: 8px; align-items: center;
    margin-bottom: 8px; flex-wrap: wrap;
  }
  .dish-row .dr-cat { flex: 0 0 150px; }
  .dish-row .dr-desc { flex: 1; min-width: 150px; }
  .dish-row .dr-remove {
    flex: 0 0 auto; width: 38px; height: 38px; padding: 0;
    font-size: 19px; line-height: 1; cursor: pointer;
    color: var(--muted); background: var(--paper);
    border: 1px solid var(--line); border-radius: 9px;
  }
  .dish-row .dr-remove:hover { color: var(--accent); border-color: var(--accent); }
  .add-dish { margin: 2px 0 16px; }

  .btn {
    font: inherit; font-weight: 600; font-size: 15px;
    cursor: pointer; border: none; border-radius: 9px;
    padding: 12px 20px; color: #fff; background: var(--accent);
    transition: background .15s, transform .05s;
  }
  .btn:hover { background: var(--accent-d); }
  .btn:active { transform: translateY(1px); }
  .btn[disabled] { opacity: .6; cursor: progress; }
  .actions {
    display: flex; align-items: center; gap: 16px;
    margin-top: 4px; flex-wrap: wrap;
  }
  .linkbtn {
    background: none; border: none; cursor: pointer; padding: 0;
    color: var(--muted); font: inherit; font-size: 14px;
    text-decoration: underline; text-underline-offset: 3px;
  }
  .linkbtn:hover { color: var(--ink); }
  .linkbtn.danger:hover { color: var(--accent-d); }
  .msg { font-size: 14px; margin-top: 10px; min-height: 1px; }
  .msg.error { color: var(--accent-d); }

  /* ---- Guest list ---- */
  .section { margin-bottom: 26px; }
  .section:last-child { margin-bottom: 0; }
  .section-head {
    display: flex; align-items: baseline; gap: 9px;
    padding-bottom: 7px; margin-bottom: 12px;
    border-bottom: 2px solid var(--cat, var(--line));
  }
  .section-head .emoji { font-size: 19px; }
  .section-head h3 {
    font-family: 'Fraunces', Georgia, serif;
    font-size: 1.16rem; font-weight: 600; margin: 0;
    color: var(--cat, var(--ink));
  }
  .section-head .count { color: var(--muted); font-size: 13px; margin-left: auto; }
  .section.is-empty .section-head { opacity: .5; }
  .section-empty { color: var(--muted); font-size: 14px; font-style: italic; }

  .entry {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 11px 0; border-bottom: 1px dashed var(--line);
  }
  .entry:last-child { border-bottom: none; }
  .entry .dot {
    flex: 0 0 9px; height: 9px; margin-top: 7px; border-radius: 50%;
    background: var(--cat, var(--muted));
  }
  .entry .body { flex: 1; min-width: 0; }
  .entry .who { font-weight: 600; }
  .entry .party {
    font-size: 12px; color: var(--muted); font-weight: 500;
    border: 1px solid var(--line); border-radius: 999px;
    padding: 1px 7px; margin-left: 6px;
  }
  .entry .you {
    font-size: 11px; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--accent); margin-left: 6px;
  }
  .entry .dish { font-size: 15px; }
  .entry .dish.none { color: var(--muted); font-style: italic; }
  .entry .note { font-size: 13.5px; color: var(--muted); margin-top: 1px; }
  .entry .ctl { display: none; margin-top: 5px; }
  .entry.mine .ctl { display: block; }
  .entry .ctl a {
    color: var(--accent); font-size: 14px;
    text-decoration: underline; text-underline-offset: 3px;
  }
  .entry.mine {
    background: var(--mine-bg); border-radius: 8px;
    margin: 0 -8px; padding-left: 8px; padding-right: 8px;
  }

  .empty-all {
    text-align: center; color: var(--muted);
    font-style: italic; padding: 16px 0;
  }
  .notice {
    background: var(--soft); border: 1px solid var(--line);
    border-radius: 10px; padding: 12px 15px; font-size: 14px;
    color: var(--accent-d); margin-bottom: 22px;
  }
  footer {
    text-align: center; color: var(--muted);
    font-size: 12.5px; margin-top: 30px;
  }
  footer a {
    color: inherit; text-decoration: underline; text-underline-offset: 3px;
  }
  @media (max-width: 460px) {
    .row { flex-wrap: wrap; }
    .row .field.small { flex: 1 1 100%; }
    .dish-row .dr-cat { flex: 1 1 100%; }
  }
</style>
</head>
<body>
<div class="wrap">

  {% if banner_src %}
  <div class="banner-hero">
    <img src="{{ banner_src }}" alt="{{ title }}">
  </div>
  {% endif %}

  <header>
    <div class="kicker">You're invited</div>
    <h1>{{ title }}</h1>
    <div class="meta">
      {% if event_date %}<span>&#128197; {{ event_date }}</span>{% endif %}
      {% if location %}<span>&#128205; {{ location }}</span>{% endif %}
    </div>
    {% if description %}<p class="desc">{{ description }}</p>{% endif %}
  </header>

  {% if link_error %}
  <div class="notice">That RSVP link wasn't found — it may have been removed. You can RSVP again below.</div>
  {% endif %}

  <!-- Personal bookmark link (only shown when editing via /r/&lt;token&gt;) -->
  <div class="bookmark" id="bookmark" hidden>
    <div class="saved-flag" id="saved-flag" hidden>&#10003; RSVP saved</div>
    <div class="bk-title">This is your personal RSVP link</div>
    <div class="bk-sub">Bookmark this page — open it any time, on any device, to change your RSVP or what you're bringing.</div>
    <div class="bk-row">
      <input id="bk-url" type="text" readonly>
      <button class="bk-copy" id="bk-copy" type="button">Copy link</button>
    </div>
  </div>

  <!-- Coverage summary -->
  <div class="card">
    <h2>What's on the table</h2>
    <div class="sub">A quick look at what's covered so far.</div>
    <div class="coverage">
      {% for s in sections %}
      <span class="pill {% if s.count == 0 %}empty{% endif %}">
        {{ s.emoji }} {{ s.label }} <span class="n">{{ s.count }}</span>
      </span>
      {% endfor %}
    </div>
    <div class="tally">
      <b>{{ rsvp_count }}</b> {{ 'person' if rsvp_count == 1 else 'people' }} RSVP'd
      &middot; <b>{{ head_count }}</b> coming
      &middot; <b>{{ dish_count }}</b> {{ 'dish' if dish_count == 1 else 'dishes' }} on the way
    </div>
  </div>

  <!-- RSVP form -->
  <div class="card" id="form-card">
    <h2 id="form-title">Count me in</h2>
    <div class="sub" id="form-sub">No account needed — just fill this in.</div>
    <div class="field">
      <label for="f-name">Your name</label>
      <input id="f-name" type="text" maxlength="80" placeholder="e.g. {{ example_name }}" autocomplete="name">
    </div>
    <div class="row">
      <div class="field small">
        <label for="f-party">How many <span class="opt">(incl. you)</span></label>
        <input id="f-party" type="number" min="1" max="50" value="1">
      </div>
    </div>

    <label>What are you bringing? <span class="opt">(add as many dishes as you like)</span></label>
    <div id="dish-list"></div>
    <button class="linkbtn add-dish" id="add-dish" type="button">+ Add another dish</button>

    <div class="field">
      <label for="f-note">Note <span class="opt">(optional)</span></label>
      <textarea id="f-note" maxlength="300" placeholder="Allergies, serving size, running late…"></textarea>
    </div>
    <div class="actions">
      <button class="btn" id="submit-btn">I'm coming &#127881;</button>
      <button class="linkbtn danger" id="delete-btn" type="button" hidden>Remove my RSVP</button>
    </div>
    <div class="msg" id="form-msg"></div>
  </div>

  <!-- Guest list -->
  <div class="card">
    <h2>Who's coming &amp; what they're bringing</h2>
    <div class="sub">Each dish shows under its category. Use your personal link to edit yours.</div>
    {% if dish_count == 0 %}
      <div class="empty-all">No RSVPs yet — be the first to sign up! &#127869;</div>
    {% else %}
      {% for s in sections %}
      <div class="section {% if s.count == 0 %}is-empty{% endif %}" style="--cat: {{ s.color }}">
        <div class="section-head">
          <span class="emoji">{{ s.emoji }}</span>
          <h3>{{ s.label }}</h3>
          <span class="count">{{ s.count }}</span>
        </div>
        {% if s.count == 0 %}
          <div class="section-empty">Nothing here yet.</div>
        {% else %}
          {% for e in s.entries %}
          <div class="entry" style="--cat: {{ s.color }}" data-rsvp="{{ e.rsvp_id }}">
            <span class="dot"></span>
            <div class="body">
              <div>
                <span class="who">{{ e.name }}</span>
                {% if e.party_size > 1 %}<span class="party">party of {{ e.party_size }}</span>{% endif %}
                <span class="you" hidden>You</span>
              </div>
              {% if e.dish %}
                <div class="dish">{{ e.dish }}</div>
              {% else %}
                <div class="dish none">Dish to be decided</div>
              {% endif %}
              {% if e.note %}<div class="note">{{ e.note }}</div>{% endif %}
              <div class="ctl"><a href="#">Edit your RSVP &#8599;</a></div>
            </div>
          </div>
          {% endfor %}
        {% endif %}
      </div>
      {% endfor %}
    {% endif %}
  </div>

  <footer>
    Potluck RSVP &middot; open to everyone with the link &middot; no sign-up required
    {% if github_repo %}&middot; <a href="{{ github_repo }}" rel="noopener">GitHub</a>{% endif %}
  </footer>
</div>

<script id="categories-data" type="application/json">{{ categories_json|safe }}</script>
<script id="editing-data" type="application/json">{{ editing_json|safe }}</script>
<script>
(function () {
  "use strict";
  var STORE = "potluck_mine_v2";
  var CATS = JSON.parse(document.getElementById("categories-data").textContent);
  var EDITING = JSON.parse(document.getElementById("editing-data").textContent);

  // --- localStorage: map of {rsvpId: token} for entries made on this device ---
  function getMine() {
    try { return JSON.parse(localStorage.getItem(STORE)) || {}; }
    catch (e) { return {}; }
  }
  function saveMine(map) {
    try { localStorage.setItem(STORE, JSON.stringify(map)); } catch (e) {}
  }
  function rememberMine(id, token) {
    var m = getMine(); m[id] = token; saveMine(m);
  }
  function forgetMine(id) {
    var m = getMine(); delete m[id]; saveMine(m);
  }

  // --- Element references ---
  var els = {
    name: document.getElementById("f-name"),
    party: document.getElementById("f-party"),
    note: document.getElementById("f-note"),
    dishList: document.getElementById("dish-list"),
    addDish: document.getElementById("add-dish"),
    submit: document.getElementById("submit-btn"),
    del: document.getElementById("delete-btn"),
    msg: document.getElementById("form-msg"),
    title: document.getElementById("form-title"),
    sub: document.getElementById("form-sub"),
    bookmark: document.getElementById("bookmark"),
    bkUrl: document.getElementById("bk-url"),
    bkCopy: document.getElementById("bk-copy"),
    savedFlag: document.getElementById("saved-flag")
  };

  function showMsg(text, isError) {
    els.msg.textContent = text || "";
    els.msg.className = "msg" + (isError ? " error" : "");
  }

  // --- Dish rows -------------------------------------------------------
  function refreshRemoveButtons() {
    var rows = els.dishList.querySelectorAll(".dish-row");
    rows.forEach(function (row) {
      row.querySelector(".dr-remove").style.visibility =
        rows.length > 1 ? "visible" : "hidden";
    });
  }

  function addDishRow(category, desc) {
    var row = document.createElement("div");
    row.className = "dish-row";

    var sel = document.createElement("select");
    sel.className = "dr-cat";
    CATS.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.emoji + "\u00a0 " + c.label;
      sel.appendChild(o);
    });
    if (category) sel.value = category;

    var desc_input = document.createElement("input");
    desc_input.className = "dr-desc";
    desc_input.type = "text";
    desc_input.maxLength = 200;
    desc_input.placeholder = "What are you bringing? (optional)";
    desc_input.value = desc || "";

    var rm = document.createElement("button");
    rm.type = "button";
    rm.className = "dr-remove";
    rm.title = "Remove this dish";
    rm.innerHTML = "&times;";
    rm.addEventListener("click", function () {
      if (els.dishList.querySelectorAll(".dish-row").length > 1) {
        row.remove();
        refreshRemoveButtons();
      }
    });

    row.appendChild(sel);
    row.appendChild(desc_input);
    row.appendChild(rm);
    els.dishList.appendChild(row);
    refreshRemoveButtons();
  }

  function collectDishes() {
    var out = [];
    els.dishList.querySelectorAll(".dish-row").forEach(function (row) {
      out.push({
        category: row.querySelector(".dr-cat").value,
        dish: row.querySelector(".dr-desc").value.trim()
      });
    });
    return out;
  }

  els.addDish.addEventListener("click", function () {
    if (els.dishList.querySelectorAll(".dish-row").length >= 20) {
      showMsg("That's plenty of dishes!", true);
      return;
    }
    addDishRow(null, "");
  });

  // --- Submit (create or update) --------------------------------------
  function submit() {
    var data = {
      name: els.name.value.trim(),
      party_size: parseInt(els.party.value, 10) || 1,
      note: els.note.value.trim(),
      dishes: collectDishes()
    };
    if (!data.name) { showMsg("Please add your name.", true); els.name.focus(); return; }

    var creating = !EDITING;
    var url = creating ? "/api/rsvp" : "/api/rsvp/" + EDITING.id;
    var body = creating ? data : Object.assign({ token: EDITING.token }, data);

    els.submit.disabled = true;
    showMsg(creating ? "Sending…" : "Saving…");

    fetch(url, {
      method: creating ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          els.submit.disabled = false;
          showMsg(res.j.error || "Something went wrong. Please try again.", true);
          return;
        }
        if (creating) {
          rememberMine(res.j.id, res.j.token);
          // Send them to their personal, bookmarkable link.
          window.location = "/r/" + res.j.token + "?saved=1";
        } else {
          window.location.reload();
        }
      })
      .catch(function () {
        els.submit.disabled = false;
        showMsg("Couldn't reach the server. Please try again.", true);
      });
  }

  function removeRsvp() {
    if (!EDITING) return;
    if (!window.confirm("Remove your RSVP for " + EDITING.name + "?")) return;

    fetch("/api/rsvp/" + EDITING.id, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: EDITING.token })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { window.alert(res.j.error || "Could not remove that RSVP."); return; }
        forgetMine(EDITING.id);
        window.location = "/";
      })
      .catch(function () { window.alert("Couldn't reach the server. Please try again."); });
  }

  els.submit.addEventListener("click", submit);
  els.del.addEventListener("click", removeRsvp);

  // --- Mode setup ------------------------------------------------------
  if (EDITING) {
    // Editing an existing RSVP via its personal link.
    els.title.textContent = "Your RSVP";
    els.sub.textContent = "Change anything below and save — bring as many dishes as you like.";
    els.submit.textContent = "Save changes";
    els.del.hidden = false;
    els.name.value = EDITING.name;
    els.party.value = EDITING.party_size;
    els.note.value = EDITING.note;
    (EDITING.dishes.length ? EDITING.dishes : [{ category: null, dish: "" }])
      .forEach(function (d) { addDishRow(d.category, d.dish); });

    // Show the bookmark banner with this page's URL.
    els.bookmark.hidden = false;
    els.bkUrl.value = window.location.origin + "/r/" + EDITING.token;
    if (/[?&]saved=1\b/.test(window.location.search)) {
      els.savedFlag.hidden = false;
      // Tidy the address bar so the bookmarked URL is clean.
      history.replaceState(null, "", "/r/" + EDITING.token);
    }
    els.bkCopy.addEventListener("click", function () {
      var done = function () {
        els.bkCopy.textContent = "Copied \u2713";
        setTimeout(function () { els.bkCopy.textContent = "Copy link"; }, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(els.bkUrl.value).then(done, function () {
          els.bkUrl.select(); document.execCommand("copy"); done();
        });
      } else {
        els.bkUrl.select(); document.execCommand("copy"); done();
      }
    });

    // Highlight this guest's dishes in the list below.
    document.querySelectorAll('.entry[data-rsvp="' + EDITING.id + '"]')
      .forEach(function (node) {
        node.classList.add("mine");
        var tag = node.querySelector(".you");
        if (tag) tag.hidden = false;
        var link = node.querySelector(".ctl a");
        if (link) link.setAttribute("href", "/r/" + EDITING.token);
      });
  } else {
    // Fresh RSVP — start with one empty dish row.
    addDishRow(null, "");

    // If earlier RSVPs were made on this device, mark them and link to edit.
    var mine = getMine();
    Object.keys(mine).forEach(function (id) {
      document.querySelectorAll('.entry[data-rsvp="' + id + '"]')
        .forEach(function (node) {
          node.classList.add("mine");
          var tag = node.querySelector(".you");
          if (tag) tag.hidden = false;
          var link = node.querySelector(".ctl a");
          if (link) link.setAttribute("href", "/r/" + mine[id]);
        });
    });
  }

  // Ctrl/Cmd+Enter submits from the note field.
  els.note.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
  });
})();
</script>
</body>
</html>
"""
