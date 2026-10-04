"""Pure parts of the pipeline engine (oxjob #1530): bin labels, group-filter scripts,
plan prices, cursors. The live checks (every #1512 example against independent ES
queries) are in the job: work/scripts/verify.py."""
import pytest

from query_translation import analytics as A
from query_translation.oql_lang import parse
from query_translation.oqo import BranchFilter, Measure, MeasureFilter
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _oqo(q):
    return canonicalize_oqo(parse(q))


@pytest.mark.parametrize("col,edges,is_float,labels", [
    ("cited_by_count", [1, 10, 100], False, ["0", "1-9", "10-99", "100+"]),
    ("cited_by_count", [5, 10], False, ["0-4", "5-9", "10+"]),
    ("publication_year", [2000, 2010], False, ["under 2000", "2000-2009", "2010+"]),
    ("fwci", [0.5, 1, 2], True, ["under 0.5", "0.5-1", "1-2", "2+"]),
])
def test_bin_labels(col, edges, is_float, labels):
    assert A._bin_labels(col, edges, is_float) == labels


def test_selector_script_for_a_measure_tree():
    tree = BranchFilter("and", [
        MeasureFilter("count", ">", 10),
        MeasureFilter("mean", ">=", 2, column_id="fwci"),
        MeasureFilter("percent", "<", 50, column_id="open_access.is_oa", is_negated=True),
        MeasureFilter("median", ">", 3, column_id="cited_by_count"),
    ])
    paths, script = A._selector_script(tree)
    assert paths["c"] == "_count"
    assert paths["v_mean_fwci"] == "m_mean_fwci"
    assert paths["t_percent_open_access_is_oa"] == "m_percent_open_access_is_oa>_count"
    assert paths["v_median_cited_by_count"] == "m_median_cited_by_count[50.0]"
    assert "params.c > 10.0" in script and "&&" in script and "!(" in script


def test_min_doc_count_from_a_count_filter():
    assert A._min_doc_count(MeasureFilter("count", ">", 10)) == 11
    assert A._min_doc_count(MeasureFilter("count", ">=", 10)) == 10
    assert A._min_doc_count(BranchFilter("and", [MeasureFilter("count", ">", 3),
                                                 MeasureFilter("count", ">=", 8)])) == 8
    assert A._min_doc_count(MeasureFilter("mean", ">", 1, column_id="fwci")) == 1


def test_split_where_separates_measures_from_own_fields():
    oqo = _oqo("get works where year > (2020); then group those works by author where "
               "count of those works > (10) and h-index > (20)")
    m, k = A._split_where(oqo.group_by[0].where)
    assert len(m) == 1 and len(k) == 1


def test_split_where_refuses_an_or_mixing_kinds():
    oqo = _oqo("get works where year > (2020); then group those works by author where "
               "count of those works > (10) or h-index > (20)")
    with pytest.raises(A.AnalyticsError) as ei:
        A._split_where(oqo.group_by[0].where)
    assert ei.value.code == "group_filter_mix" and ei.value.fix


@pytest.mark.parametrize("q,credits", [
    ("get works where year > (2020); then group those works by year; then calculate count", 1),
    ("get works where title-abstract has (kelp); then group those works by year; then "
     "calculate count", 10),
    ('get works where year > (2020); then group those works by title-abstract search in '
     '(("a"), ("b"), ("c")); then calculate count', 31),
    ("get works where title-abstract has (kelp); then group those works by author where "
     "count of those works > (10) and h-index > (20) and co-author is not (A1)", 12),
    ("get works where year > (2020); then group those works by author where that author "
     "is in (A1, A2)", 1),
    ("get works where year > (2020); then group those works into ((title has (a)), "
     "(year > (2021))); then calculate count", 11),
])
def test_price(q, credits):
    p = A.price(_oqo(q))
    assert p["credits"] == credits
    assert p["usd"] == pytest.approx(credits * 0.0001)
    assert sum(s["credits"] for s in p["steps"]) == credits


def test_cursor_round_trip_and_garbage():
    c = A._encode_cursor("https://openalex.org/A5000004691")
    assert A._decode_cursor(c) == "https://openalex.org/A5000004691"
    with pytest.raises(A.AnalyticsError):
        A._decode_cursor("abc")


def test_measure_keys():
    assert Measure("mean", "fwci").key == "mean_fwci"
    assert Measure("percent", "open_access.is_oa").key == "percent_open_access_is_oa"
    assert Measure("percent_of_those").key == "percent_of_those"


def test_a_negated_list_of_groups_is_an_exclude_set():
    # `that institution is not in (A, B)` parses to a negated OR; in negation normal
    # form it's an AND of negated leaves, which the key-set rules read (one request)
    oqo = A._nnf_group_filters(_oqo(
        "get works where topic is (T10878); then group those works by institution where "
        "that institution is not in (I63966007, I97018004)"))
    m, k = A._split_where(oqo.group_by[0].where)
    assert m == [] and len(k) == 2 and all(p.is_negated for p in k)


def test_condition_labels_read_by_name():
    assert A._ANNOTATED_VALUE.sub(lambda m: m.group(2),
                                  "institution is (I99464096 [KU Leuven])") == (
        "institution is (KU Leuven)")


@pytest.mark.parametrize("s,said", [
    (1, "1 second"), (14.4, "14 seconds"), (200, "about 3 minutes"),
    (1089880, "about 13 days")])
def test_say_seconds(s, said):
    assert A.say_seconds(s) == said


@pytest.mark.parametrize("q,reranked,credits", [
    ("works where year is 2020", False, 1),
    ("works where title-abstract has (kelp)", False, 10),
    ("works where title-abstract has (kelp) group by year", False, 10),  # costs the search
    ("works where year is 2020 group by type", False, 1),
    ("works where title-abstract has (kelp)", True, 20),
    ("works where year is 2020", True, 11),
])
def test_a_plain_query_costs_what_its_url_costs(q, reranked, credits):
    assert A.plain_price(_oqo(q), reranked=reranked)["credits"] == credits


def test_a_grandfathered_key_pays_1_for_a_search_as_on_the_url():
    kelp = _oqo("works where title-abstract has (kelp)")
    assert A.plain_price(kelp, grandfathered=True)["credits"] == 1
    assert A.plain_price(kelp, reranked=True, grandfathered=True)["credits"] == 11


def test_the_websites_facets_stay_at_1():
    facet = _oqo("works where title-abstract has (kelp) group by year")
    assert A.plain_price(facet, website=True)["credits"] == 1
    assert A.plain_price(facet)["credits"] == 10
    # the website's results call is a search like any other
    assert A.plain_price(_oqo("works where title-abstract has (kelp)"),
                         website=True)["credits"] == 10


def test_count_floor_only():
    def where(q):
        return A._nnf_group_filters(_oqo(q)).group_by[0].where
    base = "get works where year > (2020); then group those works by author where "
    assert A._count_floor_only(where(base + "count of those works > (5)"))
    assert not A._count_floor_only(where(base + "count of those works < (5)"))
    assert not A._count_floor_only(where(base + "mean FWCI of those works > (1)"))
    assert not A._count_floor_only(where(base + "count of those works > (5) and h-index > (20)"))


def test_groups_count_after_a_key_set():
    lv = A.Level(0, None, "terms")
    assert A._groups_count(lv, {"n_groups": {"value": 100}}) == 100
    lv.exclude = {"a", "b", "c"}
    assert A._keyset_count_agg(lv, "f")["terms"]["include"] == ["a", "b", "c"]
    # two of the three left-out keys are in the set
    assert A._groups_count(lv, {"n_groups": {"value": 100},
                                "n_keyset": {"buckets": [{}, {}]}}) == 98
    lv.include, lv.exclude = {"a", "b"}, None
    assert A._groups_count(lv, {"n_keyset": {"buckets": [{}]}}) == 1


def test_a_filtered_split_says_when_it_left_groups_unchecked():
    lv = A.Level(0, None, "terms")
    lv.size = A.FILTERED_CANDIDATES
    full = {"buckets": [{}] * A.FILTERED_CANDIDATES}
    assert A._filter_truncated(lv, {"s0": full})              # a count floor filled the split
    assert not A._filter_truncated(lv, {"s0": {"buckets": [{}]}})
    more = {"buckets": [{}] * (A.FILTERED_CANDIDATES + 1)}
    assert A._filter_truncated(lv, {"s0": {"buckets": []}, "n_candidates": more})
