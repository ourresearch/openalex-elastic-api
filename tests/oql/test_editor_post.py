"""The editor routes read a POST body as well as the query string (oxjob #941).

The API refuses a request line over 8,190 bytes, so a long query in the website's OQL
tab failed `GET /validate` and Search silently did nothing. The editor now POSTs
{"q": ...} past that, and `/validate`, `/oql-phrases` and `/parse-context` answer a POST
exactly as they answer the GET. Run:
    PYTHONPATH=. pytest tests/oql/test_editor_post.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401


@pytest.fixture(scope="module")
def client():
    from flask import Flask
    from query_translation.editor_views import blueprint
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    with app.test_client() as c:
        yield c


SHORT = 'get works about ("eye" and "screening" within 5 words of each other) from 2003–2025'
# a systematic-review search: hundreds of proximity pairs, far past what a URL can carry
LONG = "get works from 2003–2025 about (" + " or ".join(
    f'("{a}" and "{b}" within 5 words of each other)'
    for a in ("eye", "eyes", "retina", "retinal", "retinopathy", "macula", "macular")
    for b in ("screen", "screening", "diagnosis", "detection", "test", "testing", "program",
              "programme", "care", "exam", "examination", "checks", "check-up", "surveillance",
              "monitor", "monitoring")
) + ")"


def test_long_query_is_too_long_for_a_url():
    from urllib.parse import quote
    assert len(quote(LONG)) > 8190


@pytest.mark.parametrize("q", [SHORT, LONG])
def test_validate_post_answers_as_get(client, q):
    got = client.get("/validate", query_string={"q": q}).get_json()
    posted = client.post("/validate", json={"q": q}).get_json()
    assert posted == got
    assert posted["valid"] is True and posted["oql"]


def test_validate_post_reports_errors(client):
    bad = client.post("/validate", json={"q": "get the count of works about by author"}).get_json()
    assert bad["valid"] is False and bad["diagnostics"]


def test_validate_post_plain_words(client):
    q = "get works about kelp please show me the newest"
    got = client.get("/validate", query_string={"q": q, "plain_words": "1"}).get_json()
    posted = client.post("/validate", json={"q": q, "plain_words": True}).get_json()
    assert posted == got


def test_validate_post_without_a_usable_body(client):
    # no body, a non-object body, or a non-string q: read as the empty query, never a 500
    empty = client.get("/validate").get_json()
    for kwargs in ({}, {"json": ["get works"]}, {"json": {"q": 5}}, {"data": "not json"}):
        r = client.post("/validate", **kwargs)
        assert r.status_code == 200 and r.get_json() == empty


def test_phrases_post_answers_as_get(client):
    for q in (SHORT, LONG):
        got = client.get("/oql-phrases", query_string={"q": q}).get_json()
        assert client.post("/oql-phrases", json={"q": q}).get_json() == got
    assert client.post("/oql-phrases", json={}).get_json() == {"phrases": []}


def test_parse_context_post_answers_as_get(client):
    for q in (SHORT, LONG):
        pos = len(q) - 1
        got = client.get("/parse-context", query_string={"q": q, "pos": pos}).get_json()
        assert client.post("/parse-context", json={"q": q, "pos": pos}).get_json() == got
