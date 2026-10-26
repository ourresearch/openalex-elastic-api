"""Every yes/no group_by counts what its own filter matches (oxjob #1859).

For a boolean column F, `group_by=F` must return the counts of `filter=F:true` and
`filter=F:false`, keyed "true" and "false" (the values the filter takes). Before
#1859, group_by ran a terms agg or an `exists` on the raw field: `has_abstract` put
all 328M works under true (the filter found 148.7M without an abstract), the two
OA-version columns came back empty, and most columns keyed "1"/"0", which the filter
refuses. No ES needed: these compare the queries the code builds, column by column,
on every entity.
"""
import glob
import importlib
import os

import pytest
from elasticsearch_dsl import AttrDict, Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.group_by.buckets import GROUP_BY_METRIC_AGG_NAME, create_group_by_buckets
from core.group_by.results import calculate_group_by_count, get_boolean_group_by_results

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARAMS = {"per_page": 200, "cursor": None, "q": None, "sort": None}


def _entity_fields():
    out = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "*", "fields.py"))):
        module = os.path.basename(os.path.dirname(path))
        try:
            fields_dict = importlib.import_module(f"{module}.fields").fields_dict
        except (ImportError, AttributeError):
            continue
        out[module] = fields_dict
    return out


ENTITY_FIELDS = _entity_fields()
BOOLEAN_COLUMNS = [
    (module, param)
    for module, fields_dict in ENTITY_FIELDS.items()
    for param, field in fields_dict.items()
    if type(field).__name__ == "BooleanField"
]


def _filter_query(fields_dict, param, value):
    q = filter_records(fields_dict, [{param: value}], Search()).to_dict()["query"]
    # most entities wrap one filter as bool.filter[0]; awards renders the bare query
    if list(q) == ["bool"] and list(q["bool"]) == ["filter"] and len(q["bool"]["filter"]) == 1:
        return q["bool"]["filter"][0]
    return q


def _group_by_agg(fields_dict, param, include_unknown, sort=None):
    params = dict(PARAMS, sort=sort)
    s = create_group_by_buckets(fields_dict, param, include_unknown, Search(), params)
    return s.to_dict()["aggs"][f"groupby_{param.replace('.', '_')}"]


def test_the_registry_has_boolean_columns():
    # guards the parametrized tests below against silently running on nothing
    assert len(BOOLEAN_COLUMNS) > 50
    assert ("works", "has_abstract") in BOOLEAN_COLUMNS
    assert ("sources", "is_oa") in BOOLEAN_COLUMNS


@pytest.mark.parametrize("module,param", BOOLEAN_COLUMNS)
def test_boolean_group_by_counts_what_its_filter_matches(module, param):
    fields_dict = ENTITY_FIELDS[module]
    try:
        agg = _group_by_agg(fields_dict, param, include_unknown=True)
    except APIQueryParamsError:
        pytest.skip(f"{module}.{param} can't be grouped")
    q_true = _filter_query(fields_dict, param, "true")
    q_false = _filter_query(fields_dict, param, "false")

    assert agg == {"filters": {"filters": {"true": q_true, "false": q_false},
                               "other_bucket_key": "unknown"}}
    assert q_true != q_false, "the filter's true and false run the same query"
    assert "other_bucket_key" not in _group_by_agg(fields_dict, param, include_unknown=False)["filters"]


@pytest.mark.parametrize("module,param", BOOLEAN_COLUMNS)
def test_a_term_on_true_reads_a_column_of_that_name(module, param):
    """`filter=F:true` as a term on "true" only works against a stored true/false
    column. locations.source.has_issn ran one against the ISSN keyword and matched
    no work (oxjob #1859), as has_recipient_country had (2026-10-15). A column that
    means "has a value" needs an exists test (settings.EXTERNAL_ID_FIELDS or the
    exists branch in BooleanField.build_query)."""
    q = _filter_query(ENTITY_FIELDS[module], param, "true")
    if list(q) != ["term"]:
        return
    ((es_field, value),) = q["term"].items()
    assert value == "true"
    assert es_field.split(".")[-1] == param.split(".")[-1], (param, es_field)


def test_has_abstract_reads_the_stored_flag():
    # every work carries has_abstract (true or false), so an exists test counted them all
    agg = _group_by_agg(ENTITY_FIELDS["works"], "has_abstract", include_unknown=False)
    assert agg == {"filters": {"filters": {"true": {"term": {"has_abstract": "true"}},
                                           "false": {"term": {"has_abstract": "false"}}}}}


def test_metric_sort_rides_on_each_group():
    agg = _group_by_agg(ENTITY_FIELDS["works"], "is_oa", False, sort={"cited_by_count.mean": "desc"})
    assert agg["aggs"] == {GROUP_BY_METRIC_AGG_NAME: {"avg": {"field": "cited_by_count"}}}


def _response(group_by, true, false, unknown=None, metric=None):
    counts = {"true": true, "false": false}
    if unknown is not None:
        counts["unknown"] = unknown
    buckets = {}
    for key, count in counts.items():
        buckets[key] = {"doc_count": count}
        if metric:
            buckets[key][GROUP_BY_METRIC_AGG_NAME] = {"value": metric.get(key)}
    return AttrDict({"aggregations": {f"groupby_{group_by}": {"buckets": buckets}}})


def _keys(results):
    return [(r["key"], r["doc_count"]) for r in results]


def test_keys_are_the_filter_values_most_works_first():
    results = get_boolean_group_by_results(_response("is_oa", 3, 5), "is_oa")
    assert _keys(results) == [("false", 5), ("true", 3)]
    assert [r["key_display_name"] for r in results] == ["false", "true"]


def test_unknown_only_when_it_has_works():
    assert _keys(get_boolean_group_by_results(_response("x", 3, 5, 0), "x")) == [("false", 5), ("true", 3)]
    assert _keys(get_boolean_group_by_results(_response("x", 3, 5, 7), "x")) == [
        ("unknown", 7), ("false", 5), ("true", 3)]


def test_sort_orders_boolean_groups():
    r = _response("x", 3, 5, 7)

    def order(sort):
        return [k for k, _ in _keys(get_boolean_group_by_results(r, "x", {"sort": sort}))]

    assert order({"count": "asc"}) == ["true", "false", "unknown"]
    assert order({"key": "asc"}) == ["false", "true", "unknown"]
    assert order({"key": "desc"}) == ["unknown", "true", "false"]


def test_metric_sort_returns_the_value_and_puts_empty_groups_last():
    r = _response("x", 3, 5, 7, metric={"true": 10.5, "false": 6.0, "unknown": None})
    results = get_boolean_group_by_results(r, "x", {"sort": {"cited_by_count.mean": "desc"}})
    assert [(x["key"], x["mean_cited_by_count"]) for x in results] == [
        ("true", 10.5), ("false", 6.0), ("unknown", None)]


def test_groups_count():
    assert calculate_group_by_count({"group_by": "x"}, _response("x", 3, 5)) == 2
    assert calculate_group_by_count({"group_by": "x:include_unknown"}, _response("x", 3, 5, 0)) == 2
    assert calculate_group_by_count({"group_by": "x:include_unknown"}, _response("x", 3, 5, 7)) == 3
    # a yes/no column whose name says "version" is still two or three groups
    v = "has_oa_submitted_version"
    assert calculate_group_by_count({"group_by": v}, _response(v, 3, 5)) == 2
