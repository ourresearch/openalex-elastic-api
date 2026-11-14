"""Every works door leaves out pieces of other works by default (oxjob #2065, step 2).

Each test captures the Elasticsearch query a request builds (nothing reaches a cluster) and checks
the rule is in it, or not, the same on the REST view and the OQO executor.

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_default_view_everywhere.py -q
"""
import json
from unittest.mock import patch

import pytest
from elasticsearch_dsl import MultiSearch, Search


VISIBLE = {"bool": {"must_not": [{"term": {"is_non_traditional_child": True}}]}}
CORE = {"term": {"is_xpac": "false"}}
EXPANSION = {"term": {"is_xpac": "true"}}


class _Hits:
    total = type("T", (), {"value": 0})()

    def __iter__(self):
        return iter([])


class _Response:
    took = 1
    hits = _Hits()

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0


def _has(body, clause):
    """Whether an ES query body holds `clause` anywhere."""
    return json.dumps(clause, sort_keys=True) in json.dumps(body, sort_keys=True)


def _list_query(client, url):
    """The search a list request (REST view or OQO executor) runs."""
    captured = []

    def fake(s, params):
        captured.append(s.to_dict())
        return _Response()

    with patch("core.shared_view.execute_search", side_effect=fake), \
            patch("query_translation.execution.execute_search", side_effect=fake):
        try:
            client.get(url)
        except Exception:  # noqa: BLE001 the stub response can't always be rendered; the query was built
            pass
    assert captured, url
    return captured[0]


def _any_query(client, url, multi_only=False):
    """Every search a request sends through Search / MultiSearch (filters, stats, autocomplete).
    `multi_only`: just the MultiSearch ones (/works/filters counts; its name lookups go one by one)."""
    captured = []
    multi = []

    def fake_execute(self, *a, **k):
        captured.append(self.to_dict())
        return _Response()

    def fake_count(self, *a, **k):
        captured.append(self.to_dict())
        return 0

    def fake_multi(self, *a, **k):
        multi.extend(s.to_dict() for s in self._searches)
        captured.extend(multi)
        return [_Response() for _ in self._searches]

    with patch.object(Search, "execute", fake_execute), patch.object(Search, "count", fake_count), \
            patch.object(MultiSearch, "execute", fake_multi):
        try:
            client.get(url)
        except Exception:  # noqa: BLE001 the stub response can't be rendered; the query was built
            pass
    assert captured, url
    return multi if multi_only else captured


REST_AND_OQO = [
    ("/works", "/?oql=works"),
    ("/works?filter=type:dataset", "/?oql=works%20where%20type%20is%20dataset"),
    ("/works?search=kelp", "/?oql=works%20where%20full%20text%20has%20kelp"),
    ("/works?group_by=type", "/?oql=works%20group%20by%20type"),
    ("/works?filter=authorships.institutions.lineage:I27837315", "/?oql=works%20where%20institution%20is%20I27837315"),
    ("/works?filter=is_traditional:false", "/?oql=works%20where%20traditional%20scholarly%20work%20is%20false"),
    ("/works?corpus=core", "/?oql=works"),
]


@pytest.mark.parametrize("rest,oqo", REST_AND_OQO)
def test_the_default_view_hides_pieces_on_both_doors(client, rest, oqo):
    for url in (rest, oqo):
        body = _list_query(client, url)
        assert _has(body, CORE), url
        assert _has(body, VISIBLE), url


LIFTED = [
    ("/works?filter=lineage:W3109397498", "/?oql=works%20where%20work%20lineage%20is%20W3109397498"),
    ("/works?filter=lineage:!W3109397498", "/?oql=works%20where%20work%20lineage%20is%20not%20W3109397498"),
    ("/works?filter=parent_works.id:W3109397498|W2741809807",
     "/?oql=works%20where%20parent%20work%20is%20(W3109397498%20or%20W2741809807)"),
    ("/works?filter=has_parent_work:true", "/?oql=works%20where%20has%20parent%20work%20is%20true"),
    ("/works?filter=parent_works.relationship:component&group_by=type",
     "/?oql=works%20where%20relationship%20to%20parent%20work%20is%20component%20group%20by%20type"),
]


@pytest.mark.parametrize("rest,oqo", LIFTED)
def test_a_parent_child_filter_brings_pieces_back_and_keeps_the_corpus(client, rest, oqo):
    for url in (rest, oqo):
        body = _list_query(client, url)
        assert _has(body, CORE), url          # expansion works stay out
        assert not _has(body, VISIBLE), url


def test_corpus_all_applies_nothing_and_expansion_only_its_own(client):
    for url in ("/works?corpus=all", "/works?include_xpac=true"):
        body = _list_query(client, url)
        assert not _has(body, CORE) and not _has(body, VISIBLE), url
    body = _list_query(client, "/works?corpus=expansion")
    assert _has(body, EXPANSION) and not _has(body, VISIBLE)
    body = _list_query(client, "/works?filter=is_xpac:true")
    assert not _has(body, VISIBLE)
    body = _list_query(client, "/works?filter=is_xpac:false")
    assert _has(body, VISIBLE)


def test_oqo_corpus_all_and_expansion(client):
    def run(oqo):
        captured = []

        def fake(s, params):
            captured.append(s.to_dict())
            return _Response()

        with patch("query_translation.execution.execute_search", side_effect=fake):
            try:
                client.post("/", json={"oqo": oqo})
            except Exception:  # noqa: BLE001
                pass
        return captured[0]

    assert not _has(run({"get_rows": "works", "corpus": "all"}), VISIBLE)
    body = run({"get_rows": "works", "corpus": "expansion"})
    assert _has(body, EXPANSION) and not _has(body, VISIBLE)
    body = run({"get_rows": "works", "corpus": "core"})
    assert _has(body, CORE) and _has(body, VISIBLE)
    nested = {"get_rows": "works", "filter_rows": [{"join": "or", "filters": [
        {"column_id": "type", "value": "dataset"}, {"column_id": "lineage", "value": "W3109397498"}]}]}
    body = run(nested)
    assert _has(body, CORE) and not _has(body, VISIBLE)


def test_the_internal_key_is_not_a_filter(client):
    for url in ("/works?filter=_default.hide_pieces:false", "/works?filter=-default.hide-pieces:true",
                "/works/filters/_default.hide_pieces:false", "/autocomplete/works?q=kelp&filter=_default.hide_pieces:false"):
        res = client.get(url)
        assert res.status_code == 400, url
        assert "is not a valid field" in res.get_json()["message"]


def test_v2_works_hides_pieces_too(client):
    assert _has(_list_query(client, "/v2/works"), VISIBLE)
    assert not _has(_list_query(client, "/v2/works?filter=lineage:W3109397498"), VISIBLE)


def test_works_filters_counts_follow_the_default_view(client):
    counts = _any_query(client, "/works/filters/type:dataset|article", multi_only=True)
    assert len(counts) == 3 and all(_has(body, VISIBLE) for body in counts)  # the whole query + each OR value
    counts = _any_query(client, "/works/filters/authorships.institutions.lineage:I27837315", multi_only=True)
    assert counts and all(_has(body, VISIBLE) for body in counts)
    counts = _any_query(client, "/works/filters/parent_works.id:W3109397498", multi_only=True)
    assert counts and not any(_has(body, VISIBLE) for body in counts)


def test_works_stats_follow_the_default_view(client):
    assert all(_has(b, VISIBLE) for b in _any_query(client, "/works/stats/?filter=type:dataset"))
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/works/stats/?filter=has_parent_work:true"))


def test_autocomplete_does_not_suggest_pieces(client):
    assert any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/works?q=handbook"))
    assert any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete?q=handbook%20of%20kelp"))
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/works?q=handbook&filter=lineage:W3109397498"))
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/works?q=handbook&corpus=all"))
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/works?q=handbook&include_xpac=true"))
    # other entities' autocomplete is untouched
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/authors?q=smith"))
    # an id typed as q still finds any work
    assert not any(_has(b, VISIBLE) for b in _any_query(client, "/autocomplete/works?q=W3109397498"))


def test_a_single_work_is_never_filtered(client):
    for body in _any_query(client, "/works/W3109397498"):
        assert not _has(body, VISIBLE)
