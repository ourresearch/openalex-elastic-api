"""Sets past 450,000 works (oxjob #1930): which shard holds a work, routed id-filter pieces, composite pages split
side by side, and the list guard."""
import pytest

from query_translation import id_split as S
from query_translation import shard_route as R
from query_translation import walk_exec as W
from query_translation.oqo import LeafFilter


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
    ctx = W.Ctx("walden", None, query=parse(q))
    assert ctx.lists and W._reads(ctx) is False                     # a list never reads its set's references
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


# ---------------------------------------------------------------------------
# Past the limits, a calculation's page view answers from a sample of the cited works (Jason, 2026-11-02)
# ---------------------------------------------------------------------------
def _calc(q):
    from query_translation.oql_lang import parse
    return parse(q)


SET = "get works where it's cited by works in (get works where institution is (I27837315))"


def test_scale_estimate_scales_counts_and_sums_only():
    oqo = _calc(SET + "; then group those works by type; then summarize using count, sum citation count, and mean FWCI")
    body = {"group_by": [{"count": 10, "key": "article", "sum_cited_by_count": 50.0, "mean_fwci": 1.5,
                          "groups": [{"count": 3, "key": "2020", "sum_cited_by_count": 9.0, "mean_fwci": None}]}],
            "summary": {"all": {"count": 12, "sum_cited_by_count": 60.0, "mean_fwci": 1.4},
                        "splits": [{"groups": [{"count": 10, "key": "article", "mean_fwci": 1.5}]}]},
            "meta": {"count": 12, "groups_count": 1, "rows_count": 1}}
    W.scale_estimate(body, oqo, {"share": 0.125, "works": 2_979_009})
    row = body["group_by"][0]
    assert (row["count"], row["sum_cited_by_count"], row["mean_fwci"]) == (80, 400.0, 1.5)
    assert (row["groups"][0]["count"], row["groups"][0]["sum_cited_by_count"]) == (24, 72.0)
    assert body["summary"]["all"] == {"count": 96, "sum_cited_by_count": 480.0, "mean_fwci": 1.4}
    assert body["summary"]["splits"][0]["groups"][0]["count"] == 80
    m = body["meta"]
    assert (m["count"], m["groups_count"], m["rows_count"]) == (96, 1, 1)
    assert m["estimate"]["sample_share"] == 0.125 and "1 in 8 of the 2,979,009 works" in m["estimate"]["message"]


@pytest.mark.parametrize("q, export, why", [
    ("; then group those works by type; then summarize using count and mean FWCI", False, None),
    ("; then group those works by type; then summarize using count", True, "export"),
    ("; then group those works by type; then summarize using max FWCI", False, "max"),
    ("; then get authors of those works; then get all those authors' works; then summarize using count", False,
     "walk"),
    ("", False, None),                 # a list: its count scales up (step 2)
    ("", True, "export"),
])
def test_what_a_sample_can_answer(q, export, why):
    got = W._why_not_estimable(_calc(SET + q), export)
    assert (got is None) if why is None else (why in got)


def test_a_cursor_page_is_never_estimated():
    from dataclasses import replace
    oqo = replace(_calc(SET + "; then group those works by type; then summarize using count"), cursor="*")
    assert "export" in W._why_not_estimable(oqo, False)


def test_only_a_set_anded_into_the_works_is_sampled():
    calc = "; then group those works by type; then summarize using count"
    ctx = W.Ctx("walden", None, query=_calc(SET + calc))
    assert W._cited_way(ctx, 3_000_000, 5_000_000, top=True) == "sample"
    assert W._cited_way(ctx, 3_000_000, 5_000_000, top=False) == "refuse"     # inside not, or, a split
    assert W._cited_way(ctx, 3_000_000, None, top=True) == "refuse"           # can't read references
    assert W._cited_way(ctx, 400_000, None, top=False) == "list"
    ctx.sampled = True
    assert W._cited_way(ctx, 3_000_000, 5_000_000, top=True) == "refuse"      # one sampled set a query
    sampled = W.IdSet(["https://openalex.org/W1"], "s", "cited_by", {"share": 0.1, "works": 3_000_000})
    from query_translation.oqo import BranchFilter
    pos = _calc(SET + calc).__class__(get_rows="works", filter_rows=[LeafFilter("ids.openalex", sampled, "in")])
    assert W.sample_of(pos) == {"share": 0.1, "works": 3_000_000}
    neg = pos.__class__(get_rows="works", filter_rows=[LeafFilter("ids.openalex", sampled, "in", True)])
    ored = pos.__class__(get_rows="works", filter_rows=[BranchFilter(
        join="or", filters=[LeafFilter("ids.openalex", sampled, "in"), LeafFilter("type", "article", "is")])])
    assert W.sample_of(neg) is None and W.sample_of(ored) is None


def test_list_keys_can_read_only_the_first_partitions():
    calls = []

    class Ctx:
        def search(self, body, what, **params):
            calls.append(body["aggs"]["k"]["terms"]["include"])
            assert params["filter_path"].startswith("aggregations.k.buckets.key")
            return {"aggregations": {"k": {"buckets": [{"key": f"W{len(calls)}"}]}}}
    keys = W.list_keys(Ctx(), {"match_all": {}}, "referenced_works", 3_000_000, "listing", first=W.SAMPLE_PARTS)
    assert len(keys) == W.SAMPLE_PARTS == len(calls)
    assert {c["num_partitions"] for c in calls} == {W._list_parts(3_000_000)}
    assert sorted(c["partition"] for c in calls) == list(range(W.SAMPLE_PARTS))


# ---------------------------------------------------------------------------
# Step 2: past the limit, a list's page answers from a sample of the cited works; its rows are its own first works
# where the set cites them, and a list of a few thousand works is checked whole
# ---------------------------------------------------------------------------
def _sampled(ids=("https://openalex.org/W1", "https://openalex.org/W2"), share=0.1):
    return W.IdSet(list(ids), "s", "cited_by", {"share": share, "works": 3_000_000, "set_query": {"match_all": {}}})


def test_a_list_can_be_sampled_unless_it_groups_samples_or_searches_semantically():
    from dataclasses import replace
    from query_translation.oqo import GroupBy
    oqo = _calc(SET)
    assert not oqo.calculates and W._why_not_estimable(oqo, False) is None
    assert "groups" in W._why_not_estimable(replace(oqo, group_by=[GroupBy(column_id="type")]), False)
    assert "random sample" in W._why_not_estimable(replace(oqo, sample=100), False)
    sem = replace(oqo, filter_rows=oqo.filter_rows + [
        LeafFilter("title_and_abstract.search.semantic", "folding", "is")])
    assert "semantic" in W._why_not_estimable(sem, False)
    assert W._why_not_estimable(None, False)


class _FakeSearch:
    """A Ctx.search answering the list resolver's calls: the references total, the distinct count, partitions."""

    def __init__(self, refs, est, per_part=3):
        self.refs, self.est, self.per_part, self.calls = refs, est, per_part, []

    def __call__(self, body, what, index=None, **params):
        aggs = body.get("aggs") or {}
        if "refs" in aggs:
            self.calls.append("refs")
            return {"aggregations": {"refs": {"value": self.refs}}}
        if "n" in aggs:
            self.calls.append("distinct")
            return {"hits": {"total": {"value": 1}}, "aggregations": {"n": {"value": self.est}}}
        inc = aggs["k"]["terms"]["include"]
        self.calls.append(("part", inc["partition"], inc["num_partitions"]))
        return {"aggregations": {"k": {"buckets": [{"key": f"W{inc['partition']}-{i}"}
                                                   for i in range(self.per_part)]}}}


def _list_ctx(fake, export=False, calc=""):
    ctx = W.Ctx("walden", None, query=_calc(SET + calc), export=export)
    ctx.search = fake
    return ctx


def test_a_big_set_is_sampled_without_counting_its_works():
    for calc in ("", "; then group those works by type; then summarize using count"):   # a list, a calculation
        fake = _FakeSearch(refs=20_000_000, est=None, per_part=4_000)
        ctx = _list_ctx(fake, calc=calc)
        ids, sample = W._list_or_sample_cited(ctx, {"match_all": {}}, 20_000_000, True, "listing")
        parts = W._list_parts(20_000_000 * W.MAX_DISTINCT_SHARE)
        assert "distinct" not in fake.calls                       # the references total sizes the partitions
        assert {c[2] for c in fake.calls if c[0] == "part"} == {parts}
        assert len(ids) == 4_000 * W.SAMPLE_PARTS and ctx.sampled
        assert sample == {"share": W.SAMPLE_PARTS / parts, "works": round(len(ids) * parts / W.SAMPLE_PARTS),
                          "set_query": {"match_all": {}}}


def test_a_set_naming_few_works_is_listed_whole_after_all():
    fake = _FakeSearch(refs=20_000_000, est=None, per_part=1)   # 1 id a partition: a few hundred works in all
    ctx = _list_ctx(fake)
    ids, sample = W._list_or_sample_cited(ctx, {"match_all": {}}, 20_000_000, True, "listing")
    assert sample is None and not ctx.sampled
    assert fake.calls[-1][2] == W._list_parts(W._list_parts(20_000_000 * W.MAX_DISTINCT_SHARE))


def test_a_middling_set_is_counted_then_sampled_or_listed():
    fake = _FakeSearch(refs=1_200_000, est=660_000)
    ids, sample = W._list_or_sample_cited(_list_ctx(fake), {"match_all": {}}, 1_200_000, True, "listing")
    assert fake.calls[0] == "distinct"
    assert sample["share"] == W.SAMPLE_PARTS / W._list_parts(660_000)
    fake = _FakeSearch(refs=600_000, est=300_000)
    ids, sample = W._list_or_sample_cited(_list_ctx(fake), {"match_all": {}}, 600_000, True, "listing")
    assert sample is None and len([c for c in fake.calls if c[0] == "part"]) == W._list_parts(300_000)


def test_a_list_export_or_a_set_inside_not_is_refused_with_its_reason():
    from query_translation import analytics as A
    for ctx, top, why in ((_list_ctx(_FakeSearch(20_000_000, 9_000_000), export=True), True, "export"),
                          (_list_ctx(_FakeSearch(20_000_000, 9_000_000)), False, "`not`")):
        with pytest.raises(A.AnalyticsError) as e:
            W._list_or_sample_cited(ctx, {"match_all": {}}, 20_000_000, top, "listing")
        assert e.value.message.startswith("This list needs about 9,000,000 works") and why in e.value.message
        assert "a list holds up to 450,000 exactly" in e.value.message


def test_without_and_thin_sample_touch_only_the_sampled_set():
    from query_translation.oqo import OQO, BranchFilter
    sampled, kept = LeafFilter("ids.openalex", _sampled(), "in"), LeafFilter("type", "article", "is")
    oqo = OQO(get_rows="works", filter_rows=[BranchFilter(join="and", filters=[sampled, kept])])
    assert W.without_sample(oqo).filter_rows == [BranchFilter(join="and", filters=[kept])]
    assert W.without_sample(OQO(get_rows="works", filter_rows=[sampled])).filter_rows == []
    neg = OQO(get_rows="works", filter_rows=[LeafFilter("ids.openalex", _sampled(), "in", True)])
    assert W.without_sample(neg) == neg
    many = [f"https://openalex.org/W{i}" for i in range(4_000)]
    thin, k = W.thin_sample(OQO(get_rows="works", filter_rows=[LeafFilter("ids.openalex", _sampled(many), "in"),
                                                               kept]), 1_000)
    s = thin.filter_rows[0].value
    assert k == 4 and 800 < len(s) < 1_200 and set(s.ids) <= set(many) and s.sample["share"] == 0.1
    assert thin.filter_rows[1] == kept
    thin, k = W.thin_sample(oqo, 1_000)
    assert k == 1 and thin.filter_rows[0].filters[0].value.ids == _sampled().ids


def test_cited_first_checks_a_round_then_more_only_when_it_can_fill_the_page(monkeypatch):
    ids = [f"W{i}" for i in range(1_000)]
    checked = []

    def with_cited(cited):
        def fake(connection, deadline, set_query, part):
            checked.append(len(part))
            return [w for w in part if w in cited]
        monkeypatch.setattr(W, "cited_by_set", fake)
    with_cited(set(ids[::2]))
    assert W.cited_first(None, None, {}, ids, 25) == ids[:W.MEMBER_PIECE:2]
    assert checked == [W.MEMBER_PIECE]                            # one round: 63 of the first 125 cited
    checked.clear()
    with_cited(set(ids[:5]) | set(ids[200::4]))     # 5 of the first 125: at that rate the rest makes up 25
    got = W.cited_first(None, None, {}, ids, 25)
    assert len(got) >= 25 and got[:5] == ids[:5] and checked == [W.MEMBER_PIECE, 1_000 - W.MEMBER_PIECE]
    checked.clear()
    with_cited(set(ids[:3]) | set(ids[200::4]))     # 3 of 125: 24 at most at that rate, so the sample's rows
    assert W.cited_first(None, None, {}, ids, 25) is None and checked == [W.MEMBER_PIECE]
    checked.clear()
    with_cited(set())
    assert W.cited_first(None, None, {}, ids, 25) is None and checked == [W.MEMBER_PIECE]   # no second round


def test_cited_by_set_counts_one_bucket_a_work_in_pieces(monkeypatch):
    from query_translation import analytics as A
    bodies = []

    def search(index, connection, body, deadline, what, **params):
        bodies.append(body)
        f = body["aggs"]["m"]["filters"]["filters"]
        return {"aggregations": {"m": {"buckets": {k: {"doc_count": int(v["term"]["referenced_works"].endswith("7"))}
                                                   for k, v in f.items()}}}}
    monkeypatch.setattr(A, "_search", search)
    ids = [f"https://openalex.org/W{i}" for i in range(300)]
    got = W.cited_by_set("walden", None, {"term": {"type": "review"}}, ids)
    assert got == [w for w in ids if w.endswith("7")]               # in the list's order
    assert sorted(len(b["aggs"]["m"]["filters"]["filters"]) for b in bodies) == [50, 125, 125]
    assert all(b["query"] == {"term": {"type": "review"}} and b["size"] == 0 for b in bodies)


def test_label_list_scales_the_count_and_gives_its_margin():
    meta = {}
    W.label_list(meta, {"share": 0.02, "works": 10_500_000}, 200_000, None)
    assert meta["count"] == 10_000_000 and meta["approximate"] is True
    e = meta["estimate"]
    assert e["rows"] == "first" and e["count_margin"] == round(1.96 * (200_000 * 0.98) ** 0.5 * 50)
    assert "1 in 50 of the 10,500,000 works" in e["message"] and "the rows are exact" in e["message"]
    assert f"give or take {e['count_margin']:,}" in e["message"]
    W.label_list(meta, {"share": 0.02, "works": 10_500_000}, 200_000, 14)
    assert meta["estimate"]["rows"] == "sample"
    assert "a random 1 in 700 of the list's works" in meta["estimate"]["message"]


def test_a_calculation_estimate_gives_its_count_margin_too():
    body = {"meta": {"count": 12, "groups_count": None}, "group_by": [], "summary": {"all": {"count": 12}}}
    W.scale_estimate(body, _calc(SET + "; then summarize using count"), {"share": 0.125, "works": 2_979_009})
    e = body["meta"]["estimate"]
    assert body["meta"]["count"] == 96 and e["count_margin"] == round(1.96 * (12 * 0.875) ** 0.5 * 8)
    assert e["message"] == ("Estimated from a random 1 in 8 of the 2,979,009 works the set in parentheses cites: "
                            "counts and sums are scaled up, means and percents are the sample's. Narrow the set for "
                            "exact numbers.")
