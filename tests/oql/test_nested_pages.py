"""Nested splits past what one answer holds (oxjob #1598): with a cursor, every combination in key order (a multi-
source composite, ranged on the leading split like a single split's pages); without one, the first rows in the usual
order (`more_groups`, `groups_count`). The engine runs against a fake ES here; the live checks against production
(ranged vs read whole page by page, the page view vs the whole answer's first rows) are in the job's EXPLORE.md."""
import itertools
from collections import Counter
from dataclasses import replace

import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either


def _a(n):
    return f"https://openalex.org/A{n:04d}"


# works: (authors, years); a work holds several authors (cross products, as nested splits count them)
WORKS = [
    ([_a(1), _a(7)], [2020]), ([_a(2)], [2021]), ([_a(2), _a(3), _a(9)], [2020]), ([_a(4)], [2022]),
    ([_a(5), _a(1)], [2021]), ([_a(6)], [2020]), ([_a(7), _a(8)], [2022]), ([_a(9)], [2021]),
    ([_a(9), _a(2)], [2020]), ([_a(10)], [2023]), ([_a(11), _a(3)], [2021]), ([_a(12)], [2020]),
    ([_a(2)], [2021]), ([_a(9)], [2021]), ([_a(1)], [2020]), ([_a(13), _a(1), _a(2)], [2024]),
]


class FakeES:
    """Answers the probe (cardinalities), the whole-set request, a multi-source composite page (with a range on
    the leading key in the query) and terms-enum on the leading key (index-wide: a superset of the set's keys)."""

    def __init__(self, works, index_terms=None, min_count=None):
        self.works = works
        self.index_terms = sorted(index_terms or {k for w in works for k in w[0]})
        self.min_count = min_count
        self.calls = []
        self.fields = None   # [author field, year field], read from the first composite

    def _vals(self, work, field):
        return work[0] if "author" in field else work[1]

    def _terms_agg(self, works, agg):
        """A terms aggregation (the page view's): order, size, include, min_doc_count and a terms level under it."""
        t = agg["terms"]
        f = t["field"]
        counts = Counter(k for w in works for k in set(self._vals(w, f)))
        if isinstance(t.get("include"), list):
            counts = Counter({k: c for k, c in counts.items() if k in t["include"]})
        items = [(k, c) for k, c in counts.items() if c >= t.get("min_doc_count", 1)]
        for o in reversed(t.get("order") or [{"_count": "desc"}, {"_key": "asc"}]):
            (what, way), = o.items()
            items.sort(key=(lambda kc: kc[1]) if what == "_count" else (lambda kc: kc[0]), reverse=way == "desc")
        out = []
        for k, c in items[:t["size"]]:
            b = {"key": k, "doc_count": c}
            for name, sub in (agg.get("aggs") or {}).items():
                if "terms" in sub:
                    b[name] = self._terms_agg([w for w in works if k in self._vals(w, f)], sub)
            out.append(b)
        return {"buckets": out, "sum_other_doc_count": sum(c for _, c in items[t["size"]:])}

    def _works_in(self, query, lead):
        rng = None
        for f in (query.get("bool") or {}).get("filter") or []:
            if "terms" in f:
                (field, keys), = f["terms"].items()
                return [w for w in self.works if set(self._vals(w, field)) & set(keys)]
            if "range" in f:
                rng = list(f["range"].values())[0]
        if rng is None:
            return self.works

        def inside(k):
            return (("gt" not in rng or k > rng["gt"]) and ("gte" not in rng or k >= rng["gte"])
                    and ("lte" not in rng or k <= rng["lte"]))
        return [w for w in self.works if any(inside(k) for k in self._vals(w, lead))]

    def search(self, index, connection, body, deadline, what, **params):
        self.calls.append(("search", body))
        aggs = body.get("aggs") or {}
        out = {}
        for name, a in aggs.items():
            if name.startswith("card"):
                out[name] = {"value": len({k for w in self.works for k in self._vals(w, a["cardinality"]["field"])})}
        works = self.works
        if "combo" in aggs:   # the combined keys' count (a small set: the script, not the sample)
            fields = aggs["combo"]["cardinality"]["script"]["params"]["fields"]
            out["combo"] = {"value": len({c for w in works
                                          for c in itertools.product(*[self._vals(w, f) for f in fields])})}
        for name, a in aggs.items():
            if "terms" in a:
                out[name] = self._terms_agg(self._works_in(body["query"], a["terms"]["field"]), a)
        if "s0" in aggs and "terms" in aggs["s0"]:
            works = self._works_in(body["query"], aggs["s0"]["terms"]["field"])
        if "s0" in aggs and "composite" in aggs["s0"]:
            comp = aggs["s0"]["composite"]
            srcs = [(next(iter(s)), s[next(iter(s))]["terms"]["field"]) for s in comp["sources"]]
            works = self._works_in(body["query"], srcs[0][1])
            counts = Counter(combo for w in works
                             for combo in itertools.product(*[self._vals(w, f) for _, f in srcs]))
            after = comp.get("after")
            after_t = tuple(after[n] for n, _ in srcs) if after else None
            keys = sorted(c for c in counts if after_t is None or c > after_t)[:comp["size"]]
            buckets = [{"key": dict(zip([n for n, _ in srcs], c)), "doc_count": counts[c]} for c in keys]
            page = {"buckets": buckets}
            if keys:
                page["after_key"] = buckets[-1]["key"]
            if self.min_count and "having" in (aggs["s0"].get("aggs") or {}):
                page["buckets"] = [b for b in buckets if b["doc_count"] >= self.min_count]
            out["s0"] = page
        return {"hits": {"total": {"value": len(works)}}, "took": 1, "aggregations": out}

    def terms_after(self, index, connection, field, after, size, deadline):
        self.calls.append(("terms_enum", after, size))
        if "author" not in field:
            return None          # a number field can't list its keys: the walk reads it as one range
        rest = [t for t in self.index_terms if after is None or t > after]
        return rest[:size], True


OQL = "get the count of all works by author and year"


def _setup(monkeypatch, fake, min_works=0):
    from works.fields import fields_dict
    monkeypatch.setattr(A, "_search", fake.search)
    monkeypatch.setattr(A, "_terms_after", fake.terms_after)
    monkeypatch.setattr(A, "name_rows", lambda levels, rows, connection: rows)
    monkeypatch.setattr(A, "PARTITION_MIN_WORKS", min_works)
    monkeypatch.setattr(A, "PARTITION_MIN_TERMS", 2)
    monkeypatch.setattr(A, "MAX_LEVEL_GROUPS", 3)     # 13 authors: past what one answer holds
    return fields_dict


def _leaves(rows):
    return [(o["key"], i["key"], i["count"]) for o in rows for i in o["groups"]]


def _walk(monkeypatch, fake, oql=OQL, per_page=3, min_works=0, start="*", max_pages=300):
    fields_dict = _setup(monkeypatch, fake, min_works)
    oqo = parse_either(oql)
    cursor, rows, pages = start, [], 0
    while cursor and pages < max_pages:
        body = A.run(replace(oqo, cursor=cursor), index_name="works", connection=None,
                     fields_dict=fields_dict, base_query={"match_all": {}}, per_page=per_page)
        rows += _leaves(body["group_by"])
        cursor = body["meta"]["next_cursor"]
        pages += 1
    return rows, pages


def _exact(works, min_count=1):
    counts = Counter(c for a, y in works for c in itertools.product(a, y))
    return sorted((a, str(y), n) for (a, y), n in counts.items() if n >= min_count)


def _norm(rows):
    return [(a, str(y), n) for a, y, n in rows]


@pytest.mark.parametrize("per_page", [1, 2, 3, 5, 8, 100])
def test_a_nested_walk_lists_every_combination_once_in_key_order(monkeypatch, per_page):
    fake = FakeES(WORKS)
    rows, _ = _walk(monkeypatch, fake, per_page=per_page)
    assert _norm(rows) == _exact(WORKS)
    assert any(c[0] == "terms_enum" for c in fake.calls)


def test_keys_the_set_lacks_read_nothing_and_still_walk_exactly(monkeypatch):
    extra = {_a(n) for n in range(100, 140)} | {f"https://openalex.org/A{n:04d}5" for n in range(1, 13)}
    fake = FakeES(WORKS, index_terms=sorted({k for w in WORKS for k in w[0]} | extra))
    rows, _ = _walk(monkeypatch, fake, per_page=4)
    assert _norm(rows) == _exact(WORKS)


def test_a_cursor_inside_a_leading_key_resumes_with_its_other_combinations(monkeypatch):
    # A0001 has works in 2020, 2021 and 2024: a page that ends at (A0001, 2020) must come back for the rest
    fake = FakeES(WORKS)
    rows, _ = _walk(monkeypatch, fake, per_page=1, max_pages=3)
    assert _norm(rows) == _exact(WORKS)[:3]
    assert [r[0] for r in rows] == [_a(1)] * 3


def test_a_small_set_reads_whole_and_walks_exactly(monkeypatch):
    fake = FakeES(WORKS)
    rows, _ = _walk(monkeypatch, fake, per_page=4, min_works=10 ** 9)
    assert _norm(rows) == _exact(WORKS)
    assert not any(c[0] == "terms_enum" for c in fake.calls)


def test_a_count_floor_on_the_inner_split_walks_exactly(monkeypatch):
    # year first (a number: no term list, so one range), authors with at least 2 works that year
    fake = FakeES(WORKS, min_count=2)
    rows, _ = _walk(monkeypatch, fake, per_page=2,
                    oql="get the count of all works by year and author. Only authors with at least 2 works.")
    counts = Counter(c for a, y in WORKS for c in itertools.product(y, a))
    assert [(str(y), a, n) for y, a, n in rows] == sorted(
        (str(y), a, n) for (y, a), n in counts.items() if n >= 2)


def test_short_pages_when_time_runs_low_lose_nothing(monkeypatch):
    fake = FakeES(WORKS)
    monkeypatch.setattr(A, "PARTITION_RESERVE_S", 10 ** 6)   # always out of time
    monkeypatch.setattr(A, "PARTITION_MAX_TERMS", 2)         # ranges of two keys
    rows, pages = _walk(monkeypatch, fake, per_page=10)
    assert _norm(rows) == _exact(WORKS)
    assert pages >= 6


def test_a_cursor_page_says_how_many_combinations_remain_unknown_but_whether_more_follow(monkeypatch):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    body = A.run(replace(parse_either(OQL), cursor="*"), index_name="works", connection=None,
                 fields_dict=fields_dict, base_query={"match_all": {}}, per_page=3)
    m = body["meta"]
    assert m["more_groups"] is True and m["next_cursor"].startswith("g1.")
    assert isinstance(A._decode_cursor(m["next_cursor"]), dict)
    # outer rows carry their key; their own numbers aren't read on a cursor page
    assert body["group_by"][0]["count"] is None and body["group_by"][0]["groups"]


def test_a_single_split_cursor_on_a_nested_query_is_refused(monkeypatch):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    with pytest.raises(A.AnalyticsError) as e:
        A.run(replace(parse_either(OQL), cursor=A._encode_cursor(_a(3))), index_name="works", connection=None,
              fields_dict=fields_dict, base_query={"match_all": {}}, per_page=3)
    assert e.value.code == "invalid_cursor"


def test_a_nested_cursor_on_a_single_split_is_refused(monkeypatch):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    with pytest.raises(A.AnalyticsError) as e:
        A.run(replace(parse_either("get the count of all works by author"),
                      cursor=A._encode_cursor({"k0": _a(3), "k1": 2020})),
              index_name="works", connection=None, fields_dict=fields_dict, base_query={"match_all": {}},
              per_page=3)
    assert e.value.code == "invalid_cursor"


def test_nested_splits_by_columns_page_in_the_export_lane():
    from works.fields import fields_dict
    assert A.pages_by_cursor(parse_either(OQL), fields_dict, "works")
    assert A.pages_by_cursor(parse_either("get the count of all works by country and author"),
                             fields_dict, "works")
    assert not A.pages_by_cursor(parse_either("get the count of all works"), fields_dict, "works")


def _whole_answer(works):
    """The nested table as one answer would order it: authors most works first (then by key), each author's years
    oldest first."""
    by_author = Counter(a for au, _ in works for a in set(au))
    rows = []
    for a in sorted(by_author, key=lambda a: (-by_author[a], a)):
        years = Counter(y for au, ys in works if a in au for y in ys)
        rows += [(a, str(y), years[y]) for y in sorted(years)]
    return rows


@pytest.mark.parametrize("per_page,page", [(5, 1), (5, 2), (3, 4), (40, 1)])
def test_the_page_shows_the_whole_answers_rows_in_order(monkeypatch, per_page, page):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    body = A.run(parse_either(OQL), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, per_page=per_page, page=page)
    whole = _whole_answer(WORKS)
    assert _norm(_leaves(body["group_by"])) == whole[(page - 1) * per_page:page * per_page]
    m = body["meta"]
    assert m["more_groups"] is True and m["next_cursor"] is None
    assert m["groups_count"] == len(whole)            # the combined keys' count (the script, on a small set)
    outer = body["summary"]["splits"][0]["groups"]    # the outer split on its own: its first groups
    assert [r["key"] for r in outer][:3] == [_a(2), _a(1), _a(9)]


def test_the_page_view_of_a_count_floored_split_has_no_combination_count(monkeypatch):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    body = A.run(parse_either("get the count of all works by year and author. Only authors with at least 2 works."),
                 index_name="works", connection=None, fields_dict=fields_dict, base_query={"match_all": {}},
                 per_page=3)
    assert body["meta"]["groups_count"] is None
    assert all(r["count"] >= 2 for o in body["group_by"] for r in o["groups"])


def test_leaf_slice_keeps_outer_rows_around_the_leaves():
    rows = [{"key": "a", "groups": [{"key": "a1"}, {"key": "a2"}]}, {"key": "b", "groups": []},
            {"key": "c", "groups": [{"key": "c1"}, {"key": "c2"}, {"key": "c3"}]}]
    got = A._leaf_slice(rows, 2, 1, 4)
    assert [(r["key"], [g["key"] for g in r["groups"]]) for r in got] == [("a", ["a2"]), ("c", ["c1", "c2"])]


def test_unsupported_nested_shapes_keep_their_refusal():
    from works.fields import fields_dict
    oqo = A._nnf_group_filters(parse_either(OQL))
    levels = [A.build_level(i, g, oqo, fields_dict, "works") for i, g in enumerate(oqo.group_by)]
    count = [A.Measure("count")]
    assert A._nested_pages_ok(levels, count, None, None)
    assert A._nested_pages_ok(levels, count, ("count", "desc"), None)
    assert not A._nested_pages_ok(levels, count, ("cited_by_count_mean", "desc"), None)
    assert not A._nested_pages_ok(levels, [A.Measure("percent_of_those")], None, "*")
    levels[0].include = {_a(1)}
    assert not A._nested_pages_ok(levels, count, None, None)
