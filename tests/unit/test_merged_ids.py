"""oxjob #1124: merged-away author, source and funder IDs resolve to the winner, in filters and on
the single-record GET. No ES: the merge-index lookup is faked. Run with --noconftest."""
import json
from collections import OrderedDict
from unittest import mock

import pytest
from elasticsearch_dsl import Search

import core.merged_ids as merged_ids
from core.filter import filter_records
from works.fields import fields_dict as works_fields_dict

MERGES = {"A5107411446": "A5107863564", "S4306502279": "S4306502280", "F4320307874": "F4320311904",
          "W4251036366": "W1623399274"}


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
    _body([{"authorships.institutions.id": "I27837315"}])
    _body([{"primary_topic.id": "T10001"}])
    assert es.calls == []


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
