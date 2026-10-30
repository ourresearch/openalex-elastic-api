"""Sets past 450,000 works (oxjob #1930): which shard holds a work, routed id-filter pieces, composite pages split
side by side, and the list guard."""
import pytest

from query_translation import id_split as S
from query_translation import shard_route as R
from query_translation import walk_exec as W


def _reference_hash(s: str) -> int:
    """murmur3_x86_32 (seed 0) over UTF-16LE, one character at a time: ES's Murmur3HashFunction.hash(String)."""
    data = s.encode("utf-16-le")
    c1, c2, h, n = 0xcc9e2d51, 0x1b873593, 0, len(data) // 4 * 4
    rotl = lambda x, r: ((x << r) | (x >> (32 - r))) & 0xffffffff   # noqa: E731
    for i in range(0, n, 4):
        k = rotl((int.from_bytes(data[i:i + 4], "little") * c1) & 0xffffffff, 15) * c2 & 0xffffffff
        h = (rotl(h ^ k, 13) * 5 + 0xe6546b64) & 0xffffffff
    if len(data) % 4:
        k = rotl((int.from_bytes(data[n:], "little") * c1) & 0xffffffff, 15) * c2 & 0xffffffff
        h ^= k
    h ^= len(data)
    for shift, mul in ((16, 0x85ebca6b), (13, 0xc2b2ae35)):
        h = ((h ^ (h >> shift)) * mul) & 0xffffffff
    h ^= h >> 16
    return h - (1 << 32) if h & 0x80000000 else h


def test_shards_of_works_as_production_routes_them():
    # found on these shards of works-v40 (72 shards, 576 routing shards) with preference=_shards:k, 2026-10-30
    live = {"https://openalex.org/W2100837269": 63, "https://openalex.org/W2741809807": 43,
            "https://openalex.org/W3001118548": 27}
    assert dict(zip(live, R.shards_of(list(live), 72, 576).tolist())) == live


@pytest.mark.parametrize("ids", [
    [f"https://openalex.org/W{i}" for i in range(1, 3000, 7)],          # odd and even lengths
    ["x", "ab", "https://openalex.org/A5023888391", "héllo", ""],
])
def test_vector_hash_equals_the_reference(ids):
    got = R.shards_of(ids, 72, 576).tolist()
    assert got == [(_reference_hash(s) % 576) // 8 for s in ids]


def test_characters_outside_the_bmp_are_not_routed():
    assert R.shards_of(["https://openalex.org/W1", "emoji \U0001F600"], 72, 576) is None


def test_default_routing_shards_as_elasticsearch():
    assert [R.default_routing_shards(n) for n in (1, 5, 12, 72, 1024)] == [1024, 640, 768, 576, 2048]


def test_group_cuts_by_shard_and_keeps_every_id():
    ids = [f"https://openalex.org/W{i}" for i in range(50_000)]
    where = R.shards_of(ids, 72, 576)
    groups = R.group(ids, where, 72, 24)
    assert sorted(i for _, part in groups for i in part) == sorted(ids)
    for shards, part in groups:
        assert len(shards) == 3 and set(R.shards_of(part, 72, 576).tolist()) <= set(shards)


IDS = [f"https://openalex.org/W{i}" for i in range(100_000)]


def _body(aggs):
    return {"size": 0, "track_total_hits": True,
            "query": {"bool": {"filter": [S._terms("id", IDS), {"term": {"is_xpac": "false"}}]}}, "aggs": aggs}


def _route(field, clause):
    if field != "id":
        return None
    ids = S._values(clause)
    return "works-v40", R.group(ids, R.shards_of(ids, 72, 576), 72, S.ROUTE_PIECES)


def test_routed_pieces_ask_only_their_shards():
    pieces = S.pieces(_body({"n": {"value_count": {"field": "id"}}}), _route)
    assert len(pieces) == S.ROUTE_PIECES
    seen = []
    for piece, (index, pref) in pieces:
        assert index == "works-v40"
        shards = [int(x) for x in pref.removeprefix("_shards:").split(",")]
        ids = S._values(piece["query"]["bool"]["filter"][0])
        assert set(R.shards_of(ids, 72, 576).tolist()) <= set(shards)
        seen += ids
    assert sorted(seen) == sorted(IDS)
    unrouted = S.pieces(_body({"n": {"value_count": {"field": "id"}}}), lambda f, c: None)
    assert [extra for _, extra in unrouted] == [()] * S.unrouted_pieces(len(IDS))


def test_a_filters_lists_are_the_same_objects_each_call():
    b = _body({})
    clause = b["query"]["bool"]["filter"][0]
    assert all(a is c for a, c in zip(S.chunk_lists(clause), S.chunk_lists(clause)))
    assert sum(map(len, S.chunk_lists(clause))) == len(IDS)


def test_search_sends_each_piece_its_shards_and_merges():
    calls = []

    def run_one(piece, index=None, shards=None):
        calls.append((index, shards))
        n = len(S._values(piece["query"]["bool"]["filter"][0]))
        return {"hits": {"total": {"value": n, "relation": "eq"}}, "aggregations": {"n": {"value": n}}}
    out = S.search(run_one, _body({"n": {"value_count": {"field": "id"}}}), route=_route)
    assert out["hits"]["total"]["value"] == len(IDS) and out["aggregations"]["n"]["value"] == len(IDS)
    assert len(calls) == S.ROUTE_PIECES and all(i == "works-v40" and p.startswith("_shards:") for i, p in calls)


COMP = {"s0": {"composite": {"size": 3, "sources": [{"k": {"terms": {"field": "primary_location.source.id"}}}],
                             "after": {"k": "S0"}},
               "aggs": {"c": {"sum": {"field": "cited_by_count"}}}}}


def _page(*rows):
    return {"buckets": [{"key": {"k": k}, "doc_count": n, "c": {"value": 10 * n}} for k, n in rows],
            "after_key": {"k": rows[-1][0]} if rows else None}


def test_a_composite_page_splits():
    p = S.plan(_body(COMP))
    assert p and p[0]["aggs"]["s0"]["composite"] == COMP["s0"]["composite"]   # same size, same after-key
    for bad in ({"order": "desc"}, {"missing_bucket": True}):
        src = {"k": {"terms": {"field": "type", **bad}}}
        assert S.plan(_body({"s0": {"composite": {"size": 3, "sources": [src]}}})) is None


def test_a_composite_page_merges_to_the_whole_sets_first_keys():
    # piece 1 holds S1 S2 S4 (full page), piece 2 holds S1 S3 (all it has); S5 may be missing from piece 1's page
    out = S.merge(_body(COMP), [
        {"hits": {"total": {"value": 9}}, "aggregations": {"s0": _page(("S1", 2), ("S2", 1), ("S4", 5))}},
        {"hits": {"total": {"value": 4}}, "aggregations": {"s0": _page(("S1", 1), ("S3", 3))}}])
    s0 = out["aggregations"]["s0"]
    assert [(b["key"]["k"], b["doc_count"], b["c"]["value"]) for b in s0["buckets"]] == [
        ("S1", 3, 30), ("S2", 1, 10), ("S3", 3, 30)]
    assert s0["after_key"] == {"k": "S3"}
    empty = S.merge(_body(COMP), [{"hits": {"total": {"value": 0}}, "aggregations": {"s0": _page()}}] * 2)
    assert empty["aggregations"]["s0"] == {"buckets": []}


def test_lists_keep_the_older_limit_and_calculations_take_more():
    from query_translation.oql_lang import parse
    q = "get works where it's cited by works in (get works where institution is (I146416000))"
    assert not parse(q).calculates and parse(q).runs_as_analytics
    assert parse(q + "; then summarize using count").calculates
    ctx = W.Ctx.__new__(W.Ctx)
    ctx.lists = True
    assert W._reads(ctx) is False                                   # a list never reads its set's references
    assert W._read_seconds(W.READ_REFS_MAX + 1) is None and W._read_seconds(None) is None
    assert 0 < W._read_seconds(1_200_000) < 8


def test_a_request_that_runs_whole_counts_its_work_ids():
    b = _body({"m": {"percentiles": {"field": "fwci"}}})
    b["query"]["bool"]["must_not"] = [S._terms("id", IDS[:10])]
    b["aggs"]["f"] = {"filter": S._terms("id", IDS[:5]), "aggs": {"t": {"terms": {"field": "id", "include": IDS[:3]}}}}
    assert S.id_terms(b) == len(IDS) + 15


def test_a_mean_splits_into_its_sum_and_count():
    aggs = {"s0": {"terms": {"field": "publication_year", "size": 5, "order": {"m": "desc"}},
                   "aggs": {"m": {"avg": {"field": "cited_by_count"}}}},
            "all": {"avg": {"field": "cited_by_count"}}}
    p = S.plan(_body(aggs))[0]["aggs"]
    assert p["all__sum"] == {"sum": {"field": "cited_by_count"}} and "all" not in p
    assert p["s0"]["aggs"] == {"m__sum": {"sum": {"field": "cited_by_count"}},
                               "m__n": {"value_count": {"field": "cited_by_count"}}}
    part = lambda yrs, s, n: {"hits": {"total": {"value": n}}, "aggregations": {   # noqa: E731
        "all__sum": {"value": s}, "all__n": {"value": n},
        "s0": {"sum_other_doc_count": 0, "buckets": [
            {"key": y, "doc_count": c, "m__sum": {"value": t}, "m__n": {"value": c}} for y, c, t in yrs]}}}
    out = S.merge(_body(aggs), [part([(2020, 2, 10), (2021, 1, 9)], 19, 3), part([(2020, 2, 2)], 2, 2)])["aggregations"]
    assert out["all"] == {"value": 21 / 5}
    assert [(b["key"], b["doc_count"], b["m"]["value"]) for b in out["s0"]["buckets"]] == [(2021, 1, 9.0), (2020, 4, 3.0)]
    assert S.plan(_body({"m": {"avg": {"field": "fwci", "missing": 0}}})) is None
