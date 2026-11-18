"""oxjob #1124: merged-away author, source and funder IDs resolve to the winner, in filters and on
the single-record GET. No ES: the merge-index lookup is faked. Run with --noconftest."""
import json
from collections import OrderedDict
from unittest import mock

import pytest
from elasticsearch_dsl import Search

import core.merged_ids as merged_ids
from core.filter import filter_records
from awards.fields import fields_dict as awards_fields_dict
from works.fields import fields_dict as works_fields_dict

MERGES = {"A5107411446": "A5107863564", "S4306502279": "S4306502280", "F4320307874": "F4320311904",
          "W4251036366": "W1623399274", "I4210133110": "I166825849", "G5706016782": "G8222464832"}


class FakeES:
    def __init__(self, merges=MERGES, fail=False):
        self.merges, self.fail, self.calls = merges, fail, []

    def search(self, index, body, request_timeout):
        self.calls.append((index, sorted(body["query"]["ids"]["values"])))
        if self.fail:
            raise ConnectionError("es down")
        hits = []
        for url in body["query"]["ids"]["values"]:
            short = url.rsplit("/", 1)[-1]
            if short in self.merges:
                hits.append({"_id": url, "_source": {"merge_into_id": "https://openalex.org/" + self.merges[short]}})
        return {"hits": {"hits": hits}}


def _fresh_state(monkeypatch):
    monkeypatch.setattr(merged_ids, "_cache", OrderedDict())
    monkeypatch.setattr(merged_ids, "_breakers", {i: merged_ids.Breaker(failures=3, window_s=30, open_s=60)
                                                  for i in merged_ids.MERGE_INDEXES.values()})


@pytest.fixture
def es(monkeypatch):
    _fresh_state(monkeypatch)
    fake = FakeES()
    monkeypatch.setattr(merged_ids, "get_connection", lambda *a, **k: fake)
    return fake


def _body(filters):
    return json.dumps(filter_records(works_fields_dict, filters, Search()).to_dict())


def test_author_filter_on_loser_also_matches_winner(es):
    body = _body([{"authorships.author.id": "A5107411446"}])
    # loser kept: works still stamped with it until the nightly re-stamp match too
    assert '"terms"' in body
    assert "https://openalex.org/A5107863564" in body and "https://openalex.org/A5107411446" in body


def test_unmerged_id_stays_a_single_term(es):
    body = _body([{"authorships.author.id": "A5000000001"}])
    assert '"term"' in body and '"terms"' not in body


def test_or_list_adds_winners_in_one_lookup(es):
    body = _body([{"authorships.author.id": "A5107411446|A5000000001"}])
    for a in ("A5107863564", "A5000000001", "A5107411446"):
        assert f"https://openalex.org/{a}" in body
    assert len(es.calls) == 1


def test_negated_loser_excludes_winner_too(es):
    body = _body([{"authorships.author.id": "!A5107411446"}])
    assert "must_not" in body and "https://openalex.org/A5107863564" in body


def test_and_list_and_negated_or_cost_one_lookup(es):
    _body([{"authorships.author.id": "A5107411446 A5000000001"}])
    _body([{"authorships.author.id": "!A5000000002|A5000000003|A5000000004"}])
    assert len(es.calls) == 2  # one per request (the prefetch), not one per value


def test_source_filters_including_journal_and_repository(es):
    for param in ("primary_location.source.id", "locations.source.id", "journal", "repository"):
        body = _body([{param: "S4306502279"}])
        assert "https://openalex.org/S4306502280" in body, param


def test_funder_filter(es):
    body = _body([{"funders.id": "F4320307874"}])
    assert "https://openalex.org/F4320311904" in body


def test_other_entity_ids_never_looked_up(es):
    _body([{"primary_topic.id": "T10001"}])
    assert es.calls == []


def test_institution_filter_on_loser_also_matches_winner(es):
    # #1037 (ZD 4322, 23578): merged institution IDs, same best effort as works, authors and sources
    body = _body([{"authorships.institutions.id": "I4210133110"}])
    assert "https://openalex.org/I166825849" in body and "https://openalex.org/I4210133110" in body
    assert es.calls == [("merge-institutions", ["https://openalex.org/I4210133110"])]


def test_award_filters_on_loser_also_match_winner(es):
    # an NIH year record folded into its project (G5706016782 -> G8222464832, R01CA148791): GET /awards/<loser> already
    # 301s from merge-awards; works' awards.id and the awards `id` filter answered 0 for the old ID
    body = _body([{"awards.id": "G5706016782"}])
    assert "https://openalex.org/G8222464832" in body and "https://openalex.org/G5706016782" in body
    assert es.calls == [("merge-awards", ["https://openalex.org/G5706016782"])]
    for value in ("G5706016782", "https://openalex.org/G5706016782", "G5706016782|G1000"):
        body = json.dumps(filter_records(awards_fields_dict, [{"id": value}], Search()).to_dict())
        assert "https://openalex.org/G8222464832" in body and "https://openalex.org/G5706016782" in body, value
    body = json.dumps(filter_records(awards_fields_dict, [{"id": "!G5706016782"}], Search()).to_dict())
    assert "must_not" in body and "https://openalex.org/G8222464832" in body
    body = json.dumps(filter_records(awards_fields_dict, [{"id": "G1000"}], Search()).to_dict())
    assert body.count("https://openalex.org/G") == 1  # never merged: the one term, as before
    # a negated OR resolves its IDs one by one: the request's one prefetch covers them (one lookup, not one per ID)
    merged_ids._cache.clear()
    es.calls.clear()
    filter_records(awards_fields_dict, [{"id": "!G5706016782|G1000|G1001"}], Search())
    assert len(es.calls) == 1
    # the same field class on works: a merged institution, as authorships.institutions.id already does (#1037)
    assert "https://openalex.org/I166825849" in _body([{"authorships.affiliations.institution_ids": "I4210133110"}])


def test_work_id_filters_also_match_the_winner(es):
    for param in ("openalex_id", "ids.openalex", "cites"):
        body = _body([{param: "W4251036366"}])
        assert "https://openalex.org/W1623399274" in body, param
    body = _body([{"openalex_id": "W4251036366|W2741809807"}])
    assert "https://openalex.org/W1623399274" in body and "https://openalex.org/W2741809807" in body
    assert es.calls[-1] == ("merge-works", ["https://openalex.org/W2741809807"])  # the merged one is cached


def test_cited_by_on_a_merged_work_reads_the_winner(es):
    seen = []

    def fake_execute(self):
        seen.append(self.to_dict())
        return []
    with mock.patch("elasticsearch_dsl.Search.execute", fake_execute):
        _body([{"cited_by": "W4251036366"}])
    assert "https://openalex.org/W1623399274" in json.dumps(seen)


def test_cache_answers_repeat_lookups(es):
    _body([{"authorships.author.id": "A5107411446"}])
    _body([{"authorships.author.id": "A5107411446"}])
    _body([{"authorships.author.id": "A5000000001"}])
    _body([{"authorships.author.id": "A5000000001"}])
    assert len(es.calls) == 2


def test_lookup_failure_serves_ids_as_given(monkeypatch):
    _fresh_state(monkeypatch)
    fake = FakeES(fail=True)
    monkeypatch.setattr(merged_ids, "get_connection", lambda *a, **k: fake)
    bodies = [_body([{"authorships.author.id": "A5107411446"}]) for _ in range(5)]
    assert all("A5107863564" not in b and "https://openalex.org/A5107411446" in b for b in bodies)
    assert len(fake.calls) == 3  # the breaker opens after 3 failures


def test_long_lists_skip_the_lookup(es):
    ids = "|".join(f"A{5000000000 + i}" for i in range(merged_ids.MAX_LOOKUP_IDS + 1))
    field = works_fields_dict["authorships.author.id"]
    field.build_terms_query(ids.split("|"))
    assert es.calls == []


def test_merged_winner_direct(es):
    assert merged_ids.merged_winner("A5107411446") == "A5107863564"
    assert merged_ids.merged_winner("F4320307874") == "F4320311904"
    assert merged_ids.merged_winner("A5000000001") is None
    assert merged_ids.merged_winner("W2741809807") is None


@pytest.fixture
def app_client(monkeypatch):
    for k, v in {"REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
                 "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
                 "USERS_DB_URL": "postgresql://u:p@localhost:5432/db",
                 "DATABASE_URL": "postgresql://u:p@localhost:5432/db", "JWT_SECRET_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    from app import create_app
    app = create_app("tests.settings")
    return app.test_client()


@pytest.mark.parametrize("path,location", [
    ("/authors/A5107411446?select=id", "/authors/A5107863564?select=id"),
    ("/people/A5107411446", "/authors/A5107863564"),
    ("/sources/S4306502279", "/sources/S4306502280"),
    ("/funders/F4320307874", "/funders/F4320311904"),
    ("/works/W4251036366?select=id", "/works/W1623399274?select=id"),
])
def test_get_on_loser_redirects_301(es, app_client, path, location):
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get(path)
    assert r.status_code == 301
    assert r.headers["Location"].endswith(location)


def test_get_on_merged_institution_redirects_301(es, app_client):
    # the institutions view reads response.hits, so the fake response needs that attribute
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=mock.Mock(hits=[])):
        r = app_client.get("/institutions/I4210133110?select=id")
        assert r.status_code == 301
        assert r.headers["Location"].endswith("/institutions/I166825849?select=id")
        assert app_client.get("/institutions/I1000").status_code == 404
        assert app_client.get("/institutions/ror:00000000").status_code == 404
    assert ("merge-institutions", ["https://openalex.org/I1000"]) in es.calls
    assert all("ror" not in str(c) for c in es.calls)


def test_get_on_unmerged_missing_id_is_404(es, app_client):
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False):
        assert app_client.get("/works/W2741809807").status_code == 404
        assert app_client.get("/authors/A5000000001").status_code == 404
        assert app_client.get("/sources/S1").status_code == 404


@pytest.mark.parametrize("path", [
    # oxjob #1907: the two requests Sentry OPENALEX-ELASTIC-API-2B caught (HTTP 500, UnboundLocalError 'clean_id').
    # With its pmid: prefix cut off, an Elsevier article number reads like a source id.
    "/works/pmid:S0016-5085(16)00131-1",
    "/works/pmid:S0034-75072004000300002",
    "/works/pmid:A99999999999",
    "/works/pmcid:S123456",
    "/works/pmcid:W99999999999",
    "/works/doi:10.0000/none-such",
    "/authors/orcid:0000-0002-1825-0097",
    "/authors/scopus:7004212771",
    "/sources/issn:0000-0000",
    "/sources/issn_l:0000-0000",
    "/funders/ror:02mhbdp94",
    "/funders/doi:10.13039/100000001",
    "/funders/crossref:100000001",
])
def test_get_on_missing_external_id_is_404_without_merge_lookup(es, app_client, path):
    with mock.patch("elasticsearch_dsl.Search.execute", return_value=[]), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get(path)
    assert r.status_code == 404, (path, r.status_code)
    assert es.calls == []  # only an OpenAlex id the request asked for is looked up in the merge indexes


# oxjob #1975 (IDfuse, ZD 26415): a list response names, in meta.merged_ids, each merged-away ID its filters read as
# the winner, so a batched lookup can map every record back to the ID it asked for.

URL = "https://openalex.org/"


def _noted(filters, fields=works_fields_dict):
    from flask import Flask
    with Flask(__name__).test_request_context():
        filter_records(fields, filters, Search())
        return merged_ids.resolved_in_request()


def test_meta_pairs_name_each_loser_once_in_order(es):
    pairs = _noted([{"authorships.author.id": "A5107411446|A5000000001"},
                    {"primary_location.source.id": "s4306502279"},
                    {"authorships.author.id": "A5107411446"}])
    assert pairs == [{"id": URL + "A5107411446", "merge_into_id": URL + "A5107863564"},
                     {"id": URL + "S4306502279", "merge_into_id": URL + "S4306502280"}]


def test_meta_pairs_empty_when_nothing_merged(es):
    assert _noted([{"authorships.author.id": "A5000000001|A5000000002"}]) == []


def test_meta_pairs_cover_negated_and_cited_by(es):
    assert _noted([{"authorships.author.id": "!A5107411446"}]) == [
        {"id": URL + "A5107411446", "merge_into_id": URL + "A5107863564"}]
    with mock.patch("elasticsearch_dsl.Search.execute", lambda self: []):
        assert _noted([{"cited_by": "W4251036366"}]) == [
            {"id": URL + "W4251036366", "merge_into_id": URL + "W1623399274"}]


def test_meta_pairs_skip_long_lists_that_are_not_resolved(es):
    # only a collection's member list can be this long (a URL filter stops at MAX_IDS_IN_FILTER)
    from flask import Flask
    ids = [f"A{5000000000 + i}" for i in range(merged_ids.MAX_LOOKUP_IDS)] + ["A5107411446"]
    with Flask(__name__).test_request_context():
        works_fields_dict["authorships.author.id"].build_terms_query(ids)
        assert merged_ids.resolved_in_request() == []


def test_meta_pairs_outside_a_request_do_nothing(es):
    _body([{"authorships.author.id": "A5107411446"}])
    assert merged_ids.resolved_in_request() == []


def _fake_list_execute(self):
    from elasticsearch_dsl.response import Response
    hits = [{"_index": "authors", "_id": URL + "A5107863564", "_score": 1.0,
             "_source": {"id": URL + "A5107863564", "display_name": "Sonia Luquín"}}]
    return Response(self, {"took": 3, "timed_out": False,
                           "hits": {"total": {"value": 1, "relation": "eq"}, "max_score": 1.0, "hits": hits}})


@pytest.mark.parametrize("path", [
    "/authors?filter=openalex_id:A5107411446|A5000000001",
    "/authors?filter=ids.openalex:a5107411446|A5000000001&select=id,display_name",
    "/works?filter=authorships.author.id:https://openalex.org/A5107411446",
])
def test_list_response_names_the_merged_id_it_read(es, app_client, path):
    with mock.patch("elasticsearch_dsl.Search.execute", _fake_list_execute), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get(path)
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    assert r.json["meta"]["merged_ids"] == [{"id": URL + "A5107411446", "merge_into_id": URL + "A5107863564"}]


def test_list_response_without_merged_ids_has_no_key(es, app_client):
    with mock.patch("elasticsearch_dsl.Search.execute", _fake_list_execute), \
            mock.patch("works.lakebase.should_route", return_value=False):
        r = app_client.get("/authors?filter=openalex_id:A5107863564|A5000000001")
        r2 = app_client.get("/authors?filter=openalex_id:A5107411446")
        r3 = app_client.get("/authors?filter=openalex_id:A5107863564")
    assert r.status_code == 200 and "merged_ids" not in r.json["meta"]
    assert r2.json["meta"]["merged_ids"][0]["id"] == URL + "A5107411446"
    assert "merged_ids" not in r3.json["meta"]  # nothing carries over from the previous request
