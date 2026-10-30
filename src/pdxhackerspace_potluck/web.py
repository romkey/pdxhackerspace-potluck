"""The Flask app: the RSVP page, the JSON API and GET /healthz."""

import json
import logging
import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.wrappers import Response as WerkzeugResponse

from pdxhackerspace_potluck import __version__, db
from pdxhackerspace_potluck.categories import FALLBACK
from pdxhackerspace_potluck.config import Settings

logger = logging.getLogger(__name__)

MAX_DISHES = 20
MAX_PARTY_SIZE = 50
_BANNER_NAMES = ("banner.png", "banner.jpg", "banner.jpeg", "banner.webp", "banner.gif")


class InvalidRsvpError(ValueError):
    """Submitted RSVP data can't be used; the message is shown to the guest."""


@dataclass(frozen=True)
class CleanRsvp:
    name: str
    party_size: int
    note: str
    dishes: list[db.NewDish]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def clean_rsvp(data: Mapping[str, object], category_ids: set[str]) -> CleanRsvp:
    """Validate and normalise submitted RSVP data."""
    name = _text(data.get("name"))
    note = _text(data.get("note"))
    raw_size = data.get("party_size")
    try:
        party_size = int(raw_size) if isinstance(raw_size, int | str) else 1
    except ValueError:
        party_size = 1
    party_size = max(1, min(party_size, MAX_PARTY_SIZE))

    dishes: list[db.NewDish] = []
    raw_dishes = data.get("dishes")
    for raw in raw_dishes if isinstance(raw_dishes, list) else []:
        if not isinstance(raw, dict):
            continue
        category = _text(raw.get("category"))
        if category not in category_ids:
            continue
        dishes.append(db.NewDish(category, _text(raw.get("dish"))[:200]))

    if not name:
        raise InvalidRsvpError("Please add your name.")
    if not dishes:
        raise InvalidRsvpError("Please add at least one dish (just pick a category).")
    return CleanRsvp(name[:80], party_size, note[:300], dishes[:MAX_DISHES])


def resolve_banner(settings: Settings) -> tuple[str, str] | None:
    """Return ('url', url) or ('file', path), or None when there's no banner.

    Resolved on each request so a banner can be dropped in without a restart.
    """
    if settings.banner:
        if settings.banner.startswith(("http://", "https://")):
            return "url", settings.banner
        if Path(settings.banner).is_file():
            return "file", str(Path(settings.banner).resolve())
        return None
    for name in _BANNER_NAMES:
        candidate = settings.data_dir / name
        if candidate.is_file():
            return "file", str(candidate.resolve())
    return None


def create_app(settings: Settings) -> Flask:
    app = Flask(__name__)
    category_ids = {c.id for c in settings.categories}

    def get_db() -> db.Conn:
        if "db" not in g:
            g.db = db.connect(settings.database_url)
        conn: db.Conn = g.db
        return conn

    @app.teardown_appcontext
    def close_db(_exc: BaseException | None) -> None:
        conn: db.Conn | None = g.pop("db", None)
        if conn is not None:
            conn.close()

    def render_page(
        editing: dict[str, object] | None = None, link_error: bool = False
    ) -> str:
        conn = get_db()
        rsvps = db.list_rsvps(conn)
        dishes = db.list_dishes(conn)
        by_id = {r.id: r for r in rsvps}

        # Flatten into per-dish entries, then group those by category.
        grouped: dict[str, list[dict[str, object]]] = {
            c.id: [] for c in settings.categories
        }
        uncategorized: list[dict[str, object]] = []
        for d in dishes:
            host = by_id.get(d.rsvp_id)
            if host is None:
                continue
            entries = grouped.get(d.category)
            if entries is None:
                entries = grouped.get("other", uncategorized)
            entries.append(
                {
                    "rsvp_id": host.id,
                    "name": host.name,
                    "party_size": host.party_size,
                    "note": host.note,
                    "dish": d.dish,
                }
            )

        sections = [
            {**asdict(c), "entries": grouped[c.id], "count": len(grouped[c.id])}
            for c in settings.categories
        ]
        if uncategorized:
            sections.append(
                {
                    **asdict(FALLBACK),
                    "entries": uncategorized,
                    "count": len(uncategorized),
                }
            )

        banner = resolve_banner(settings)
        banner_src = None
        if banner is not None:
            banner_src = banner[1] if banner[0] == "url" else "/banner"

        return render_template(
            "page.html",
            title=settings.title,
            event_date=settings.event_date,
            location=settings.location,
            description=settings.description,
            example_name=settings.example_name,
            github_repo=settings.github_repo,
            banner_src=banner_src,
            categories=settings.categories,
            categories_json=json.dumps([asdict(c) for c in settings.categories]),
            sections=sections,
            rsvp_count=len(rsvps),
            head_count=sum(r.party_size for r in rsvps),
            dish_count=len(dishes),
            editing_json=json.dumps(editing),
            link_error=link_error,
        )

    def json_body() -> dict[str, object]:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}

    @app.get("/healthz")
    def healthz() -> Response:
        return jsonify(status="ok", version=__version__)

    @app.get("/")
    def index() -> str:
        return render_page(link_error=request.args.get("notfound") == "1")

    @app.get("/banner")
    def banner() -> Response:
        """Serve the configured banner image (local files only)."""
        resolved = resolve_banner(settings)
        if resolved is None or resolved[0] != "file":
            abort(404)
        return send_file(resolved[1], max_age=3600)

    @app.get("/r/<token>")
    def edit_link(token: str) -> str | WerkzeugResponse:
        """A guest's personal, bookmarkable RSVP page."""
        conn = get_db()
        row = db.get_rsvp_by_token(conn, token)
        if row is None:
            return redirect(url_for("index", notfound=1))
        editing: dict[str, object] = {
            "id": row.id,
            "token": row.token,
            "name": row.name,
            "party_size": row.party_size,
            "note": row.note,
            "dishes": [
                {"category": d.category, "dish": d.dish}
                for d in db.dishes_for(conn, row.id)
            ],
        }
        return render_page(editing=editing)

    @app.post("/api/rsvp")
    def create_rsvp() -> tuple[Response, int] | Response:
        try:
            data = clean_rsvp(json_body(), category_ids)
        except InvalidRsvpError as e:
            return jsonify(error=str(e)), 400
        token = secrets.token_urlsafe(16)
        rsvp_id = db.create_rsvp(
            get_db(),
            name=data.name,
            party_size=data.party_size,
            note=data.note,
            token=token,
            dishes=data.dishes,
        )
        return jsonify(id=rsvp_id, token=token)

    @app.put("/api/rsvp/<int:rsvp_id>")
    def update_rsvp(rsvp_id: int) -> tuple[Response, int] | Response:
        payload = json_body()
        conn = get_db()
        row = db.get_rsvp(conn, rsvp_id)
        if row is None:
            return jsonify(error="That RSVP no longer exists."), 404
        if payload.get("token") != row.token:
            return jsonify(error="You can only edit your own RSVP."), 403
        try:
            data = clean_rsvp(payload, category_ids)
        except InvalidRsvpError as e:
            return jsonify(error=str(e)), 400
        db.update_rsvp(
            conn,
            rsvp_id,
            name=data.name,
            party_size=data.party_size,
            note=data.note,
            dishes=data.dishes,
        )
        return jsonify(ok=True)

    @app.delete("/api/rsvp/<int:rsvp_id>")
    def delete_rsvp(rsvp_id: int) -> tuple[Response, int] | Response:
        payload = json_body()
        conn = get_db()
        row = db.get_rsvp(conn, rsvp_id)
        if row is None:
            return jsonify(ok=True)  # already gone
        if payload.get("token") != row.token:
            return jsonify(error="You can only remove your own RSVP."), 403
        db.delete_rsvp(conn, rsvp_id)
        return jsonify(ok=True)

    return app
