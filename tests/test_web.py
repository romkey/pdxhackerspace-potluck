from pathlib import Path

import pytest
from flask.testing import FlaskClient

from pdxhackerspace_potluck import __version__, db
from pdxhackerspace_potluck.config import Settings
from pdxhackerspace_potluck.web import (
    InvalidRsvpError,
    clean_rsvp,
    create_app,
    resolve_banner,
)

IDS = {"meat", "other"}
GOOD = {"name": "Ada", "dishes": [{"category": "meat", "dish": "ribs"}]}


@pytest.fixture
def client(settings: Settings, conn: db.Conn) -> FlaskClient:
    del conn  # only to start from an empty database
    return create_app(settings).test_client()


def test_healthz(client: FlaskClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "version": __version__}


def test_unknown_path_is_404(client: FlaskClient) -> None:
    assert client.get("/nope").status_code == 404


def test_clean_rsvp_normalises() -> None:
    clean = clean_rsvp(
        {
            "name": "  Ada ",
            "party_size": "999",
            "note": " n ",
            "dishes": [
                {"category": "meat", "dish": " ribs "},
                {"category": "bogus", "dish": "x"},
                "not a dict",
            ],
        },
        IDS,
    )
    assert (clean.name, clean.party_size, clean.note) == ("Ada", 50, "n")
    assert clean.dishes == [db.NewDish("meat", "ribs")]


@pytest.mark.parametrize("size", ["many", None, 0, -3])
def test_clean_rsvp_party_size_floor(size: object) -> None:
    assert clean_rsvp({**GOOD, "party_size": size}, IDS).party_size == 1


@pytest.mark.parametrize(
    "data",
    [{}, {"name": "Ada"}, {"name": "Ada", "dishes": [{"category": "x"}]}],
)
def test_clean_rsvp_rejects_incomplete(data: dict[str, object]) -> None:
    with pytest.raises(InvalidRsvpError):
        clean_rsvp(data, IDS)


def test_create_rsvp_rejects_bad_input(client: FlaskClient) -> None:
    response = client.post("/api/rsvp", json={"name": ""})
    assert response.status_code == 400
    assert response.get_json() == {"error": "Please add your name."}
    assert client.post("/api/rsvp", data="not json").status_code == 400


def test_full_rsvp_lifecycle(client: FlaskClient) -> None:
    created = client.post(
        "/api/rsvp",
        json={
            "name": "Ada <b>",
            "party_size": 3,
            "dishes": [{"category": "meat", "dish": "ribs"}],
        },
    ).get_json()
    token, rsvp_id = created["token"], created["id"]

    page = client.get("/").get_data(as_text=True)
    assert "ribs" in page
    assert "Ada &lt;b&gt;" in page  # escaped

    edit = client.get(f"/r/{token}").get_data(as_text=True)
    assert '"token": "%s"' % token in edit  # noqa: UP031

    forbidden = client.put(f"/api/rsvp/{rsvp_id}", json={**GOOD, "token": "wrong"})
    assert forbidden.status_code == 403
    updated = client.put(
        f"/api/rsvp/{rsvp_id}",
        json={"name": "Ada", "token": token, "dishes": [{"category": "x"}]},
    )
    assert updated.status_code == 400
    updated = client.put(
        f"/api/rsvp/{rsvp_id}",
        json={
            "name": "Ada",
            "token": token,
            "dishes": [{"category": "drinks", "dish": "tea"}],
        },
    )
    assert updated.get_json() == {"ok": True}
    assert "tea" in client.get("/").get_data(as_text=True)

    assert client.delete(f"/api/rsvp/{rsvp_id}", json={"token": "x"}).status_code == 403
    assert client.delete(f"/api/rsvp/{rsvp_id}", json={"token": token}).get_json() == {
        "ok": True
    }
    assert client.delete(f"/api/rsvp/{rsvp_id}").get_json() == {"ok": True}
    assert client.put(f"/api/rsvp/{rsvp_id}", json=GOOD).status_code == 404


def test_unknown_token_redirects_with_notice(client: FlaskClient) -> None:
    response = client.get("/r/nope")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/?notfound=1")
    assert client.get("/?notfound=1").status_code == 200


def test_dish_in_unknown_category_lands_in_other(
    client: FlaskClient, conn: db.Conn
) -> None:
    db.create_rsvp(
        conn,
        name="Bo",
        party_size=1,
        note="",
        token="t2",  # noqa: S106
        dishes=[db.NewDish("retired-category", "stew")],
    )
    assert "stew" in client.get("/").get_data(as_text=True)


def test_banner_from_data_dir(settings: Settings, client: FlaskClient) -> None:
    assert client.get("/banner").status_code == 404
    (settings.data_dir / "banner.png").write_bytes(b"png")
    assert client.get("/banner").data == b"png"
    assert 'src="/banner"' in client.get("/").get_data(as_text=True)


def test_resolve_banner_options(tmp_path: Path) -> None:
    file = tmp_path / "b.png"
    file.write_bytes(b"x")
    base = Settings(database_url="postgresql://x/y", data_dir=tmp_path / "none")
    assert resolve_banner(base) is None
    url = "https://example.com/b.png"
    assert resolve_banner(Settings(**{**base.__dict__, "banner": url})) == ("url", url)
    by_file = resolve_banner(Settings(**{**base.__dict__, "banner": str(file)}))
    assert by_file == ("file", str(file.resolve()))
    missing = Settings(**{**base.__dict__, "banner": str(tmp_path / "gone.png")})
    assert resolve_banner(missing) is None
