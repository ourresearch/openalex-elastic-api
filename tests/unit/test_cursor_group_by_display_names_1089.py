"""oxjob #1089 (ZD 4172): cursor pages of a group_by must name their keys the same way the
first page does.

#106 (fd0cfcf, 16 Nov 2026) kept `repository` cursor pages listing every source by looking
the keys up as `locations.source.id`. That swap was applied to every group_by with a
cursor, so a subfield, keyword, SDG, license or study-design key went to the generic
OpenAlex-id lookup, which can't route `subfields/1100` and answered 400 ("'subfields/1100'
is not a valid OpenAlex ID."). Live, 16 Nov 12:50 CT:
`/works?filter=title_and_abstract.search:nature&group_by=topics.subfield.id&cursor=*` -> 400,
while the same group_by without a cursor named all 200 groups. Only `repository` swaps now.
ES-free: Search.execute is stubbed.
"""
import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response

from core.group_by.results import get_group_by_results
from works.fields import fields_dict

PARAMS = {"per_page": 200, "cursor": "*", "q": None, "sort": None, "group_by": None}

NAMES = {
    "https://openalex.org/subfields/1100": "General Agricultural and Biological Sciences",
    "https://openalex.org/subfields/1102": "Agronomy and Crop Science",
    "https://openalex.org/keywords/0-0-band": "0-0 band",
    "https://openalex.org/licenses/cc-by": "CC BY",
    "https://openalex.org/S4306401280": "DOAJ",
    "https://openalex.org/S2736485060": "Indo-Pacific Journal of Phenomenology",
}


class _StubIndex:
    """Answers any id lookup from NAMES and records the index each lookup went to."""

    def __init__(self):
        self.indexes = []

    def __call__(self, search, *args, **kwargs):
        body = search.to_dict()
        self.indexes.append(search._index)
        query = body["query"]["bool"]
        if "filter" in query:   # the repository lookup: ids AND type:repository
            asked = next(c["terms"]["id"] for c in query["filter"] if "terms" in c)
            asked = [k for k in asked if k == "https://openalex.org/S4306401280"]
        else:
            asked = [c["term"]["id"] for c in query["should"]]
        hits = [{"_index": "x", "_id": k, "_score": 1.0,
                 "_source": {"id": k, "display_name": NAMES[k]}}
                for k in asked if k in NAMES]
        raw = {"took": 1, "timed_out": False,
               "hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}}
        return Response(search, raw)


@pytest.fixture
def index(monkeypatch):
    stub = _StubIndex()
    monkeypatch.setattr(Search, "execute", lambda search, *a, **k: stub(search))
    monkeypatch.setattr("core.group_by.results.get_all_groupby_values", lambda **kw: [])
    return stub


def _agg_response(group_by, keys_counts):
    buckets = [{"key": k, "doc_count": c} for k, c in keys_counts]
    raw = {"took": 1, "timed_out": False,
           "hits": {"total": {"value": 10, "relation": "eq"}, "hits": []},
           "aggregations": {f"groupby_{group_by.replace('.', '_')}": {"buckets": buckets}}}
    return Response(Search(), raw)


@pytest.mark.parametrize("group_by,keys", [
    ("topics.subfield.id", ["https://openalex.org/subfields/1100",
                            "https://openalex.org/subfields/1102"]),
    ("keywords.id", ["https://openalex.org/keywords/0-0-band"]),
    ("primary_location.license", ["https://openalex.org/licenses/cc-by"]),
])
def test_cursor_page_names_its_keys(index, group_by, keys):
    response = _agg_response(group_by, [(k, 5) for k in keys])
    for cursor in ("*", None):
        params = {**PARAMS, "cursor": cursor}
        results = get_group_by_results(group_by, False, params, "works-v33", fields_dict,
                                       response)
        assert [(r["key"], r["key_display_name"]) for r in results] == [
            (k, NAMES[k]) for k in keys], (group_by, cursor)


def test_repository_cursor_page_still_lists_every_source(index):
    """#106's cursor behaviour is kept: every source, journals included, each named."""
    journal, doaj = "https://openalex.org/S2736485060", "https://openalex.org/S4306401280"
    response = _agg_response("repository", [(journal, 69), (doaj, 13)])
    results = get_group_by_results("repository", False, PARAMS, "works-v33", fields_dict,
                                   response)
    assert [(r["key"], r["key_display_name"]) for r in results] == [
        (journal, NAMES[journal]), (doaj, "DOAJ")]
