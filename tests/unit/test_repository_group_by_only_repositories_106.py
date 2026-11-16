"""oxjob #106 (ZD 1148; same defect as #2270): `group_by=repository`, the website's
Repository facet, listed journals.

The works with a repository copy are kept, then a terms agg counts the source id of
EVERY location of those works (`locations_full` is an object array, not nested, so ES
can't tie a location's type to its id). The search's own journals, ebook platforms and
aggregators came back as "repositories": PLoS ONE, Nature, Springer eBooks in the global
top 200 (21 of 200), the journal itself first on S2736485060 (69 works).

Now the agg asks for more groups than the page shows, the bucket keys are looked up in
the sources index with `type:repository` (the same one lookup that already fetched their
names), every other key is dropped, the list is cut back to the page, and
`meta.groups_count` counts the groups served. ES-free: Search.execute is stubbed.
"""
from collections import OrderedDict

import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response

from core.group_by import display_names as display_names_module
from core.group_by.buckets import (REPOSITORY_EXTRA_GROUPS, create_group_by_buckets,
                                   group_list_size)
from core.group_by.display_names import (get_display_name_mapping,
                                         get_display_names_repositories)
from core.group_by.results import (get_group_by_results, get_nested_group_by_results,
                                   outer_group_is_repository, keep_repository_buckets)
from core.group_by.utils import parse_group_by_dimensions
from core.utils import get_field
from works.fields import fields_dict

REPO_TERM = {"term": {"locations_full.source.type": "repository"}}
PARAMS = {"per_page": 200, "cursor": None, "q": None, "sort": None, "group_by": None}

DOAJ = "https://openalex.org/S4306401280"
NORA = "https://openalex.org/S7407064446"
PHILPAPERS = "https://openalex.org/S4306402130"
JOURNAL = "https://openalex.org/S2736485060"      # Indo-Pacific Journal of Phenomenology
PLOS = "https://openalex.org/S202381698"          # a journal
SPRINGER_EBOOKS = "https://openalex.org/S4306463937"  # an ebook platform

REPOSITORY_NAMES = {DOAJ: "DOAJ", NORA: "NORA", PHILPAPERS: "PhilPapers"}
OTHER_SOURCE_NAMES = {JOURNAL: "Indo-Pacific Journal of Phenomenology", PLOS: "PLoS ONE",
                      SPRINGER_EBOOKS: "Springer eBooks"}


class _StubSources:
    """Stands in for the sources index: answers the repository lookup with the
    repositories among the asked ids and records the query it was sent."""

    def __init__(self, repositories):
        self.repositories = repositories
        self.queries = []

    def __call__(self, search, *args, **kwargs):
        body = search.to_dict()
        self.queries.append((search._index, body))
        query = body["query"]["bool"]
        if "filter" in query:   # the repository lookup: ids AND type:repository
            asked = next(c["terms"]["id"] for c in query["filter"] if "terms" in c)
            known = self.repositories
        else:                   # the generic id lookup: any source, any type
            asked = [c["term"]["id"] for c in query["should"]]
            known = {**OTHER_SOURCE_NAMES, **self.repositories}
        hits = [{"_index": "sources", "_id": k, "_score": 1.0,
                 "_source": {"id": k, "display_name": known[k]}}
                for k in asked if k in known]
        raw = {"took": 1, "timed_out": False,
               "hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}}
        return Response(search, raw)


@pytest.fixture
def sources(monkeypatch):
    stub = _StubSources(REPOSITORY_NAMES)

    def execute(search, *args, **kwargs):
        return stub(search)

    monkeypatch.setattr(Search, "execute", execute)
    # no zero-value padding from the group-by values index in these tests
    monkeypatch.setattr("core.group_by.results.get_all_groupby_values", lambda **kw: [])
    return stub


def _agg_response(group_by, keys_counts, search=None):
    search = search or Search()
    buckets = [{"key": k, "doc_count": c} for k, c in keys_counts]
    raw = {"took": 1, "timed_out": False,
           "hits": {"total": {"value": 396, "relation": "eq"}, "hits": []},
           "aggregations": {f"groupby_{group_by.replace('.', '_')}": {"buckets": buckets}}}
    return Response(search, raw)


# --- the agg asks for more than the page ---------------------------------------------

def test_repository_asks_es_for_more_groups_than_the_page():
    s = create_group_by_buckets(fields_dict, "repository", False, Search(), PARAMS)
    d = s.to_dict()
    assert d["query"]["bool"]["filter"] == [REPO_TERM]          # unchanged scope
    assert d["aggs"]["groupby_repository"]["terms"]["size"] == 2 * 200 + REPOSITORY_EXTRA_GROUPS


def test_other_group_bys_keep_their_size():
    for param in ("locations.source.id", "primary_location.source.id", "journal",
                  "authorships.institutions.lineage"):
        s = create_group_by_buckets(fields_dict, param, False, Search(), PARAMS)
        agg = s.to_dict()["aggs"][f"groupby_{param.replace('.', '_')}"]
        assert agg["terms"]["size"] == 200, param


def test_sorted_repository_list_asks_for_more_too():
    params = {**PARAMS, "sort": {"key": "asc"}}
    s = create_group_by_buckets(fields_dict, "repository", False, Search(), params)
    assert s.to_dict()["aggs"]["groupby_repository"]["terms"]["size"] == 500


def test_group_list_size():
    repo = get_field(fields_dict, "repository")
    other = get_field(fields_dict, "locations.source.id")
    assert group_list_size(repo, 10) == 120
    assert group_list_size(other, 10) == 10
    assert group_list_size(repo, None) is None


# --- the lookup keeps only repositories -----------------------------------------------

def test_repository_lookup_asks_the_sources_index_for_type_repository(sources):
    names = get_display_names_repositories([JOURNAL, DOAJ, "unknown", PLOS, NORA])
    assert names == {DOAJ: "DOAJ", NORA: "NORA"}
    index, body = sources.queries[-1]
    assert index == ["sources"]
    assert {"terms": {"id": [JOURNAL, DOAJ, PLOS, NORA]}} in body["query"]["bool"]["filter"]
    assert {"term": {"type": "repository"}} in body["query"]["bool"]["filter"]
    assert body["size"] == 4


def test_repository_lookup_with_nothing_to_look_up(sources):
    assert get_display_names_repositories([]) == {}
    assert get_display_names_repositories(["unknown"]) == {}
    assert sources.queries == []


def test_display_name_mapping_routes_repository_only(sources):
    assert get_display_name_mapping([JOURNAL, DOAJ], "repository") == {DOAJ: "DOAJ"}
    # locations.source.id still names every source, journals included
    names = get_display_name_mapping([JOURNAL, DOAJ], "locations.source.id")
    index, body = sources.queries[-1]
    assert "filter" not in body["query"]["bool"]       # the generic id lookup, no type filter
    assert names == {JOURNAL: "Indo-Pacific Journal of Phenomenology", DOAJ: "DOAJ"}


def test_keep_repository_buckets_only_touches_repository():
    class B(dict):
        __getattr__ = dict.get
    buckets = [B(key=JOURNAL), B(key=DOAJ), B(key="unknown")]
    assert [b.key for b in keep_repository_buckets(buckets, "repository", {DOAJ: "DOAJ"})] == [
        DOAJ, "unknown"]
    assert keep_repository_buckets(buckets, "locations.source.id", {}) == buckets


# --- served results --------------------------------------------------------------------

def test_ticket_example_journal_no_longer_listed_as_repository(sources):
    """#2270's live example: filter=primary_location.source.id:S2736485060&group_by=repository
    answered the journal itself first (69), then DOAJ 13, NORA 8, PhilPapers 5."""
    response = _agg_response("repository", [(JOURNAL, 69), (DOAJ, 13), (NORA, 8),
                                            (PHILPAPERS, 5)])
    results = get_group_by_results("repository", False, PARAMS, "works-v33", fields_dict,
                                   response)
    assert [(r["key"], r["key_display_name"], r["doc_count"]) for r in results] == [
        (DOAJ, "DOAJ", 13), (NORA, "NORA", 8), (PHILPAPERS, "PhilPapers", 5)]


def test_page_is_cut_back_to_per_page_after_the_drop(sources):
    many = {f"https://openalex.org/S{9000 + i}": f"Repo {i}" for i in range(30)}
    sources.repositories = {**REPOSITORY_NAMES, **many}
    keys = [(PLOS, 1000), (SPRINGER_EBOOKS, 900)] + [(k, 500 - i) for i, k in enumerate(many)]
    response = _agg_response("repository", keys)
    params = {**PARAMS, "per_page": 10}
    results = get_group_by_results("repository", False, params, "works-v33", fields_dict,
                                   response)
    assert len(results) == 10
    assert PLOS not in [r["key"] for r in results]
    assert [r["key_display_name"] for r in results] == [f"Repo {i}" for i in range(10)]


def test_q_search_keeps_500_before_the_name_match(sources):
    many = {f"https://openalex.org/S{9000 + i}": f"Repo {i}" for i in range(600)}
    sources.repositories = many
    response = _agg_response("repository", [(k, 1) for k in many])
    params = {**PARAMS, "per_page": 25, "q": "repo"}
    results = get_group_by_results("repository", False, params, "works-v33", fields_dict,
                                   response)
    assert len(results) == 500   # search_group_by_strings_with_q then cuts to per_page


def test_cursor_pages_stay_as_they_were(sources):
    """A cursor walks the keys in id order (journals first), so dropping them served
    empty pages that still carried a next_cursor (live check, 16 Nov 02:30 CT). Cursor
    pages keep every source, each named, as before the fix."""
    response = _agg_response("repository", [(JOURNAL, 69), (DOAJ, 13)])
    params = {**PARAMS, "per_page": 2, "cursor": "*"}
    results = get_group_by_results("repository", False, params, "works-v33", fields_dict,
                                   response)
    assert [(r["key"], r["key_display_name"]) for r in results] == [
        (JOURNAL, "Indo-Pacific Journal of Phenomenology"), (DOAJ, "DOAJ")]


def test_include_unknown_keeps_unknown(sources):
    response = _agg_response("repository", [(JOURNAL, 69), (DOAJ, 13), ("unknown", 2)])
    results = get_group_by_results("repository", True, PARAMS, "works-v33", fields_dict,
                                   response)
    assert [r["key"] for r in results] == [DOAJ, "unknown"]


def test_locations_source_id_still_lists_every_source(sources):
    """The any-location source facet is meant to list journals; only `repository` filters."""
    response = _agg_response("locations.source.id", [(JOURNAL, 69), (DOAJ, 13)])
    results = get_group_by_results("locations.source.id", False, PARAMS, "works-v33",
                                   fields_dict, response)
    assert [r["key"] for r in results] == [JOURNAL, DOAJ]


def test_nested_repository_level_drops_journals(sources):
    dims = parse_group_by_dimensions("repository,publication_year")
    raw = {"took": 1, "timed_out": False,
           "hits": {"total": {"value": 396, "relation": "eq"}, "hits": []},
           "aggregations": {"groupby_repository": {"buckets": [
               {"key": JOURNAL, "doc_count": 69,
                "groupby_publication_year": {"buckets": [{"key": 2008, "doc_count": 32}]}},
               {"key": DOAJ, "doc_count": 13,
                "groupby_publication_year": {"buckets": [{"key": 2010, "doc_count": 13}]}},
           ]}}}
    response = Response(Search(), raw)
    results = get_nested_group_by_results(dims, PARAMS, "works-v33", fields_dict, response)
    assert [r["key"] for r in results] == [DOAJ]
    assert results[0]["groups"][0]["doc_count"] == 13


# --- meta.groups_count -----------------------------------------------------------------

def test_outer_group_is_repository():
    assert outer_group_is_repository("repository")
    assert outer_group_is_repository("repository:include_unknown")
    assert outer_group_is_repository("repository,publication_year")
    assert not outer_group_is_repository("publication_year,repository")
    assert not outer_group_is_repository("locations.source.id")
    assert not outer_group_is_repository(None)


def test_format_response_counts_the_groups_served(sources):
    from flask import Flask

    from core.shared_view import format_response

    response = _agg_response("repository", [(JOURNAL, 69), (DOAJ, 13), (NORA, 8),
                                            (PHILPAPERS, 5)])
    params = {**PARAMS, "group_by": "repository", "group_bys": None, "page": 1,
              "sample": None, "apc_sum": None, "cited_by_count_sum": None}
    with Flask(__name__).app_context():
        result = format_response(response, params, "works-v33", fields_dict, Search())
    assert result["meta"]["groups_count"] == 3
    assert [g["key"] for g in result["group_by"]] == [DOAJ, NORA, PHILPAPERS]
