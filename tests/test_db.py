from pdxhackerspace_potluck import db


def test_migrate_is_idempotent(database_url: str) -> None:
    db.migrate(database_url)
    assert db.migrate(database_url) == []


def test_rsvp_round_trip(conn: db.Conn) -> None:
    rsvp_id = db.create_rsvp(
        conn,
        name="Ada",
        party_size=2,
        note="hi",
        token="tok",  # noqa: S106
        dishes=[db.NewDish("meat", "ribs"), db.NewDish("drinks", "")],
    )
    rsvp = db.get_rsvp(conn, rsvp_id)
    assert rsvp is not None
    assert (rsvp.name, rsvp.party_size, rsvp.note) == ("Ada", 2, "hi")
    assert db.get_rsvp_by_token(conn, "tok") == rsvp
    assert [d.dish for d in db.dishes_for(conn, rsvp_id)] == ["ribs", ""]

    db.update_rsvp(
        conn,
        rsvp_id,
        name="Ada L",
        party_size=1,
        note="",
        dishes=[db.NewDish("carbs", "bread")],
    )
    assert [d.category for d in db.list_dishes(conn)] == ["carbs"]
    assert [r.name for r in db.list_rsvps(conn)] == ["Ada L"]

    db.delete_rsvp(conn, rsvp_id)
    assert db.get_rsvp(conn, rsvp_id) is None
    assert db.list_dishes(conn) == []
    assert db.get_rsvp_by_token(conn, "tok") is None
