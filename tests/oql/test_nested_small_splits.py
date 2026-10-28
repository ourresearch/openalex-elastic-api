"""Nested splits past the limits with a small split beside the column ones (oxjob #1598): listed values, conditions,
`at` bins and yes/no columns after a column split ride under each of its keys (every group, as one answer shows
them); one before them is walked a group at a time. "by institution and open access" was refused past 10,000
institutions; now the page shows its first rows and the cursor pages every row. Against a fake ES; the production
checks are in the job's EXPLORE.md."""
import itertools
from collections import Counter
from dataclasses import replace

import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either
from tests.oql.test_nested_pages import WORKS, FakeES, _a, _setup

BY_AUTHOR_BINS = ("get works where year >= (1900); then group those works by author; then group those works again "
                  "by year bins at (2021, 2023); then summarize using count")
BY_BINS_AUTHOR = ("get works where year >= (1900); then group those works by year bins at (2021, 2023); then group "
                  "those works again by author; then summarize using count")
BINS = [("b0", None, 2021), ("b1", 2021, 2023), ("b2", 2023, None)]


def _in_bin(y, lo, hi):
    return (lo is None or y >= lo) and (hi is None or y < hi)


class SmallES(FakeES):
    """FakeES that also reads queries (bool / range / term / terms) and answers range and filters aggregations,
    top level, under a terms bucket or under a composite bucket."""

    def _match(self, w, q) -> bool:
        if not q or "match_all" in q:
            return True
        if "bool" in q:
            return all(self._match(w, f) for f in q["bool"].get("filter", []))
        (kind, spec), = q.items()
        (field, arg), = spec.items()
        vals = self._vals(w, field)
        if kind == "range":
            return any(("gt" not in arg or v > arg["gt"]) and ("gte" not in arg or v >= arg["gte"])
                       and ("lt" not in arg or v < arg["lt"]) and ("lte" not in arg or v <= arg["lte"]) for v in vals)
        wanted = {str(x) for x in (arg if kind == "terms" else [arg])}
        return bool({str(v) for v in vals} & wanted)

    def _subs(self, works, agg):
        return {n: self._agg(works, a) for n, a in (agg.get("aggs") or {}).items()
                if any(t in a for t in ("terms", "range", "filters"))}

    def _agg(self, works, agg):
        if "range" in agg:
            f = agg["range"]["field"]
            out = []
            for r in agg["range"]["ranges"]:
                ws = [w for w in works if any(_in_bin(v, r.get("from"), r.get("to")) for v in self._vals(w, f))]
                out.append({"key": r["key"], "doc_count": len(ws), **self._subs(ws, agg)})
            return {"buckets": out}
        if "filters" in agg:
            out = {}
            for k, q in agg["filters"]["filters"].items():
                ws = [w for w in works if self._match(w, q)]
                out[k] = {"doc_count": len(ws), **self._subs(ws, agg)}
            return {"buckets": out}
        t = agg["terms"]
        f = t["field"]
        counts = Counter(k for w in works for k in set(self._vals(w, f)))
        if isinstance(t.get("include"), list):
            counts = Counter({k: c for k, c in counts.items() if k in t["include"]})
        items = [(k, c) for k, c in counts.items() if c >= t.get("min_doc_count", 1)]
        for o in reversed(t.get("order") or [{"_count": "desc"}, {"_key": "asc"}]):
            (what, way), = o.items()
            items.sort(key=(lambda kc: kc[1]) if what == "_count" else (lambda kc: kc[0]), reverse=way == "desc")
        out = [{"key": k, "doc_count": c, **self._subs([w for w in works if k in self._vals(w, f)], agg)}
               for k, c in items[:t["size"]]]
        return {"buckets": out, "sum_other_doc_count": sum(c for _, c in items[t["size"]:])}

    def _composite(self, works, a):
        comp = a["composite"]
        srcs = [(n, s[n]["terms"]["field"]) for s in comp["sources"] for n in s]
        combos = {}
        for w in works:
            for c in itertools.product(*[sorted(set(self._vals(w, f))) for _, f in srcs]):
                combos.setdefault(c, []).append(w)
        after = comp.get("after")
        after_t = tuple(after[n] for n, _ in srcs) if after else None
        keys = sorted(c for c in combos if after_t is None or c > after_t)[:comp["size"]]
        buckets = [{"key": dict(zip([n for n, _ in srcs], c)), "doc_count": len(combos[c]),
                    **self._subs(combos[c], a)} for c in keys]
        if self.min_count and "having" in (a.get("aggs") or {}):
            buckets = [b for b in buckets if b["doc_count"] >= self.min_count]
        page = {"buckets": buckets}
        if keys:
            page["after_key"] = dict(zip([n for n, _ in srcs], keys[-1]))
        return page

    def search(self, index, connection, body, deadline, what, **params):
        self.calls.append(("search", body))
        works = [w for w in self.works if self._match(w, body.get("query"))]
        out = {}
        for name, a in (body.get("aggs") or {}).items():
            if name.startswith("card"):
                out[name] = {"value": len({k for w in works for k in self._vals(w, a["cardinality"]["field"])})}
            elif "composite" in a:
                out[name] = self._composite(works, a)
            elif any(t in a for t in ("terms", "range", "filters")):
                out[name] = self._agg(works, a)
        return {"hits": {"total": {"value": len(works)}}, "took": 1, "aggregations": out}


def _by_author_bins():
    """Every row of (author, year bin) in key order: each author's three bins, empty ones too (as one answer)."""
    authors = sorted({a for au, _ in WORKS for a in au})
    return [(a, b, sum(1 for au, ys in WORKS if a in au and any(_in_bin(y, lo, hi) for y in ys)))
            for a in authors for b, lo, hi in BINS]


def _by_bins_author():
    """Every row of (year bin, author) in key order (bins as listed; a bin's authors by key)."""
    rows = []
    for b, lo, hi in BINS:
        c = Counter(a for au, ys in WORKS if any(_in_bin(y, lo, hi) for y in ys) for a in set(au))
        rows += [(b, a, c[a]) for a in sorted(c)]
    return rows


def _flat(rows, levels):
    """Leaves as (outer raw key, inner raw key, count); bins read back to their bucket key by label."""
    def k(lv, r):
        if lv.kind == "range":
            return next(b for b, (key, _) in lv.labels.items() if key == r["key"])
        return r["_raw"][1] if "_raw" in r else r["key"]
    return [(k(levels[0], o), k(levels[1], i), i["count"]) for o in rows for i in o["groups"]]


def _levels(oql, fields_dict):
    oqo = parse_either(oql)
    return [A.build_level(i, g, oqo, fields_dict, "works") for i, g in enumerate(oqo.group_by)]


def _walk(monkeypatch, oql, per_page):
    fake = SmallES(WORKS)
    fields_dict = _setup(monkeypatch, fake)
    oqo, levels = parse_either(oql), _levels(oql, fields_dict)
    cursor, rows, pages = "*", [], 0
    while cursor and pages < 300:
        body = A.run(replace(oqo, cursor=cursor), index_name="works", connection=None, fields_dict=fields_dict,
                     base_query={"match_all": {}}, per_page=per_page)
        rows += _flat(body["group_by"], levels)
        cursor = body["meta"]["next_cursor"]
        pages += 1
    return rows, pages


def test_shapes_that_page():
    from works.fields import fields_dict
    assert A._shape(_levels(BY_AUTHOR_BINS, fields_dict)) == (0, 1)
    assert A._shape(_levels(BY_BINS_AUTHOR, fields_dict)) == (1, 0)
    assert A._shape(_levels("get the count of all works by author and open access", fields_dict)) == (0, 1)
    assert A._shape(_levels("get the count of all works by author and year", fields_dict)) == (0, 0)
    two_bins = ("get works where year >= (1900); then group those works by year bins at (2021); then group those "
                "works again by cited_by_count bins at (10); then summarize using count")
    assert A._shape(_levels(two_bins, fields_dict)) is None          # no column split: one answer holds it
    assert A.pages_by_cursor(parse_either(BY_BINS_AUTHOR), fields_dict, "works")
    assert A.pages_by_cursor(parse_either("get the count of all works by institution and open access"),
                             fields_dict, "works")
    assert not A.pages_by_cursor(parse_either(two_bins), fields_dict, "works")


@pytest.mark.parametrize("per_page", [1, 3, 4, 7, 100])
def test_bins_after_a_column_page_every_row_once_in_key_order(monkeypatch, per_page):
    rows, _ = _walk(monkeypatch, BY_AUTHOR_BINS, per_page)
    assert rows == _by_author_bins()


@pytest.mark.parametrize("per_page", [1, 2, 5, 100])
def test_bins_before_a_column_page_every_row_once_in_key_order(monkeypatch, per_page):
    rows, _ = _walk(monkeypatch, BY_BINS_AUTHOR, per_page)
    assert rows == _by_bins_author()


def test_a_cursor_between_groups_resumes_at_the_next_group(monkeypatch):
    fake = SmallES(WORKS)
    fields_dict = _setup(monkeypatch, fake)
    oqo = parse_either(BY_BINS_AUTHOR)
    body = A.run(replace(oqo, cursor=A._encode_cursor({"g": 2, "a": None})), index_name="works", connection=None,
                 fields_dict=fields_dict, base_query={"match_all": {}}, per_page=100)
    assert _flat(body["group_by"], _levels(BY_BINS_AUTHOR, fields_dict)) == [r for r in _by_bins_author()
                                                                             if r[0] == "b2"]
    assert body["meta"]["next_cursor"] is None
    for bad in ({"g": 3, "a": None}, {"g": 0}, {"k1": _a(1)}):
        with pytest.raises(A.AnalyticsError) as e:
            A.run(replace(oqo, cursor=A._encode_cursor(bad)), index_name="works", connection=None,
                  fields_dict=fields_dict, base_query={"match_all": {}}, per_page=5)
        assert e.value.code == "invalid_cursor"


def _whole_author_bins():
    """One answer's order: authors most works first (then by key), each one's bins as listed."""
    by_author = Counter(a for au, _ in WORKS for a in set(au))
    rows = {(a, b): n for a, b, n in _by_author_bins()}
    return [(a, b, rows[a, b]) for a in sorted(by_author, key=lambda a: (-by_author[a], a)) for b, _, _ in BINS]


def _whole_bins_author():
    """One answer's order: bins as listed (empty ones hold no rows), each bin's authors most works first."""
    out = []
    for b, lo, hi in BINS:
        c = Counter(a for au, ys in WORKS if any(_in_bin(y, lo, hi) for y in ys) for a in set(au))
        out += [(b, a, c[a]) for a in sorted(c, key=lambda a: (-c[a], a))]
    return out


@pytest.mark.parametrize("oql,whole", [(BY_AUTHOR_BINS, _whole_author_bins), (BY_BINS_AUTHOR, _whole_bins_author)])
@pytest.mark.parametrize("per_page,page", [(5, 1), (5, 2), (4, 3), (60, 1)])
def test_the_page_shows_the_whole_answers_rows_in_order(monkeypatch, oql, whole, per_page, page):
    fields_dict = _setup(monkeypatch, SmallES(WORKS))
    body = A.run(parse_either(oql), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, per_page=per_page, page=page)
    rows = whole()
    assert _flat(body["group_by"], _levels(oql, fields_dict)) == rows[(page - 1) * per_page:page * per_page]
    m = body["meta"]
    assert m["more_groups"] is True and m["next_cursor"] is None
    if oql == BY_AUTHOR_BINS:
        assert m["groups_count"] == 13 and m["rows_count"] == 13 * 3   # every author's three bins
    else:
        assert m["groups_count"] == 3                                  # the bins


def test_the_summary_lists_a_small_split_whole(monkeypatch):
    fields_dict = _setup(monkeypatch, SmallES(WORKS))
    body = A.run(parse_either(BY_AUTHOR_BINS), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, per_page=3, summary_only=True)
    authors, bins = body["summary"]["splits"]
    assert bins["more_groups"] is False and bins["groups_count"] == 3 and len(bins["groups"]) == 3
    assert [g["count"] for g in bins["groups"]] == [sum(1 for _, ys in WORKS if any(_in_bin(y, lo, hi) for y in ys))
                                                     for _, lo, hi in BINS]
    assert authors["groups_count"] == 13
