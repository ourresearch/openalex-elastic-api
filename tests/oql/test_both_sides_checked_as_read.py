"""One split by a group's own record where both sides are too big to list (oxjob #1598, 2026-10-30): `get the count
of works in [Nature](S137773608) by author at [University College London](I45129253)` (147,180 UCL authors, 424,449
authors in Nature's works; listing either took 6-16 s) answered `query_too_slow`. Now its groups are checked against
their own records as they are read: the page view checks the works' groups in its order a list at a time and
estimates the total from a sample; a cursor page walks the smaller side range by range (the own side's ids from its
own index, or the works' groups checked as read). The fake ES is test_nested_pages.FakeES plus a fake own index; the
live checks against production (page views and cursor walks == every passing group, counted exactly) are in the
job's EXPLORE.md, section 13."""
from collections import Counter
from dataclasses import replace

import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either
from tests.oql.test_nested_pages import WORKS, FakeES, _a, _setup

SINGLE = "get the count of all works by author at [University College London](I45129253)"
NESTED = "get the count of all works by author at [University College London](I45129253) and year"
OWN = {_a(1), _a(2), _a(4), _a(9), _a(11), _a(13), _a(20), _a(21)}   # pass their own record; A0020-21 hold no works


class OwnES(FakeES):
    """FakeES plus the authors' own index: a sorted id listing (search_after), a random sample, an id check. `own`:
    the authors whose own record passes."""

    def __init__(self, works, own=OWN, **kw):
        super().__init__(works, **kw)
        self.own = own

    def search(self, index, connection, body, deadline, what, **params):
        if index == "works":
            return super().search(index, connection, body, deadline, what, **params)
        self.calls.append(("own", body))
        own = self.own
        q = body["query"]
        if "function_score" in q:
            ids = sorted(own)[:body["size"]]
        elif body.get("sort"):
            after = (body.get("search_after") or [None])[0]
            ids = [k for k in sorted(own) if after is None or k > after][:body["size"]]
        else:
            asked = next(f["terms"]["id"] for f in q["bool"]["filter"] if "terms" in f)
            ids = [k for k in asked if k in own]
        return {"hits": {"total": {"value": len(own)},
                         "hits": [{"_source": {"id": k}, "fields": {"id": [k]}} for k in ids]}}


def _both_sides_big(monkeypatch, n_own, n_keys, n_works=450_000, works_side_limit=1):
    """Neither side listable: the own-field count and the works' group count are past their limits (with a higher
    `works_side_limit`, the works' groups are listed and checked instead)."""
    import core.join_resolver as J
    monkeypatch.setattr(A, "LOOKUP_LIMIT", 1)
    monkeypatch.setattr(A, "WORKS_SIDE_LIMIT", works_side_limit)
    monkeypatch.setattr(A, "_count_entity_matches", lambda *a, **k: n_own)
    monkeypatch.setattr(A, "_works_side", lambda *a, **k: (n_works, n_keys))
    monkeypatch.setattr(J, "resolve_query_ids", lambda *a, **k: None)


def _truth(own=OWN):
    """Every passing group, count desc then key asc."""
    counts = Counter(a for au, _ in WORKS for a in set(au) if a in own)
    return sorted(counts.items(), key=lambda kc: (-kc[1], kc[0]))


def _run(monkeypatch, fake, oql=SINGLE, min_works=0, **kw):
    fields_dict = _setup(monkeypatch, fake, min_works)
    return A.run(parse_either(oql) if isinstance(oql, str) else oql, index_name="works", connection=None,
                 fields_dict=fields_dict, base_query={"match_all": {}}, **kw)


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
@pytest.mark.parametrize("first,most", [(2_000, 20_000), (1, 3), (2, 5)])
def test_the_page_view_holds_the_first_passing_groups_in_order(monkeypatch, per_page, first, most):
    monkeypatch.setattr(A, "OWN_CANDIDATES_FIRST", first)
    monkeypatch.setattr(A, "OWN_CANDIDATES_MAX", most)
    truth = _truth()
    for page in range(1, -(-len(truth) // per_page) + 1):
        _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
        try:
            body = _run(monkeypatch, OwnES(WORKS), per_page=per_page, page=page)
        except A.AnalyticsError as e:
            # a page past the groups the list found in time says so (the list stops at `most` groups)
            assert e.code == "page_too_deep" and most < 13
            break
        rows = [(g["key"], g["count"]) for g in body["group_by"]]
        want = truth[(page - 1) * per_page:page * per_page]
        # each row is the true row at its place; a page runs short only where the list stopped (`most`)
        assert rows and rows == want[:len(rows)] and (len(rows) == len(want) or most < 13)
        m = body["meta"]
        assert m["groups_count"] == len(truth)     # the sample (here every passing author) and the works holding it
        assert m["more_groups"] == (page * per_page < len(truth) or most < 13)


def test_the_page_view_reads_only_the_works_of_its_groups_and_counts_every_work(monkeypatch):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    fake = OwnES(WORKS)
    body = _run(monkeypatch, fake, per_page=2)
    assert body["summary"]["all"]["count"] == len(WORKS)
    main = [c[1] for c in fake.calls if c[0] == "search" and "pushed" in (c[1].get("aggs") or {})]
    assert main and main[-1]["aggs"]["pushed"]["filter"]["bool"]["filter"][0]["terms"]


def test_a_sort_by_key_reads_the_works_groups_in_key_order(monkeypatch):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    body = _run(monkeypatch, OwnES(WORKS), per_page=3, sort=("key", "asc"))
    assert [g["key"] for g in body["group_by"]] == sorted(k for k, _ in _truth())[:3]


def test_a_sort_by_a_calculation_is_refused_with_its_reason(monkeypatch):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    oql = ("get the count and mean FWCI of all works by author at [University College London](I45129253), "
           "highest mean FWCI first")
    with pytest.raises(A.AnalyticsError) as e:
        _run(monkeypatch, OwnES(WORKS), oql=oql, per_page=3, sort=("mean_fwci", "desc"))
    assert e.value.code == "query_too_slow" and "This sort needs every group's numbers" in e.value.message


def _walk(monkeypatch, fake, per_page):
    oqo = parse_either(SINGLE)
    cursor, rows, pages = "*", [], 0
    while cursor and pages < 200:
        body = _run(monkeypatch, fake, oql=replace(oqo, cursor=cursor), per_page=per_page)
        rows += [(g["key"], g["count"]) for g in body["group_by"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
    return rows


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
@pytest.mark.parametrize("chunk", [1, 2, 100])
def test_a_cursor_walks_the_own_side_when_it_is_smaller(monkeypatch, per_page, chunk):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=10 ** 6)
    monkeypatch.setattr(A, "KEYSET_CHUNK", chunk)
    fake = OwnES(WORKS)
    assert _walk(monkeypatch, fake, per_page) == sorted(_truth())
    # its keys come from the own index in key order, never the works' index-wide term list
    assert not any(c[0] == "terms_enum" for c in fake.calls)
    assert any(c[0] == "own" and c[1].get("sort") for c in fake.calls)


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
def test_a_cursor_checks_the_works_groups_as_read_when_they_are_fewer(monkeypatch, per_page):
    _both_sides_big(monkeypatch, n_own=10 ** 6, n_keys=13)
    fake = OwnES(WORKS, index_terms={_a(n) for n in range(1, 30)})
    assert _walk(monkeypatch, fake, per_page) == sorted(_truth())
    assert not any(c[0] == "own" and c[1].get("sort") for c in fake.calls)   # the own side is never listed


def test_an_inner_split_keeps_the_refusal_and_says_one_split_pages(monkeypatch):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    oql = "get the count of all works by year and author at [University College London](I45129253)"
    with pytest.raises(A.AnalyticsError) as e:
        _run(monkeypatch, OwnES(WORKS), oql=oql, per_page=3)
    assert e.value.code == "query_too_slow" and "make it the only split" in e.value.fix


def _nested_truth(own=OWN):
    """Every passing author's years in the page's order (most works first, years oldest first)."""
    from tests.oql.test_nested_pages import _whole_answer
    return [r for r in _whole_answer(WORKS) if r[0] in own]


@pytest.mark.parametrize("per_page", [1, 2, 3, 5, 100])
def test_a_nested_split_led_by_it_shows_its_first_rows(monkeypatch, per_page):
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    body = _run(monkeypatch, OwnES(WORKS), oql=NESTED, per_page=per_page)
    from tests.oql.test_nested_pages import _leaves, _norm
    truth = _nested_truth()
    assert _norm(_leaves(body["group_by"])) == truth[:per_page]
    m = body["meta"]
    assert m["more_groups"] is True
    assert m["groups_count"] == len({a for a, _, _ in truth})   # the sample: every passing author here
    assert m["rows_count"] == len(truth)                         # their rows, from the same sample


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
@pytest.mark.parametrize("n_own,n_keys", [(8, 10 ** 6), (10 ** 6, 13)])
@pytest.mark.parametrize("fill", [60_000, 3, 2])
def test_a_nested_cursor_led_by_it_walks_every_passing_row(monkeypatch, per_page, n_own, n_keys, fill):
    # fill 3: a range's inner lists are cut, so each cut key is read alone; fill 2: a key holds more years than one
    # request lists, so the range is read by composite pages
    from tests.oql.test_nested_pages import _walk as nested_walk
    _both_sides_big(monkeypatch, n_own=n_own, n_keys=n_keys)
    monkeypatch.setattr(A, "KEYSET_CHUNK", 2)
    monkeypatch.setattr(A, "NESTED_FILL_BUCKETS", fill)
    fake = OwnES(WORKS, index_terms={_a(n) for n in range(1, 30)})
    rows, _ = nested_walk(monkeypatch, fake, oql=NESTED, per_page=per_page)
    assert [(a, str(y), n) for a, y, n in rows] == sorted(_nested_truth())
    reads = [c[1]["aggs"]["s0"] for c in fake.calls if c[0] == "search" and "s0" in (c[1].get("aggs") or {})]
    if n_own < n_keys:   # the own side walked: its ranges read by terms, unless a key overflows one request
        assert any("terms" in r for r in reads)
        assert any("composite" in r for r in reads) == (fill == 2)


def test_another_listed_part_is_checked_against_the_big_one(monkeypatch):
    # at UCL and one of a listed few: the listed authors are checked against UCL, no paging needed
    from query_translation.oqo import BranchFilter, LeafFilter
    _both_sides_big(monkeypatch, n_own=len(OWN), n_keys=13)
    oqo = parse_either(SINGLE)
    listed = BranchFilter("or", [LeafFilter(column_id="ids.openalex", value=_a(n).split("/")[-1]) for n in (1, 3, 9)])
    g = oqo.group_by[0]
    oqo = replace(oqo, group_by=[replace(g, where=BranchFilter("and", [g.where, listed]))])
    body = _run(monkeypatch, OwnES(WORKS), oql=oqo, per_page=100)
    assert sorted(g["key"] for g in body["group_by"]) == [_a(1), _a(9)]


def _check(monkeypatch, oql, n_own, n_keys):
    from works.fields import fields_dict
    monkeypatch.setattr(A, "_probe", lambda levels, *a, **k: (450_000, {0: n_keys}))
    monkeypatch.setattr(A, "_count_entity_matches", lambda *a, **k: n_own)
    monkeypatch.setattr(A, "_works_side", lambda *a, **k: (450_000, n_keys))
    return A.check(parse_either(oql), index_name="works", connection=None, fields_dict=fields_dict,
                   base_query={"match_all": {}})


def test_the_check_calls_a_single_split_valid_as_the_run_answers_it(monkeypatch):
    nature = ("get the count of works in [Nature](S137773608) by author at "
              "[University College London](I45129253)")
    out = _check(monkeypatch, nature, 147_180, 424_449)
    assert out["valid"] and out["estimate"]["seconds"] < 10
    assert _check(monkeypatch, nature + " and year", 147_180, 424_449)["valid"]        # it leads: it pages
    inner = ("get the count of works in [Nature](S137773608) by year and author at "
             "[University College London](I45129253)")
    assert not _check(monkeypatch, inner, 147_180, 424_449)["valid"]
    by_mean = ("get the count and mean FWCI of works in [Nature](S137773608) by author at "
               "[University College London](I45129253), highest mean FWCI first")
    assert not _check(monkeypatch, by_mean, 147_180, 424_449)["valid"]


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
@pytest.mark.parametrize("chunk", [1, 2, 100])
def test_a_single_split_key_set_walk_reads_each_range_in_one_request(monkeypatch, per_page, chunk):
    # `by author where last known institution is [X]` with its key set listed: the same walk, one terms request a
    # range (no co-authors read), every kept group once in key order
    kept = {_a(1), _a(2), _a(9), _a(13)}

    def resolve(lv, parts, oqo, *a, **k):
        lv.include, lv.exclude = set(kept), None
        return []
    monkeypatch.setattr(A, "resolve_keysets", resolve)
    monkeypatch.setattr(A, "KEYSET_CHUNK", chunk)
    fake = OwnES(WORKS)
    rows = _walk(monkeypatch, fake, per_page)
    counts = Counter(a for au, _ in WORKS for a in set(au) if a in kept)
    assert rows == sorted(counts.items())
    reads = [c[1]["aggs"]["s0"] for c in fake.calls if c[0] == "search" and "s0" in (c[1].get("aggs") or {})]
    assert reads and all("terms" in r and "composite" not in r for r in reads)
