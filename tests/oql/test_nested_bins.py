"""`of` bins in a nested split past the limits (oxjob #1598): `... by institution and by FWCI bins of 1` was refused
(`too_many_groups`) once the column split passed 10,000 groups. A bin split now pages as a column split: a composite
histogram source on cursor pages (key order, empty bins left out as in one answer), a histogram aggregation on the
page view (lowest bin first, or by count). Against a fake ES; the production checks are in the job's EXPLORE.md."""
import itertools
import math
from collections import Counter

import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either
from tests.oql.test_nested_pages import WORKS, _a, _leaves, _setup, _walk
from tests.oql.test_nested_small_splits import SmallES, _levels

# (authors, FWCI): decimals on and near bin edges (0.6 / 0.1 rounds to bin 0.5 in floating point), one with none
WORKS_F = [
    ([_a(1), _a(7)], [0.4]), ([_a(2)], [1.2]), ([_a(2), _a(3), _a(9)], [0.6]), ([_a(4)], [2.5]),
    ([_a(5), _a(1)], [1.0]), ([_a(6)], [0.0]), ([_a(7), _a(8)], [3.7]), ([_a(9)], [0.9]),
    ([_a(9), _a(2)], [1.5]), ([_a(10)], [12.2]), ([_a(11), _a(3)], [0.3]), ([_a(12)], [2.0]),
    ([_a(2)], [0.7]), ([_a(9)], [5.1]), ([_a(1)], [1.9]), ([_a(13), _a(1), _a(2)], [0.6]),
    ([_a(2)], [2.2]), ([_a(1)], [0.1]), ([_a(3)], []),
]

CASES = {"years": (WORKS, "year bins of 2"), "fwci": (WORKS_F, "FWCI bins of 0.5")}


def _lo(v, w):
    return float(math.floor(v / w) * w)


class BinsES(SmallES):
    """SmallES that also answers histogram aggregations (top level, under a terms bucket, with a terms level under
    it), composite histogram sources and the combined keys' script with bin widths."""
    AGG_KINDS = SmallES.AGG_KINDS + ("histogram",)

    def _agg(self, works, agg):
        if "histogram" not in agg:
            return super()._agg(works, agg)
        h = agg["histogram"]
        groups = {}
        for wk in works:
            for lo in {_lo(v, h["interval"]) for v in self._vals(wk, h["field"])}:
                groups.setdefault(lo, []).append(wk)
        items = [(lo, len(ws)) for lo, ws in groups.items() if len(ws) >= h.get("min_doc_count", 0)]
        order = h.get("order") or [{"_key": "asc"}]
        for o in reversed(order if isinstance(order, list) else [order]):
            (what, way), = o.items()
            items.sort(key=(lambda kc: kc[1]) if what == "_count" else (lambda kc: kc[0]), reverse=way == "desc")
        return {"buckets": [{"key": lo, "doc_count": c, **self._subs(groups[lo], agg)} for lo, c in items]}

    def _keys(self, w, src):
        if "histogram" not in src:
            return super()._keys(w, src)
        h = src["histogram"]
        return sorted({_lo(v, h["interval"]) for v in self._vals(w, h["field"])})

    def search(self, index, connection, body, deadline, what, **params):
        res = super().search(index, connection, body, deadline, what, **params)
        works = [w for w in self.works if self._match(w, body.get("query"))]
        for name, a in (body.get("aggs") or {}).items():
            if "script" in a.get("cardinality", {}):   # the combined keys, bins counted as bins
                p = a["cardinality"]["script"]["params"]
                ws = p.get("widths") or {}
                srcs = [{"histogram": {"field": f, "interval": ws[f]}} if f in ws else {"terms": {"field": f}}
                        for f in p["fields"]]
                res["aggregations"][name] = {"value": len({c for w in works for c in itertools.product(
                    *[self._keys(w, s) for s in srcs])})}
        return res


def _oql(bins, bins_first=False):
    first, second = (f"into {bins}", "by author") if bins_first else ("by author", f"by {bins}")
    return f"get works; then, group those works {first} and {second}"


def _bin_level(oql):
    from works.fields import fields_dict
    return next(lv for lv in _levels(oql, fields_dict) if lv.kind == "histogram")


def _combos(works, w):
    """(author, bin low edge) -> works."""
    c = Counter()
    for au, vals in works:
        for a, lo in itertools.product(set(au), {_lo(v, w) for v in vals}):
            c[(a, lo)] += 1
    return c


def _run(monkeypatch, fake, oql, **kw):
    fields_dict = _setup(monkeypatch, fake)
    return A.run(parse_either(oql), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, **kw)


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("per_page", [1, 2, 3, 7, 100])
@pytest.mark.parametrize("bins_first", [False, True])
def test_a_cursor_walk_lists_every_combination_once_in_key_order(monkeypatch, case, per_page, bins_first):
    works, bins = CASES[case]
    oql = _oql(bins, bins_first)
    lv = _bin_level(oql)
    rows, pages = _walk(monkeypatch, BinsES(works), oql, per_page=per_page)
    combos = _combos(works, lv.split.bins["of"])
    if bins_first:
        want = [(A._bin_label(lv, lo), a, n) for (a, lo), n in sorted(combos.items(), key=lambda kv: kv[0][::-1])]
    else:
        want = [(a, A._bin_label(lv, lo), n) for (a, lo), n in sorted(combos.items())]
    assert rows == want
    assert pages > 1 or per_page >= len(want)


def _whole(works, lv, bins_first, sort=None):
    """The table as one answer orders it: authors most works first (then by key), bins lowest first; a sort by
    count orders both by count (ties as listed)."""
    w = lv.split.bins["of"]
    combos = _combos(works, w)
    by_author = Counter(a for au, _ in works for a in set(au))
    by_bin = Counter(lo for _, vals in works for lo in {_lo(v, w) for v in vals})
    rows = []
    if bins_first:
        for lo in sorted(by_bin, key=lambda lo: ((-by_bin[lo]) if sort else 0, lo)):
            inner = sorted((a for (a, x) in combos if x == lo), key=lambda a: (-combos[(a, lo)], a))
            rows += [(A._bin_label(lv, lo), a, combos[(a, lo)]) for a in inner]
    else:
        for a in sorted(by_author, key=lambda a: (-by_author[a], a)):
            inner = sorted((lo for (x, lo) in combos if x == a), key=lambda lo: ((-combos[(a, lo)]) if sort else 0, lo))
            rows += [(a, A._bin_label(lv, lo), combos[(a, lo)]) for lo in inner]
    return rows


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("bins_first", [False, True])
@pytest.mark.parametrize("sort", [None, ("count", "desc")])
@pytest.mark.parametrize("per_page,page", [(5, 1), (5, 2), (3, 4), (60, 1)])
def test_the_page_shows_the_whole_answers_rows_in_order(monkeypatch, case, bins_first, sort, per_page, page):
    works, bins = CASES[case]
    oql = _oql(bins, bins_first)
    lv = _bin_level(oql)
    body = _run(monkeypatch, BinsES(works), oql, per_page=per_page, page=page, sort=sort)
    whole = _whole(works, lv, bins_first, sort)
    assert _leaves(body["group_by"]) == whole[(page - 1) * per_page:page * per_page]
    m = body["meta"]
    assert m["more_groups"] is True and m["next_cursor"] is None
    assert m["rows_count"] == len(whole)         # the combined keys, bins counted as bins (not 100 a key)
    n_bins = len({lo for _, vals in works for lo in {_lo(v, lv.split.bins["of"]) for v in vals}})
    assert m["groups_count"] == (n_bins if bins_first else 13)


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("bins_first", [False, True])
@pytest.mark.parametrize("sort", [None, ("count", "desc")])
def test_the_page_view_equals_one_answers_first_rows(monkeypatch, case, bins_first, sort):
    """Within the limits the same query is one answer; past them (limits lowered) the page view must show that
    answer's first rows, row for row."""
    works, bins = CASES[case]
    oql = _oql(bins, bins_first)
    paged = _run(monkeypatch, BinsES(works), oql, per_page=200, sort=sort)
    fields_dict = _setup(monkeypatch, BinsES(works))
    monkeypatch.setattr(A, "MAX_LEVEL_GROUPS", 10_000)   # one answer holds it
    one = A.run(parse_either(oql), index_name="works", connection=None, fields_dict=fields_dict,
                base_query={"match_all": {}}, per_page=200, sort=sort)
    assert one["meta"]["more_groups"] is False and paged["meta"]["more_groups"] is True
    assert _leaves(paged["group_by"]) == _leaves(one["group_by"])


def test_a_sort_by_key_on_leading_bins_keeps_its_refusal():
    """One answer sorts bins by key as their labels (`10-10.5` before `2-2.5`), not as ES lists them."""
    from works.fields import fields_dict
    levels = _levels(_oql("FWCI bins of 0.5", bins_first=True), fields_dict)
    count = [A.Measure("count")]
    assert A._nested_pages_ok(levels, count, None, None)
    assert A._nested_pages_ok(levels, count, ("count", "desc"), None)
    assert not A._nested_pages_ok(levels, count, ("key", "asc"), None)
    assert A._nested_pages_ok(levels, count, None, "*")


def test_bins_queries_hold_every_work_of_their_bins_and_merge_neighbours():
    lv = _bin_level(_oql("FWCI bins of 0.1"))
    q = A._held_query(lv, [0.5, 0.6000000000000001, 0.2])
    assert len(q["bool"]["should"]) == 2         # 0.5 and 0.6 are neighbours: one range
    es = BinsES([])
    for v in (0.6, 0.55, 0.7, 0.2, 0.29):        # 0.6 / 0.1 = 5.999...: ES puts it in bin 0.5
        assert es._match(([], [v]), q), v
    for v in (0.9, 0.35, 0.19):
        assert not es._match(([], [v]), q), v


@pytest.mark.parametrize("lead_card,n_works,widths,parts", [
    (4_429, 104_000_000, {"fwci": 1}, 104),   # few keys, many works: about a million works sampled, not all of them
    (4_429, 104_000_000, {}, 1),              # no bins: a field's cardinality, the whole set as before
    (100, 104_000_000, {"fwci": 1}, 100),     # never more partitions than keys
    (900_000, 5_000_000, {"fwci": 1}, 180),   # many keys: SAMPLE_KEYS keys, as before
])
def test_a_sample_counting_bins_reads_about_a_million_works(monkeypatch, lead_card, n_works, widths, parts):
    seen = []

    def search(index, connection, body, deadline, what, **params):
        seen.append(body["aggs"]["k"]["terms"]["include"]["num_partitions"])
        return {"aggregations": {"k": {"buckets": []}}}
    monkeypatch.setattr(A, "_search", search)
    A._sampled_combos(["authorships_full.author.id", "fwci"], lead_card, "works", None, {"match_all": {}},
                      A.Deadline(10), widths, n_works)
    assert seen == [parts]


def test_the_estimate_counts_bins_not_a_hundred_a_key(monkeypatch):
    from works.fields import fields_dict
    _setup(monkeypatch, BinsES(WORKS_F))
    levels = _levels(_oql("FWCI bins of 0.5"), fields_dict)
    n = A._combined_groups(levels, "works", None, {"match_all": {}}, A.Deadline(10), len(WORKS_F), {0: 13})
    assert n == len(_combos(WORKS_F, 0.5))
