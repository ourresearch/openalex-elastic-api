"""Exact exports of a set too big for one request, in slices (oxjob #1930, step 4): `set_slice=s/S` resolves the set
to exactly its SLICE_PARTS of S x SLICE_PARTS hash partitions, each slice answers with the helper columns it adds up
by, and X-Set-Merge says how."""
import pytest

from query_translation import analytics as A
from query_translation import analytics_csv as C
from query_translation import walk_exec as W
from query_translation.oql_lang import parse
from query_translation.oqo import BranchFilter, LeafFilter, Measure

SET = "get works where it's cited by works in (get works where institution is (I27837315))"
BY_SOURCE = "; then group those works by source; then summarize using count"


class _Fake:
    """A Ctx.search for the cited-by resolver: the references total, the distinct count, hash partitions."""

    def __init__(self, refs, est, per_part=3):
        self.refs, self.est, self.per_part, self.parts, self.asked = refs, est, per_part, [], 0

    def __call__(self, body, what, index=None, **params):
        self.asked += 1
        aggs = body.get("aggs") or {}
        if "refs" in aggs:
            return {"aggregations": {"refs": {"value": self.refs}}}
        if "n" in aggs:
            return {"hits": {"total": {"value": 1}}, "aggregations": {"n": {"value": self.est}}}
        inc = aggs["k"]["terms"]["include"]
        self.parts.append((inc["partition"], inc["num_partitions"]))
        return {"aggregations": {"k": {"buckets": [{"key": f"W{inc['partition']}-{i}"}
                                                   for i in range(self.per_part)]}}}


class _Cache:
    def __init__(self, broken=False):
        self.data, self.broken = {}, broken

    def get(self, key):
        if self.broken:
            raise ConnectionError("no cache")
        return self.data.get(key)

    def set(self, key, value, timeout=None):
        if self.broken:
            raise ConnectionError("no cache")
        self.data[key] = value



@pytest.fixture(autouse=True)
def _own_cache(monkeypatch):
    """Each test its own empty shared cache (a slice's ids are kept there, #2016), and sets read as a calculation's."""
    import extensions
    monkeypatch.setattr(extensions, "cache", _Cache())
    monkeypatch.setattr(W, "_reads", lambda ctx: True)


def _ctx(fake, calc=BY_SOURCE, export=True, slice=None):
    ctx = W.Ctx("walden", None, query=parse(SET + calc), export=export, slice=slice)
    ctx.search = fake
    return ctx


@pytest.mark.parametrize("text, want", [(None, None), ("", None), ("1/9", (1, 9)), ("9/9", (9, 9))])
def test_parse_slice(text, want):
    assert W.parse_slice(text) == want


@pytest.mark.parametrize("text", ["0/9", "10/9", "a/b", "3", "1/2/3", "-1/4"])
def test_parse_slice_refuses_a_bad_value(text):
    with pytest.raises(A.AnalyticsError) as e:
        W.parse_slice(text)
    assert e.value.code == "invalid_slice"


def test_an_export_of_a_set_too_big_to_hold_names_its_slices():
    fake = _Fake(refs=5_400_000, est=2_980_000)
    with pytest.raises(A.AnalyticsError) as e:
        W._list_or_sample_cited(_ctx(fake), {"match_all": {}}, 5_400_000, True, "listing")
    assert e.value.code == W.SLICE_ERROR
    assert e.value.slices == W.slices_for(2_980_000) == 9     # Michigan's 69 partitions, 8 a slice
    assert "set_slice=1/9 through set_slice=9/9" in e.value.message and "X-Set-Merge" in e.value.message
    assert not fake.parts                                      # refused before listing anything


@pytest.mark.parametrize("calc, top, why", [
    ("", True, "a list exports"),
    ("; then group those works by source; then summarize using median FWCI", True, "median can't be added up"),
    ("; then group those works by source; then summarize using count and percent of those works", True,
     "percent of those can't be added up"),
    (BY_SOURCE, False, "inside `not`"),
])
def test_what_cant_be_sliced_is_refused_with_its_reason(calc, top, why):
    with pytest.raises(A.AnalyticsError) as e:
        W._list_or_sample_cited(_ctx(_Fake(5_400_000, 2_980_000), calc=calc), {"match_all": {}}, 5_400_000, top,
                                "listing")
    assert e.value.code == "query_too_slow" and why in e.value.message
    assert not getattr(e.value, "slices", None)


def test_the_slices_cover_every_partition_once():
    seen = []
    for s in range(1, 4):
        fake = _Fake(refs=5_400_000, est=None)
        ctx = _ctx(fake, slice=(s, 3))
        ids = W.slice_cited(ctx, {"match_all": {}}, True, "listing")
        assert ctx.sliced and len(ids) == 3 * W.SLICE_PARTS
        assert {n for _, n in fake.parts} == {3 * W.SLICE_PARTS}
        seen += [p for p, _ in fake.parts]
    assert sorted(seen) == list(range(3 * W.SLICE_PARTS))


def test_a_slice_applies_once_to_a_set_anded_into_the_works():
    ctx = _ctx(_Fake(5_400_000, None), slice=(1, 3))
    with pytest.raises(A.AnalyticsError) as e:
        W.slice_cited(ctx, {"match_all": {}}, False, "listing")
    assert e.value.code == "invalid_slice" and "`not`" in e.value.message
    W.slice_cited(ctx, {"match_all": {}}, True, "listing")
    with pytest.raises(A.AnalyticsError) as e:
        W.slice_cited(ctx, {"match_all": {}}, True, "listing")
    assert "only one set" in e.value.message


def test_a_list_or_a_walk_is_never_sliced():
    for q in (SET, SET + "; then get authors of those works; then get all those authors' works; then summarize "
                    "using count"):
        with pytest.raises(A.AnalyticsError) as e:
            W.prepare(parse(q), "walden", A.Deadline(), export=True, slice=(1, 3))
        assert e.value.code == "invalid_slice"


def test_a_slice_is_never_the_whole_answer(client):
    """set_slice on a query with no set to slice refuses (before anything runs): summing S copies of the whole
    answer would be wrong."""
    for params in ("format=csv&set_slice=1/3", "set_slice=1/3"):
        r = client.post(f"/?{params}", json={"oql": "get works where type is article" + BY_SOURCE})
        assert r.status_code == 400 and r.get_json()["error"] == "invalid_slice", r.data[:300]


def test_slice_of_finds_the_sliced_set():
    sliced = W.IdSet(["https://openalex.org/W1"], "s", "cited_by", slice=(2, 9))
    pos = parse(SET).__class__(get_rows="works", filter_rows=[LeafFilter("ids.openalex", sliced, "in")])
    assert W.slice_of(pos) == (2, 9)
    ored = pos.__class__(get_rows="works", filter_rows=[BranchFilter(
        join="or", filters=[LeafFilter("ids.openalex", sliced, "in"), LeafFilter("type", "article", "is")])])
    assert W.slice_of(ored) is None


def test_a_slice_adds_the_helpers_its_measures_add_up_by():
    asked = [Measure("percent", "open_access.is_oa"), Measure("mean", "fwci"), Measure("sum", "fwci")]
    run = W.slice_measures(asked)
    assert run == asked + [Measure("count"), Measure("values", "fwci")]
    body = {"meta": {"splits": [], "measures": [A._measure_meta(m, "works") for m in run]}}
    rules = C.merge_rules(body, parse(SET + BY_SOURCE), asked, (2, 9))
    assert rules["slice"] == [2, 9]
    assert rules["add"] == ["sum FWCI", "count", "works with FWCI"]
    assert rules["percent"] == {"percent open access": "count"}
    assert rules["mean"] == {"mean FWCI": ["sum FWCI", "works with FWCI"]}
    assert rules["drop"] == ["count", "works with FWCI"]       # the sum was asked for: kept


def test_every_sliceable_measure_has_a_rule_and_the_rest_refuse():
    from query_translation.oqo import MEASURES
    assert set(W.SLICEABLE) - {"values"} <= set(MEASURES)
    assert {m for m in MEASURES if m not in W.SLICEABLE} == {"median", "percent_of_those"}


def test_a_slice_costs_its_share_of_the_export():
    assert A.export_price({"credits": 18}, 25_000)["credits"] == 18 * 250
    assert A.export_price({"credits": 18}, 25_000, slices=9)["credits"] == 18 * 250 // 9
    assert A.export_price({"credits": 1}, 5, slices=9)["credits"] == 1      # never free


def test_a_count_of_values_is_a_value_count():
    from works.fields import fields_dict
    assert A._measure_aggs([Measure("values", "fwci")], fields_dict) == {
        "m_values_fwci": {"value_count": {"field": "fwci"}}}


def _body(splits, measures):
    return {"meta": {"splits": splits, "measures": [{"key": k, "oql": o} for k, o in measures]}}


SOURCE = {"oql": "source", "kind": "column", "has_ids": True, "key_order": "id"}
YEAR = {"oql": "year", "kind": "column", "has_ids": False, "key_order": "year"}
TYPE = {"oql": "type", "kind": "values", "has_ids": True, "key_order": None}


@pytest.mark.parametrize("splits, sort, want", [
    ([SOURCE], None, [["source id", "asc"]]),     # as a whole export's cursor pages it
    ([YEAR], None, [["year", "asc"]]),
    ([YEAR, SOURCE], None, [["year", "asc"], ["count", "desc"], ["source id", "asc"]]),
    ([TYPE], None, [["type", "seen"]]),
    ([SOURCE], "sum_cited_by_count", [["source id", "asc"]]),
    ([YEAR, SOURCE], "sum_cited_by_count", [["year", "asc"], ["sum citations", "asc"], ["source id", "asc"]]),
])
def test_merge_order_reads_like_the_page(splits, sort, want):
    from dataclasses import replace
    from query_translation.oqo import SortBy
    oqo = parse(SET + BY_SOURCE)
    if sort:
        oqo = replace(oqo, sort_by=[SortBy(column_id=sort, direction="asc")])
    body = _body(splits, [("count", "count"), ("sum_cited_by_count", "sum citations")])
    assert C.merge_order(body, oqo) == want


# A set of 450K-1M cited works (oxjob #2016): read whole, but a request that can't run in pieces (a nested split, a
# median) can't send that many ids to every shard. An export that can slice asks for its slices instead of refusing.
NESTED = "; then group those works by year and type; then summarize using count and percent open access"


def _read_env(monkeypatch, n):
    import numpy as np
    import elasticsearch_dsl.connections as Conn
    from query_translation import shard_route
    monkeypatch.setattr(Conn, "get_connection", lambda name=None: None)
    monkeypatch.setattr(shard_route, "routing", lambda es, index: ("works-v40", 72, 576))
    monkeypatch.setattr(W, "_pmap", lambda fn, items, inflight=None: [np.arange(1, n + 1, dtype=np.int64)])


MEDIAN = "; then group those works by year; then summarize using median FWCI"


@pytest.mark.parametrize("n, calc, export, top, want", [
    # KU's 2020+ set: an export comes in 2 slices
    (661_784, NESTED, True, True, (W.SLICE_ERROR, 2, "Export it from the website", False)),
    # a page view answers from a sample (thin_set); if it can't, its refusal says an export answers it
    (661_784, NESTED, False, True, ("query_too_slow", None, "Export it: an export", True)),
    (661_784, MEDIAN, False, True, ("query_too_slow", None, "Narrow", True)),   # a median: no slices, a sample
    (661_784, NESTED, True, False, None),        # a set inside `not` or `or` can't be sliced
    (661_784, MEDIAN, True, True, None),         # a median's export: refused as before
    (400_000, NESTED, True, True, None),         # under the limit: sent whole, no slices
    (400_000, NESTED, False, True, None),
])
def test_reading_a_set_past_the_whole_limit_arms_a_better_answer(monkeypatch, n, calc, export, top, want):
    _read_env(monkeypatch, n)
    ctx = W.Ctx("walden", A.Deadline(), query=parse(SET + calc), export=export)
    assert len(W.read_cited(ctx, {"match_all": {}}, "reading", top=top)) == n
    got = ctx.deadline.whole_refusal and ctx.deadline.whole_refusal()
    assert (got and (got.code, got.slices, got.fix[:len(want[2])], got.sample)) == want


def _resolved(n, calc=NESTED):
    """`SET + calc` as prepare resolves it: its set read whole, `n` cited works."""
    from dataclasses import replace
    oqo = parse(SET + calc)
    ids = W.IdSet([f"https://openalex.org/W{i}" for i in range(n)], "the set", "cited_by")
    return replace(oqo, filter_rows=[LeafFilter("ids.openalex", ids, "in")]), ids


def test_thin_set_keeps_a_uniform_sample_small_enough_to_send_whole(monkeypatch):
    monkeypatch.setattr(W, "MAX_SET_IDS", 500)
    monkeypatch.setattr(W, "THIN_IDS", 200)
    oqo, ids = _resolved(1_000)
    assert W.thin_set(oqo)
    assert ids.sample == {"share": 0.2, "works": 1_000, "export": True}       # 1 in 5; its export comes in slices
    assert 150 < len(ids) < 250 and set(ids.ids) < {f"https://openalex.org/W{i}" for i in range(1_000)}
    assert not W.thin_set(oqo)                                                # once
    assert not W.thin_set(_resolved(400)[0])                                  # small enough already
    median, _ = _resolved(1_000, MEDIAN)
    assert W.thin_set(median) and W.sample_of(median)["export"] is False      # a median's export can't slice


def test_an_estimate_an_export_answers_exactly_says_so():
    body = {"meta": {"count": 12, "groups_count": None}, "group_by": [], "summary": {"all": {"count": 12}}}
    W.scale_estimate(body, parse(SET + "; then summarize using count"), {"share": 0.25, "works": 661_784,
                                                                          "export": True})
    assert body["meta"]["estimate"]["message"].endswith("Export it or narrow the set for exact numbers.")


def test_a_page_view_refused_for_its_whole_set_answers_from_a_sample(monkeypatch, client):
    """The run (analytics.run) refuses a request it can't send whole; the page view runs once more on a sample of
    the set, scaled up and labeled (oxjob #2016). users-api's export check reads this page, so the export starts."""
    monkeypatch.setattr(W, "MAX_SET_IDS", 500)
    monkeypatch.setattr(W, "THIN_IDS", 200)
    resolved, ids = _resolved(1_000)
    monkeypatch.setattr(W, "prepare", lambda oqo, *a, **k: ("oqo", resolved))
    sent = []

    def run(oqo, base_query=None, deadline=None, **kw):
        sent.append(str(base_query).count("https://openalex.org/W"))
        if len(sent) == 1:
            raise A.too_whole(1_000, export_it=True, sample=True)
        return {"group_by": [{"key": "2020", "key_display_name": "2020", "count": 10, "groups": []}],
                "summary": {"all": {"count": 10}}, "meta": {"count": 10, "groups_count": 1, "es_calls": 3}}
    monkeypatch.setattr(A, "run", run)
    r = client.post("/", json={"oql": SET + NESTED})
    assert r.status_code == 200, r.data[:400]
    assert sent[0] == 1_000 and 150 < sent[1] < 250                          # the second run sent the sample
    m = r.get_json()["meta"]
    assert m["count"] == 50 and m["estimate"]["sample_share"] == 0.2 and m["approximate"] is True
    assert r.get_json()["group_by"][0]["count"] == 50


def test_a_request_too_big_to_send_whole_asks_for_slices_when_armed(monkeypatch):
    import elasticsearch_dsl.connections as Conn

    class Es:
        def search(self, **params):
            raise AssertionError("never sent")
    monkeypatch.setattr(Conn, "get_connection", lambda name=None: Es())
    # a nested terms split: id_split can't run it in pieces
    body = {"size": 0, "query": {"bool": {"filter": [W._terms("id", [f"W{i}" for i in range(W.MAX_SET_IDS + 1)])]}},
            "aggs": {"y": {"terms": {"field": "publication_year"}, "aggs": {"t": {"terms": {"field": "type"}}}}}}
    deadline = A.Deadline()
    with pytest.raises(A.AnalyticsError) as e:
        A._search("works-test", "walden", body, deadline, "splitting")
    assert e.value.code == "query_too_slow" and "every shard at once" in e.value.message
    assert e.value.fix.startswith("Narrow")
    deadline.whole_refusal = lambda: W._slices_refusal(661_784)
    raised = []
    for _ in range(2):
        with pytest.raises(A.AnalyticsError) as e:
            A._search("works-test", "walden", body, deadline, "splitting")
        assert e.value.code == W.SLICE_ERROR and e.value.slices == 2
        raised.append(e.value)
    assert raised[0] is not raised[1]       # a fresh error each time: a re-raised one keeps its frames alive


def test_the_slices_ride_every_error_answer():
    """Whichever handler answers the refusal (set resolution or the calculation's run), its JSON names the slices
    users-api's export worker asks for."""
    assert W._slices_refusal(661_784).to_dict()["slices"] == 2
    assert 661_784 / 2 < W.MAX_SET_IDS                   # each of KU's 2 slices is small enough to send whole
    assert "slices" not in A.AnalyticsError("query_too_slow", "m", "f").to_dict()


# A slice's ids are listed once and kept in the shared cache for the slice's other pages (oxjob #2016).
class _Ids(_Fake):
    """Partitions of real-looking work ids (W<partition><i>), so they can be kept."""

    def __call__(self, body, what, index=None, **params):
        got = super().__call__(body, what, index, **params)
        for b in got.get("aggregations", {}).get("k", {}).get("buckets", []):
            p, i = b["key"][1:].split("-")
            b["key"] = f"https://openalex.org/W{int(p) * 1000 + int(i) + 1}"
        return got


def _slice_pages(monkeypatch, cache, pages=3, s=2, S=3):
    import extensions
    monkeypatch.setattr(extensions, "cache", cache)
    out = []
    for _ in range(pages):
        fake = _Ids(refs=5_400_000, est=None)
        ctx = W.Ctx("walden", A.Deadline(), query=parse(SET + BY_SOURCE), export=True, slice=(s, S))
        ctx.search = fake
        ids = W.slice_cited(ctx, {"term": {"type": "article"}}, True, "listing")
        out.append((ids, fake.asked, ctx.deadline.calls))
    return out


def test_a_slice_is_listed_once_across_its_pages(monkeypatch):
    cache = _Cache()
    (first, listed, calls), *rest = _slice_pages(monkeypatch, cache)
    assert listed == W.SLICE_PARTS + 1 and len(first) == W.SLICE_PARTS * 3       # its references count, its listing
    assert first == sorted(first, key=lambda w: int(w.rsplit("W", 1)[1]))      # in work order, every page alike
    assert all(ids == first and n == 0 for ids, n, _ in rest)                   # the same works, nothing asked
    assert all(c == listed for _, _, c in rest)                                 # priced as the calls they replace
    assert len(cache.data) == 1
    _slice_pages(monkeypatch, cache, pages=1, s=3)                               # another slice: its own entry
    assert len(cache.data) == 2


def test_a_slice_is_listed_every_time_without_a_cache(monkeypatch):
    assert [n for _, n, _ in _slice_pages(monkeypatch, _Cache(broken=True), pages=2)] == [W.SLICE_PARTS + 1] * 2


def test_a_slice_with_an_id_that_isnt_a_work_isnt_kept(monkeypatch):
    import extensions

    class Odd(_Ids):
        def __call__(self, body, what, index=None, **params):
            got = super().__call__(body, what, index, **params)
            for b in got.get("aggregations", {}).get("k", {}).get("buckets", [])[:1]:
                b["key"] = "https://openalex.org/A1"
            return got
    cache = _Cache()
    monkeypatch.setattr(extensions, "cache", cache)
    ctx = W.Ctx("walden", A.Deadline(), query=parse(SET + BY_SOURCE), export=True, slice=(1, 3))
    ctx.search = Odd(refs=5_400_000, est=None)
    assert "https://openalex.org/A1" in W.slice_cited(ctx, {"match_all": {}}, True, "listing")
    assert not cache.data


def test_one_table_says_how_each_measure_behaves_in_parts():
    """measure_parts (#2016): the sample, slice and id-filter piece rules all read one table; these are the rules
    #1930 shipped as three separate tables."""
    from query_translation import id_split
    from query_translation.measure_parts import AGG_MERGE, MEASURE_PARTS
    from query_translation.oqo import MEASURES
    assert set(MEASURE_PARTS) == set(MEASURES) | {"values"}
    assert set(W.ESTIMABLE) == {"count", "sum", "mean", "median", "percent", "percent_of_those", "value"}
    assert {m: (p.merge, p.helpers) for m, p in MEASURE_PARTS.items() if m in W.SLICEABLE} == {
        "count": ("add", ()), "sum": ("add", ()), "values": ("add", ()),
        "min": ("min", ()), "max": ("max", ()), "value": ("first", ()),
        "percent": ("percent", (("count", False),)),
        "mean": ("mean", (("sum", True), ("values", True)))}
    assert AGG_MERGE == {"sum": "add", "value_count": "add", "avg": "mean", "min": "min", "max": "max"}
    # a median's percentiles can't merge: a request with one runs whole
    with pytest.raises(id_split.Whole):
        id_split._piece_aggs({"m": {"percentiles": {"field": "fwci", "percents": [50]}}})
    assert id_split._piece_aggs({"m": {"avg": {"field": "fwci"}}, "n": {"max": {"field": "fwci"}}}) == {
        "m__sum": {"sum": {"field": "fwci"}}, "m__n": {"value_count": {"field": "fwci"}},
        "n": {"max": {"field": "fwci"}}}
    from works.fields import fields_dict
    assert A._measure_aggs([Measure("mean", "fwci"), Measure("max", "fwci")], fields_dict) == {
        "m_mean_fwci": {"avg": {"field": "fwci"}}, "m_max_fwci": {"max": {"field": "fwci"}}}
