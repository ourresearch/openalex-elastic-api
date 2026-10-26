"""Grouping and metric bugs found by #1512 and fixed in oxjob #1513 (2026-10-26).

Each test names the bug number from the job's README table. None of them touch
Elasticsearch: they check the query objects, the echo, and the ES request bodies.
"""
import pytest
from flask import Flask

from core.exceptions import APIQueryParamsError
from works.fields import fields_dict


# --- bug 4: the canonical form keeps a group's metric sort ---------------------

def test_canonical_form_keeps_the_metric_sort_aggregate():
    from query_translation.oqo import OQO, GroupBy, SortBy
    from query_translation.oqo_canonicalizer import canonicalize_oqo
    oqo = OQO(get_rows="works", group_by=[GroupBy("primary_topic.subfield.id")],
              sort_by=[SortBy("cited_by_count", "desc", "mean")])
    assert canonicalize_oqo(oqo).sort_by == [SortBy("cited_by_count", "desc", "mean")]


def test_a_metric_sorted_group_is_said_as_the_table_that_returns_the_same_rows():
    from query_translation.oqo import OQO, GroupBy, Measure, SortBy, metric_sort_as_table
    oqo = OQO(get_rows="works", group_by=[GroupBy("primary_topic.subfield.id")],
              sort_by=[SortBy("cited_by_count", "desc", "mean")])
    table = metric_sort_as_table(oqo)
    assert table.calculate == [Measure("count"), Measure("mean", "cited_by_count")]
    # the same key the URL path returns per group (#389)
    assert table.sort_by == [SortBy("mean_cited_by_count", "desc")]
    # nothing else changes
    plain = OQO(get_rows="works", group_by=[GroupBy("type")], sort_by=[SortBy("count", "desc")])
    assert metric_sort_as_table(plain) is plain


def test_the_url_echo_says_the_metric_sort_and_round_trips(monkeypatch):
    from query_translation import oql_lang
    from query_translation.url_parser import parse_url_to_oqo
    from query_translation.x_query import build_x_query
    from query_translation.oql_core import parse_core
    from query_translation.oqo_canonicalizer import canonicalize_oqo
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "core")
    oqo = parse_url_to_oqo("works", filter_string="publication_year:2023",
                           group_by_string="primary_topic.subfield.id",
                           sort_string="cited_by_count.mean:desc")
    with Flask(__name__).test_request_context("/"):
        xq = build_x_query(oqo)
    assert xq["oql"] == "get the count and mean citations of works from 2023 by subfield, highest mean citations first"
    assert "sort=cited_by_count.mean:desc" in xq["url"]          # the URL form keeps its own spelling
    assert xq["order"] == "highest mean citations first"
    back = canonicalize_oqo(parse_core(xq["oql"]))
    assert back.to_dict() == xq["oqo"]


def test_a_table_oqo_with_a_metric_sort_sorts_by_its_measure():
    # however the sort arrives (an OQO from the website, say), a table sorts by a measure
    from query_translation.oqo import OQO, Measure, SortBy
    oqo = OQO.from_dict({"get_rows": "works", "group_by": [{"column_id": "type"}],
                         "calculate": [{"measure": "count"}],
                         "sort_by": [{"column_id": "fwci", "direction": "desc", "aggregate": "mean"}]})
    assert oqo.calculate == [Measure("count"), Measure("mean", "fwci")]
    assert oqo.sort_by == [SortBy("mean_fwci", "desc")]


# --- bug 1: OQL plus a sibling metric sort --------------------------------------

def test_a_sibling_metric_sort_on_an_oql_table_sorts_by_that_measure():
    from query_translation.execution import _merge_view_params
    from query_translation.oql_core import parse_core
    from query_translation.oqo import Measure, SortBy
    from query_translation.validator import validate_oqo
    oqo = parse_core("get the count of works from 2023 by subfield")
    with Flask(__name__).test_request_context("/?sort=cited_by_count.mean:desc") as ctx:
        merged = _merge_view_params(oqo, ctx.request)
    assert Measure("mean", "cited_by_count") in merged.calculate
    assert merged.sort_by == [SortBy("mean_cited_by_count", "desc")]
    assert validate_oqo(merged).valid


# --- bugs 2 and 3: the URL path's group metric sort -----------------------------

def _nested_outer_agg(sort):
    """The outer terms agg a year-by-type nested group_by builds for `sort`."""
    from elasticsearch_dsl import Search
    from core.group_by.buckets import create_nested_group_by_buckets
    params = {"sort": sort, "per_page": 5, "q": None, "cursor": None}
    s = create_nested_group_by_buckets(
        fields_dict, [("publication_year", False), ("type", False)], Search(), params)
    (outer,) = s.to_dict()["aggs"].values()
    return outer


def test_a_nested_group_orders_every_level_by_the_metric_and_carries_its_value():
    outer = _nested_outer_agg({"cited_by_count.mean": "desc"})
    (inner,) = [v for k, v in outer["aggs"].items() if k != "group_by_metric"]
    for level in (outer, inner):
        assert level["terms"]["order"] == {"group_by_metric": "desc"}
        assert level["aggs"]["group_by_metric"] == {"avg": {"field": "cited_by_count"}}


@pytest.mark.parametrize("sort,order", [({"key": "asc"}, {"_key": "asc"}),
                                        ({"count": "desc"}, {"_count": "desc"}),
                                        ({}, None)])
def test_a_nested_group_takes_a_count_or_key_order(sort, order):
    assert _nested_outer_agg(sort)["terms"].get("order") == order


def test_field_groups_return_the_metric_value(monkeypatch):
    from elasticsearch_dsl.utils import AttrDict
    from core.group_by import results
    buckets = [AttrDict({"key": "13", "doc_count": 5, "group_by_metric": {"value": 38.3}}),
               AttrDict({"key": "24", "doc_count": 2, "group_by_metric": {"value": 29.3}})]
    monkeypatch.setattr(results, "get_default_buckets", lambda group_by, response: buckets)
    monkeypatch.setattr(results, "requires_display_name_conversion", lambda group_by: False)
    out = results.get_topics_group_by_results(
        "primary_topic.field.id", None, "works-v35", metric_key="mean_cited_by_count")
    assert [r["mean_cited_by_count"] for r in out] == [38.3, 29.3]


# --- bug 8: groups by cited work use map execution ------------------------------

def test_group_by_cites_uses_map_execution():
    from elasticsearch_dsl import Search
    from core.group_by.buckets import create_group_by_buckets
    s = create_group_by_buckets(fields_dict, "cites", False, Search(),
                                {"sort": None, "per_page": 25, "q": None, "cursor": None})
    (agg,) = s.to_dict()["aggs"].values()
    assert agg["terms"]["field"] == "referenced_works"
    assert agg["terms"]["execution_hint"] == "map"


# --- bug 6: /works/stats on a field no work carries -----------------------------

def test_stats_with_no_values_answer_null_percentiles(monkeypatch):
    from core import stats_view

    class _Agg:
        def __init__(self, d):
            self._d = d
            self.value = d.get("value")

        def to_dict(self):
            return self._d

    class _Resp:
        took = 1
        aggregations = {"x_percentiles": _Agg({"values": {"25.0": None, "50.0": None, "75.0": None}}),
                        "x_sum": _Agg({"value": 0})}

    class _Search:
        def __init__(self, *a, **k):
            self.aggs = self

        def extra(self, **k):
            return self

        def count(self):
            return 0

        def bucket(self, *a, **k):
            return self

        def execute(self):
            return _Resp()

    monkeypatch.setattr(stats_view, "Search", _Search)
    with Flask(__name__).test_request_context("/works/stats/") as ctx:
        out = stats_view.shared_stats_view(ctx.request, {}, "works", ["x"], "works")
    assert out["stats"] == [{"key": "x", "percentiles": {25: None, 50: None, 75: None}, "sum": 0}]


# --- bug 10: independent group_bys have no OQL form -----------------------------

def test_independent_group_bys_echo_no_nested_oql():
    from core.shared_view import _independent_groups_echo
    # the caller builds the echo from the query without the split
    xq = {"oql": "get works from 2023", "x_new_oql": "get works from 2023",
          "oqo": {"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2023}]},
          "url": "/works?filter=publication_year:2023&per_page=2",
          "order": "most cited (age-adjusted)", "order_default": True}
    out = _independent_groups_echo(xq, "publication_year,type")
    assert out["oql"] is None and out["x_new_oql"] is None and out["oql_unavailable"]
    assert out["oqo"] == xq["oqo"]
    assert out["url"] == "/works?filter=publication_year:2023&per_page=2&group_bys=publication_year,type"


@pytest.mark.parametrize("args,nested", [("group_bys=publication_year,type", False),
                                         ("group_by=publication_year,type", True),
                                         ("group_bys=type", True)])
def test_the_url_echo_of_group_bys(args, nested):
    from core.shared_view import attach_x_query
    result = {"meta": {}}
    with Flask(__name__).test_request_context(f"/works?filter=publication_year:2023&{args}") as ctx:
        attach_x_query(result, ctx.request, "works-v35")
    xq = result["meta"]["x_query"]          # attach_x_query swallows errors: it must be there
    assert ("group_by" in xq["oqo"]) is nested
    assert (xq["oql"] is not None) is nested


# --- bug 13: wrong-type IDs are errors, not 0 results ---------------------------

@pytest.mark.parametrize("column,value,ok", [
    ("referenced_works", "I27837315", False),                 # `it cites (I...)`
    ("referenced_works", "W2741809807", True),
    ("authorships.author.id", "I27837315", False),
    ("primary_location.source.host_organization_lineage", "I205783295", True),   # Cornell hosts repositories
    ("primary_location.source.host_organization_lineage", "P4310320990", True),
    ("primary_location.source.host_organization_lineage", "S4306400194", False),
])
def test_validator_checks_the_id_type(column, value, ok):
    from query_translation.oqo import OQO, LeafFilter
    from query_translation.validator import validate_oqo
    result = validate_oqo(OQO(get_rows="works", filter_rows=[LeafFilter(column, value)]))
    assert result.valid is ok, result.errors


@pytest.mark.parametrize("param,value,ok", [
    ("authorships.author.id", "I27837315", False),
    ("authorships.author.id", "https://openalex.org/A5023888391", True),
    ("cites", "I27837315", False),
    ("cited_by", "A5023888391", False),
    ("related_to", "W2741809807", True),
    ("authorships.institutions.lineage", "!A5023888391", False),
    ("locations.source.host_organization", "I205783295", True),
    ("ids.openalex", "I27837315", False),    # a works field: works IDs
    ("ids.openalex", "W2741809807", True),
])
def test_url_filters_check_the_id_type(param, value, ok):
    field = fields_dict[param]
    field.value = value
    if ok:
        field.validate(value)
    else:
        with pytest.raises(APIQueryParamsError, match="is an OpenAlex"):
            field.validate(value)


# --- ticket 26042: oxurl numbers are numbers ------------------------------------

def test_url_sample_and_paging_become_integers():
    from query_translation.url_parser import parse_url_to_oqo
    oqo = parse_url_to_oqo("works", sample="100", per_page="5", page="2", seed="3")
    assert (oqo.sample, oqo.per_page, oqo.page, oqo.seed) == (100, 5, 2, "3")
    assert parse_url_to_oqo("works", sample="abc").sample == "abc"     # left for the validator
