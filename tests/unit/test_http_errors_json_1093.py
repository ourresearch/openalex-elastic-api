"""oxjob #1093 (ZD 5750): Werkzeug's own errors (abort(404) on a missing record, abort(503), a 405) came back as
Werkzeug's HTML page; the docs promise JSON. No ES: the record lookup finds nothing. Run with --noconftest."""
from unittest import mock

import pytest


@pytest.fixture
def app_client(monkeypatch):
    for k, v in {"REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
                 "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
                 "USERS_DB_URL": "postgresql://u:p@localhost:5432/db",
                 "DATABASE_URL": "postgresql://u:p@localhost:5432/db", "JWT_SECRET_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    import ids.views
    monkeypatch.setattr(ids.views, "merged_winner", lambda *a, **k: None)  # no merge lookup (no ES)
    from app import create_app
    app = create_app("tests.settings")
    return app.test_client()


@pytest.mark.parametrize("path, message", [
    ("/works/W9999999999", "Work W9999999999 not found"),
    ("/works/doi:10.9999/doesnotexist.xyz", "Work doi:10.9999/doesnotexist.xyz not found"),
    ("/authors/A9999999999", "Author A9999999999 not found"),
    ("/people/A9999999999", "Author A9999999999 not found"),
    ("/sources/S9999999999", "Source S9999999999 not found"),
    ("/entities/sources/S9999999999", "Source S9999999999 not found"),
])
def test_missing_record_404_is_json(app_client, path, message):
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get(path)
    assert r.status_code == 404, (path, r.status_code)
    assert r.content_type == "application/json", (path, r.content_type)
    assert r.get_json() == {"error": "Not Found", "message": message}
    assert r.headers["Access-Control-Allow-Origin"] == "*"  # after_request hooks still run


def test_405_is_json_and_keeps_allow_header(app_client):
    r = app_client.delete("/works/W9999999999")
    assert r.status_code == 405
    assert r.content_type == "application/json"
    assert r.get_json()["error"] == "Method Not Allowed"
    assert "GET" in r.headers["Allow"]


def test_503_is_json_with_retry_after(app_client):
    from flask import abort
    app = app_client.application

    @app.route("/_test_503")
    def _test_503():
        abort(503)

    r = app_client.get("/_test_503")
    assert r.status_code == 503
    assert r.content_type == "application/json"
    assert r.get_json()["error"] == "Service Unavailable"
    assert r.headers["Retry-After"] == "30"


def test_custom_description_kept(app_client):
    from flask import abort
    app = app_client.application

    @app.route("/_test_404_described")
    def _test_404_described():
        abort(404, description="No such list")

    r = app_client.get("/_test_404_described")
    assert r.get_json() == {"error": "Not Found", "message": "No such list"}


def test_redirects_untouched(app_client, monkeypatch):
    # A merged-away ID still answers its 301 to the winner (oxjob #1124), not a JSON error.
    import ids.views
    monkeypatch.setattr(ids.views, "merged_winner", lambda *a, **k: "W1623399274")
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get("/works/W4251036366")
    assert r.status_code == 301
    assert r.headers["Location"].endswith("/works/W1623399274")


@pytest.mark.parametrize("path, message", [
    ("/v2/works/W1", "Work W1 not found"),
    ("/countries/XX", "Country XX not found"),
    ("/oa-statuses/purple", "OA status purple not found"),
    ("/no-such-thing/x", "Nothing found at /no-such-thing/x"),
    ("/", "Nothing found at /"),
])
def test_not_found_message(path, message):
    from app import not_found_message
    assert not_found_message(path) == message
