"""A cursor walk ends on its last page (oxjob #1029, ZD 2081 / 4314 / 4563).

A page that came back exactly full used to hand out a next_cursor, so a walk whose count is a multiple of per-page
(4 works at per-page 2; 40 at per_page 20) made one more call for an empty page. A cursor page now asks Elasticsearch
for one hit more than it shows: the extra hit only says whether anything follows, and is dropped before formatting."""
import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response

from core.cursor import MORE_AFTER_PAGE, drop_peeked_hit, get_cursor, get_next_cursor, peek_one_more
from core.shared_view import execute_search


def _hits(n):
    return [{"_index": "works", "_id": f"W{i}", "_source": {"id": f"https://openalex.org/W{i}"},
             "sort": [i, f"https://openalex.org/W{i}"]} for i in range(1, n + 1)]


def _response(n, total=None):
    return Response(Search(), {"took": 1, "timed_out": False,
                               "hits": {"total": {"value": total if total is not None else n, "relation": "eq"},
                                        "hits": _hits(n)}})


def _params(cursor="*", per_page=2, **kw):
    return {"cursor": cursor, "per_page": per_page, "page": 1, "group_by": None, "sample": None, **kw}


@pytest.mark.parametrize("params, peek", [
    (_params("*"), 1),
    (_params("IlsxLCAnVzEnXSI="), 1),
    (_params(None), 0),                       # page paging: page and per_page say where the end is
    (_params("*", group_by="type"), 0),       # group-by pages with the aggregation's after_key
    (_params("*", sample=2), 0),              # a sample's hits carry no sort values (oxjob #2003)
])
def test_only_plain_cursor_pages_look_ahead(params, peek):
    assert peek_one_more(params) == peek


def test_a_full_page_with_more_behind_it_keeps_its_cursor_and_drops_the_extra_hit():
    r = drop_peeked_hit(_response(3, total=4), per_page=2)
    assert [h.id for h in r] == ["https://openalex.org/W1", "https://openalex.org/W2"]
    assert len(r.hits) == 2 and r.hits.total.value == 4
    assert get_cursor(r, 2) == [2, "https://openalex.org/W2"]
    assert MORE_AFTER_PAGE not in r._d_  # the flag stays out of the hit data


def test_a_full_last_page_ends_the_walk():
    r = drop_peeked_hit(_response(2, total=4), per_page=2)
    assert len(r.hits) == 2
    assert get_cursor(r, 2) is None
    assert get_next_cursor(_params("IlsxLCAnVzEnXSI="), r) is None


def test_a_timed_out_full_page_keeps_its_cursor():
    # the 5 s soft timeout can return fewer hits than asked: that is not proof the walk is over
    r = _response(2, total=4)
    r._d_["timed_out"] = True
    drop_peeked_hit(r, per_page=2)
    assert get_cursor(r, 2) == [2, "https://openalex.org/W2"]


def test_a_short_last_page_still_ends_the_walk():
    r = drop_peeked_hit(_response(1, total=3), per_page=2)
    assert get_cursor(r, 2) is None


def test_a_response_that_never_looked_ahead_keeps_the_old_rule():
    # e.g. a test double, or a path that calls get_cursor without execute_search
    assert get_cursor(_response(2), 2) == [2, "https://openalex.org/W2"]
    assert get_cursor(_response(1), 2) is None
    assert get_cursor({"hits": {"hits": _hits(2)}}, 2) == [2, "https://openalex.org/W2"]


class _FakeES:
    """Stands in for Search.execute: answers from a corpus of `total` sorted hits, honouring size and search_after."""

    def __init__(self, total):
        self.total, self.sizes = total, []

    def __call__(self, search, *a, **kw):
        body = search.to_dict()
        size = body.get("size", 10)
        self.sizes.append(size)
        after = (body.get("search_after") or [0])[0]
        hits = [h for h in _hits(self.total) if h["sort"][0] > after][:size]
        return Response(search, {"took": 1, "timed_out": False,
                                 "hits": {"total": {"value": self.total, "relation": "eq"}, "hits": hits}})


@pytest.mark.parametrize("total, per_page, pages", [
    (4, 2, [2, 2]),        # ZD 4314 example B: two calls, not three
    (4, 10, [4]),          # ZD 4314 example A
    (40, 20, [20, 20]),    # ZD 5327's search today at per_page 20
    (40, 15, [15, 15, 10]),
    (0, 25, [0]),
    (1, 1, [1]),
])
def test_a_walk_makes_no_call_for_an_empty_page(monkeypatch, total, per_page, pages):
    from core.cursor import handle_cursor
    es = _FakeES(total)
    monkeypatch.setattr(Search, "execute", lambda search, *a, **kw: es(search))
    cursor, seen, sizes = "*", [], []
    for _ in range(10):
        params = _params(cursor, per_page)
        s = handle_cursor(cursor, 1, Search().sort("id"))
        r = execute_search(s, params)
        sizes.append(len(r.hits))
        seen += [h.id for h in r]
        cursor = get_next_cursor(params, r)
        if cursor is None:
            break
    assert sizes == pages
    assert seen == [f"https://openalex.org/W{i}" for i in range(1, total + 1)]
    assert es.sizes == [per_page + 1] * len(pages)


def test_page_paging_asks_for_exactly_its_page(monkeypatch):
    es = _FakeES(30)
    monkeypatch.setattr(Search, "execute", lambda search, *a, **kw: es(search))
    r = execute_search(Search().sort("id"), _params(None, per_page=10, page=2))
    assert es.sizes == [10] and len(r.hits) == 10 and not hasattr(r, MORE_AFTER_PAGE)


def _group_response(n_buckets, after=True, timed_out=False):
    from elasticsearch_dsl import A
    s = Search()
    s.aggs.bucket("groupby_type", A("composite", sources=[{"sub_key": {"terms": {"field": "type"}}}], size=2))
    buckets = [{"key": {"sub_key": f"k{i}"}, "doc_count": 1} for i in range(1, n_buckets + 1)]
    agg = {"buckets": buckets}
    if after and buckets:
        agg["after_key"] = {"sub_key": f"k{n_buckets}"}
    return Response(s, {"took": 1, "timed_out": timed_out,
                        "hits": {"total": {"value": 9, "relation": "eq"}, "hits": []},
                        "aggregations": {"groupby_type": agg}})


@pytest.mark.parametrize("n, timed_out, expected", [
    (2, False, "k2"),     # a full page: more may follow
    (1, False, None),     # a short page: ES still sends an after_key, but nothing follows (ZD 6229's walk, page 635)
    (1, True, "k1"),      # cut short by the soft timeout: keep walking
    (0, False, None),     # the empty page old walks ended on
])
def test_group_by_walk_ends_on_its_short_last_page(n, timed_out, expected):
    from core.cursor import get_group_by_after_key
    r = _group_response(n, timed_out=timed_out)
    assert get_group_by_after_key("type", r, per_page=2) == expected
    params = {"cursor": "*", "per_page": 2, "group_by": "type"}
    assert (get_next_cursor(params, r) is None) == (expected is None)


def test_group_by_without_a_page_size_keeps_the_old_rule():
    from core.cursor import get_group_by_after_key
    assert get_group_by_after_key("type", _group_response(1)) == "k1"
