"""Cursor pages over a big set read range by range (oxjob #1598): a range on the split's key, bounded by the field's
term list, keeps every work holding a key in the range, so each group's numbers are exact; the other keys those works
hold come after the range and are dropped. The engine runs against a fake ES here; the live equivalence checks
(partitioned vs whole, page by page, on production) are in the job's EXPLORE.md."""
from collections import Counter
from dataclasses import replace

from query_translation import analytics as A
from query_translation.oql_parser import parse_either


class FakeES:
    """Works holding several keys each (a field a work holds many of, like authors). Answers the whole-set request,
    a composite page (with an optional range on the key in the query) and terms-enum over `index_terms` (the
    field's keys index-wide: a superset of the set's keys)."""

    def __init__(self, works, index_terms=None, terms_enum=True, min_count=None):
        self.works = works
        self.index_terms = sorted(index_terms or {k for w in works for k in w})
        self.terms_enum_ok = terms_enum
        self.min_count = min_count      # stands in for a count filter's bucket_selector
        self.calls = []

    def _works_in(self, query):
        rng = None
        for f in (query.get("bool") or {}).get("filter") or []:
            if "range" in f:
                rng = list(f["range"].values())[0]
        if rng is None:
            return self.works

        def inside(k):
            return ("gt" not in rng or k > rng["gt"]) and ("lte" not in rng or k <= rng["lte"])
        return [w for w in self.works if any(inside(k) for k in w)]

    def search(self, index, connection, body, deadline, what, **params):
        self.calls.append(("search", body))
        works = self._works_in(body["query"])
        aggs = body.get("aggs") or {}
        out = {}
        if "n_groups" in aggs:
            out["n_groups"] = {"value": len({k for w in self.works for k in w})}
        if "s0" in aggs:
            comp = aggs["s0"]["composite"]
            counts = Counter(k for w in works for k in w)
            after = (comp.get("after") or {}).get("k")
            keys = sorted(k for k in counts if after is None or k > after)[:comp["size"]]
            buckets = [{"key": {"k": k}, "doc_count": counts[k]} for k in keys]
            page = {"buckets": buckets}
            if keys:
                page["after_key"] = {"k": keys[-1]}
            if self.min_count and "having" in (aggs["s0"].get("aggs") or {}):
                page["buckets"] = [b for b in buckets if b["doc_count"] >= self.min_count]
            out["s0"] = page
        return {"hits": {"total": {"value": len(works)}}, "took": 1, "aggregations": out}

    def terms_after(self, index, connection, field, after, size, deadline, key_kind="keyword"):
        self.calls.append(("terms_enum", after, size))
        if not self.terms_enum_ok:
            return None
        rest = [t for t in self.index_terms if after is None or t > after]
        return rest[:size], True


def _walk(monkeypatch, fake, oql="get the count of all works by author", per_page=3, min_works=0):
    from works.fields import fields_dict
    monkeypatch.setattr(A, "_search", fake.search)
    monkeypatch.setattr(A, "_terms_after", fake.terms_after)
    monkeypatch.setattr(A, "name_rows", lambda levels, rows, connection: rows)
    monkeypatch.setattr(A, "PARTITION_MIN_WORKS", min_works)
    monkeypatch.setattr(A, "PARTITION_MIN_TERMS", 2)
    oqo = parse_either(oql)
    cursor, rows, pages = "*", [], 0
    while cursor and pages < 200:
        body = A.run(replace(oqo, cursor=cursor), index_name="works", connection=None,
                     fields_dict=fields_dict, base_query={"match_all": {}}, per_page=per_page)
        rows += [(r["key"], r["count"]) for r in body["group_by"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
    return rows, pages


def _exact(works, min_count=1):
    return sorted((k, n) for k, n in Counter(k for w in works for k in w).items() if n >= min_count)


def _a(n):
    return f"https://openalex.org/A{n:04d}"


WORKS = [
    [_a(1), _a(7)], [_a(2)], [_a(2), _a(3), _a(9)], [_a(4)], [_a(5), _a(1)], [_a(6)],
    [_a(7), _a(8)], [_a(9)], [_a(9), _a(2)], [_a(10)], [_a(11), _a(3)], [_a(12)],
]


def _keys(rows):
    return [(k.rsplit("/", 1)[-1], n) for k, n in rows]


def test_a_partitioned_walk_lists_every_group_once_with_exact_counts(monkeypatch):
    fake = FakeES(WORKS)
    rows, pages = _walk(monkeypatch, fake)
    assert _keys(rows) == _keys(_exact(WORKS))
    assert any(c[0] == "terms_enum" for c in fake.calls)


def test_keys_the_set_lacks_read_nothing_and_still_walk_exactly(monkeypatch):
    # the term list holds many keys no work in the set has (other works in the index)
    index_terms = sorted({k for w in WORKS for k in w} | {_a(n) for n in range(100, 140)}
                         | {f"https://openalex.org/A{n:04d}5" for n in range(1, 13)})
    fake = FakeES(WORKS, index_terms=index_terms)
    rows, _ = _walk(monkeypatch, fake, per_page=4)
    assert _keys(rows) == _keys(_exact(WORKS))


def test_a_range_query_keeps_every_work_holding_an_in_range_key(monkeypatch):
    # A0002 is held by three works, one of them also holding A0009 far past the first range
    fake = FakeES(WORKS)
    rows, _ = _walk(monkeypatch, fake, per_page=2)
    assert dict(_keys(rows))["A0002"] == 3
    assert dict(_keys(rows))["A0009"] == 3


def test_a_count_filter_walks_exactly(monkeypatch):
    fake = FakeES(WORKS, min_count=2)
    rows, _ = _walk(monkeypatch, fake,
                    oql="get the count of all works by author. Only authors with at least 2 works.")
    assert _keys(rows) == _keys(_exact(WORKS, min_count=2))


def test_a_small_set_reads_whole(monkeypatch):
    fake = FakeES(WORKS)
    rows, _ = _walk(monkeypatch, fake, min_works=10 ** 9)
    assert _keys(rows) == _keys(_exact(WORKS))
    assert not any(c[0] == "terms_enum" for c in fake.calls)


def test_a_field_that_cant_list_its_keys_reads_whole(monkeypatch):
    fake = FakeES(WORKS, terms_enum=False)
    rows, _ = _walk(monkeypatch, fake)
    assert _keys(rows) == _keys(_exact(WORKS))


def test_a_page_stops_reading_when_its_time_runs_low(monkeypatch):
    fake = FakeES(WORKS)
    monkeypatch.setattr(A, "PARTITION_RESERVE_S", 10 ** 6)   # always out of time
    monkeypatch.setattr(A, "PARTITION_MAX_TERMS", 2)         # ranges of two keys
    rows, pages = _walk(monkeypatch, fake, per_page=10)
    assert _keys(rows) == _keys(_exact(WORKS))               # short pages, nothing lost
    assert pages >= 6                                        # one two-key range a page


def test_cursors_stay_plain_after_keys():
    c = A._encode_cursor(_a(7))
    assert c.startswith("g1.") and A._decode_cursor(c) == _a(7)


def test_a_count_filter_on_a_small_set_walks_exactly(monkeypatch):
    fake = FakeES(WORKS, min_count=2)
    rows, _ = _walk(monkeypatch, fake, min_works=10 ** 9,
                    oql="get the count of all works by author. Only authors with at least 2 works.")
    assert _keys(rows) == _keys(_exact(WORKS, min_count=2))
    assert not any(c[0] == "terms_enum" for c in fake.calls)
