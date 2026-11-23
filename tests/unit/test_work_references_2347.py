"""oxjob #2347: GET /works/{id}/references, served from Lakebase. No database: the Lakebase read is mocked.
Run with --noconftest."""
import json
from unittest import mock

import pytest

from works import lakebase

DOC = ('{"references":[{"raw_reference_string":"Cummings JH. Dietary fibre. Br Med Bull. 1981;37:65-70.",'
       '"raw_doi":null,"work_id":"https://openalex.org/W2033283428"}]}')


@pytest.fixture
def app_client(monkeypatch):
    for k, v in {"REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
                 "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
                 "USERS_DB_URL": "postgresql://u:p@localhost:5432/db",
                 "DATABASE_URL": "postgresql://u:p@localhost:5432/db", "JWT_SECRET_KEY": "x",
                 "LAKEBASE_URL": "postgresql://u:p@localhost:5432/db"}.items():
        monkeypatch.setenv(k, v)
    from app import create_app
    return create_app("tests.settings").test_client()


def _get(client, path, found=(True, DOC), winner=None):
    with mock.patch("works.lakebase.get_work_references", return_value=found) as q, \
            mock.patch("ids.views.merged_winner", return_value=winner):
        return client.get(path), q


def test_serves_the_stored_list_verbatim(app_client):
    r, q = _get(app_client, "/works/W2741809807/references")
    assert r.status_code == 200 and r.content_type == "application/json"
    assert r.get_data(as_text=True) == DOC
    q.assert_called_once_with(2741809807)


def test_work_with_no_list_is_empty(app_client):
    r, _ = _get(app_client, "/works/W2741809807/references", found=(True, None))
    assert r.status_code == 200 and r.get_json() == {"references": []}


def test_unknown_work_is_404(app_client):
    r, _ = _get(app_client, "/works/W99999999999/references", found=(False, None))
    assert r.status_code == 404
    assert r.get_json()["message"] == "Work W99999999999 not found"


def test_merged_away_work_redirects_to_the_winner(app_client):
    r, _ = _get(app_client, "/works/W123/references", found=(False, None), winner="W456")
    assert r.status_code == 301 and r.headers["Location"].split("?")[0] in ("/works/W456/references",
                                                                         "http://localhost/works/W456/references")


@pytest.mark.parametrize("path", ["/works/w2741809807/references", "/works/openalex:W2741809807/references",
                                  "/entities/works/w2741809807/references"])
def test_other_spellings_redirect_to_the_canonical_id(app_client, path):
    r, q = _get(app_client, path)
    assert r.status_code == 302 and r.headers["Location"].split("?")[0] in ("/works/W2741809807/references",
                                                                         "http://localhost/works/W2741809807/references")
    q.assert_not_called()


def test_trailing_slash_is_the_same_route(app_client):
    r, _ = _get(app_client, "/works/W2741809807/references/")
    assert r.status_code == 200 and r.get_data(as_text=True) == DOC


@pytest.mark.parametrize("path", ["/works/A5023888391/references", "/works/doi:10.7717/peerj.4375/references"])
def test_non_work_ids_are_404(app_client, path):
    with mock.patch("works.lakebase.get_work_references") as q, \
            mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False), \
            mock.patch("ids.views.redirect_if_merged", return_value=None):
        r = app_client.get(path)
    assert r.status_code == 404
    q.assert_not_called()


def test_the_work_route_still_answers_the_work(app_client):
    with mock.patch("ids.views.works_references_get") as refs, \
            mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False), \
            mock.patch("ids.views.redirect_if_merged", return_value=None):
        r = app_client.get("/works/W2741809807")
    assert r.status_code == 404  # ES mocked empty: the plain work route answered, not the references one
    refs.assert_not_called()


def test_query_reads_both_shards_by_work_id():
    with mock.patch.object(lakebase, "_query_one", return_value=(True, DOC)) as q:
        assert lakebase.get_work_references(7) == (True, DOC)
    sql = q.call_args[0][0]
    assert "lakebase_works_docs_7" in sql and "lakebase_work_references_1" in sql
    assert q.call_args[0][1] == (7,)
