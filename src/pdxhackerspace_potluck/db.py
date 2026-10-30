"""PostgreSQL access (psycopg 3) and the versioned schema migrations."""

import logging
from dataclasses import dataclass
from datetime import datetime
from importlib import resources

import psycopg
from psycopg.rows import class_row

logger = logging.getLogger(__name__)

Conn = psycopg.Connection[tuple[object, ...]]

# Arbitrary constant: serialises concurrent `migrate` runs.
_MIGRATION_LOCK_ID = 726_001


@dataclass(frozen=True)
class Rsvp:
    id: int
    name: str
    party_size: int
    note: str
    token: str
    created_at: datetime


@dataclass(frozen=True)
class Dish:
    id: int
    rsvp_id: int
    category: str
    dish: str


@dataclass(frozen=True)
class NewDish:
    category: str
    dish: str


def connect(database_url: str) -> Conn:
    return psycopg.connect(database_url, connect_timeout=10)


def migrate(database_url: str) -> list[str]:
    """Apply any migrations not yet applied; return the versions applied."""
    migrations = sorted(
        (
            entry
            for entry in resources.files(__package__).joinpath("migrations").iterdir()
            if entry.name.endswith(".sql")
        ),
        key=lambda entry: entry.name,
    )
    applied: list[str] = []
    with connect(database_url) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        done = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for entry in migrations:
            version = entry.name.removesuffix(".sql")
            if version in done:
                continue
            logger.info("applying migration %s", version)
            conn.execute(entry.read_text(encoding="utf-8").encode())
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
            )
            conn.commit()
            applied.append(version)
        conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))
    return applied


def list_rsvps(conn: Conn) -> list[Rsvp]:
    with conn.cursor(row_factory=class_row(Rsvp)) as cur:
        return cur.execute("SELECT * FROM rsvps ORDER BY created_at, id").fetchall()


def list_dishes(conn: Conn) -> list[Dish]:
    with conn.cursor(row_factory=class_row(Dish)) as cur:
        return cur.execute("SELECT * FROM dishes ORDER BY id").fetchall()


def dishes_for(conn: Conn, rsvp_id: int) -> list[Dish]:
    with conn.cursor(row_factory=class_row(Dish)) as cur:
        return cur.execute(
            "SELECT * FROM dishes WHERE rsvp_id = %s ORDER BY id", (rsvp_id,)
        ).fetchall()


def get_rsvp(conn: Conn, rsvp_id: int) -> Rsvp | None:
    with conn.cursor(row_factory=class_row(Rsvp)) as cur:
        return cur.execute("SELECT * FROM rsvps WHERE id = %s", (rsvp_id,)).fetchone()


def get_rsvp_by_token(conn: Conn, token: str) -> Rsvp | None:
    with conn.cursor(row_factory=class_row(Rsvp)) as cur:
        return cur.execute("SELECT * FROM rsvps WHERE token = %s", (token,)).fetchone()


def _write_dishes(conn: Conn, rsvp_id: int, dishes: list[NewDish]) -> None:
    conn.execute("DELETE FROM dishes WHERE rsvp_id = %s", (rsvp_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO dishes (rsvp_id, category, dish) VALUES (%s, %s, %s)",
            [(rsvp_id, d.category, d.dish) for d in dishes],
        )


def create_rsvp(
    conn: Conn,
    *,
    name: str,
    party_size: int,
    note: str,
    token: str,
    dishes: list[NewDish],
) -> int:
    row = conn.execute(
        "INSERT INTO rsvps (name, party_size, note, token)"
        " VALUES (%s, %s, %s, %s) RETURNING id",
        (name, party_size, note, token),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields a row
        raise RuntimeError("INSERT ... RETURNING returned no row")
    rsvp_id = int(str(row[0]))
    _write_dishes(conn, rsvp_id, dishes)
    conn.commit()
    return rsvp_id


def update_rsvp(
    conn: Conn,
    rsvp_id: int,
    *,
    name: str,
    party_size: int,
    note: str,
    dishes: list[NewDish],
) -> None:
    conn.execute(
        "UPDATE rsvps SET name = %s, party_size = %s, note = %s WHERE id = %s",
        (name, party_size, note, rsvp_id),
    )
    _write_dishes(conn, rsvp_id, dishes)
    conn.commit()


def delete_rsvp(conn: Conn, rsvp_id: int) -> None:
    conn.execute("DELETE FROM rsvps WHERE id = %s", (rsvp_id,))  # dishes cascade
    conn.commit()
