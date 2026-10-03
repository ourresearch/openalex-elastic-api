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
