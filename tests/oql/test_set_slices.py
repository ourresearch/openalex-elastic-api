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
        self.refs, self.est, self.per_part, self.parts = refs, est, per_part, []

    def __call__(self, body, what, index=None, **params):
        aggs = body.get("aggs") or {}
        if "refs" in aggs:
            return {"aggregations": {"refs": {"value": self.refs}}}
        if "n" in aggs:
            return {"hits": {"total": {"value": 1}}, "aggregations": {"n": {"value": self.est}}}
        inc = aggs["k"]["terms"]["include"]
        self.parts.append((inc["partition"], inc["num_partitions"]))
        return {"aggregations": {"k": {"buckets": [{"key": f"W{inc['partition']}-{i}"}
                                                   for i in range(self.per_part)]}}}


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
        ids = W.slice_cited(ctx, {"match_all": {}}, 5_400_000, True, "listing")
        assert ctx.sliced and len(ids) == 3 * W.SLICE_PARTS
        assert {n for _, n in fake.parts} == {3 * W.SLICE_PARTS}
        seen += [p for p, _ in fake.parts]
    assert sorted(seen) == list(range(3 * W.SLICE_PARTS))


def test_a_slice_applies_once_to_a_set_anded_into_the_works():
    ctx = _ctx(_Fake(5_400_000, None), slice=(1, 3))
    with pytest.raises(A.AnalyticsError) as e:
        W.slice_cited(ctx, {"match_all": {}}, 5_400_000, False, "listing")
    assert e.value.code == "invalid_slice" and "`not`" in e.value.message
    W.slice_cited(ctx, {"match_all": {}}, 5_400_000, True, "listing")
    with pytest.raises(A.AnalyticsError) as e:
        W.slice_cited(ctx, {"match_all": {}}, 5_400_000, True, "listing")
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
    assert set(W.SLICE_RULES) - {"values"} <= set(MEASURES)
    assert {m for m in MEASURES if m not in W.SLICE_RULES} == {"median", "percent_of_those"}


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
