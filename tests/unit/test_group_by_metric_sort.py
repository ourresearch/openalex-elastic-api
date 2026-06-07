"""Unit tests for sort-by-aggregate group_by — oxjob #389.

Ranking group_by buckets by a metric sub-aggregation (mean/sum/min/max of a
numeric field), e.g. `group_by=funders.id&sort=cited_by_count.mean:desc`. ES
computes a metric sub-agg per bucket and orders the terms agg by its path
natively (no mapping change).

ES-free: the bucket builder is checked via `.to_dict()`, the result transformer
against AttrDict mocks shaped like real ES bucket responses, and the schema dump
directly. The OQO/URL plumbing (SortBy.aggregate, parse/render, validator) is
checked with the pure helpers. Plain count/key group sort is untouched and
covered elsewhere (`test_queries.py`).
"""
import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.utils import AttrDict

from core.exceptions import APIQueryParamsError
from core.group_by.buckets import (
    GROUP_BY_METRICS,
    GROUP_BY_METRIC_AGG_NAME,
    create_sorted_group_by_buckets,
    parse_metric_sort_key,
    resolve_metric_es_field,
)
from core.group_by.results import get_metric_result_key, get_result
from core.schemas import GroupBySchema
from core.sort import get_sort_fields
from query_translation.oqo import SortBy
from query_translation.url_parser import parse_sort_string
from query_translation.url_renderer import render_sort
from query_translation.validator import VALID_SORT_AGGREGATES
from works.fields import fields_dict


class TestParseMetricSortKey:
    def test_metric_key(self):
        assert parse_metric_sort_key("cited_by_count.mean") == ("cited_by_count", "mean")

    @pytest.mark.parametrize("metric", ["mean", "sum", "min", "max"])
    def test_all_metrics(self, metric):
        assert parse_metric_sort_key(f"cited_by_count.{metric}") == (
            "cited_by_count",
            metric,
        )

    def test_count_and_key_are_not_metric(self):
        assert parse_metric_sort_key("count") == (None, None)
        assert parse_metric_sort_key("key") == (None, None)

    def test_plain_column_is_not_metric(self):
        assert parse_metric_sort_key("cited_by_count") == (None, None)

    def test_dotted_nonmetric_column_preserved(self):
        # `primary_topic.id` last segment `id` is not a metric -> not a metric key.
        assert parse_metric_sort_key("primary_topic.id") == (None, None)

    def test_nested_field_only_last_segment_is_metric(self):
        assert parse_metric_sort_key("apc_paid.value_usd.sum") == (
            "apc_paid.value_usd",
            "sum",
        )

    def test_unknown_metric_name_rejected(self):
        assert parse_metric_sort_key("cited_by_count.median") == (None, None)

    def test_non_string(self):
        assert parse_metric_sort_key(None) == (None, None)


class TestResolveMetricEsField:
    def test_numeric_field_resolves(self):
        assert resolve_metric_es_field(fields_dict, "cited_by_count") == "cited_by_count"

    def test_non_numeric_field_rejected(self):
        # `type` is a TermField, not numeric.
        with pytest.raises(APIQueryParamsError):
            resolve_metric_es_field(fields_dict, "type")

    def test_unknown_field_rejected(self):
        with pytest.raises(APIQueryParamsError):
            resolve_metric_es_field(fields_dict, "not_a_field")


class TestSortedBucketBuilder:
    def _build(self, sort_params, group_by_field="funders.id"):
        s = Search(index="works")
        create_sorted_group_by_buckets(
            bucket_keys={"default": "groupby_funders_id"},
            group_by_field=group_by_field,
            include_unknown=False,
            missing="unknown",
            per_page=200,
            s=s,
            shard_size=3000,
            sort_params=sort_params,
            fields_dict=fields_dict,
        )
        return s.to_dict()["aggs"]

    def test_metric_sub_agg_attached_and_ordered(self):
        aggs = self._build({"cited_by_count.mean": "desc"})
        terms = aggs["groupby_funders_id"]
        assert terms["terms"]["field"] == "funders.id"
        # ordered by the metric sub-agg path, desc
        assert terms["terms"]["order"] == {GROUP_BY_METRIC_AGG_NAME: "desc"}
        # the sub-agg is an `avg` over cited_by_count (mean -> ES avg)
        sub = terms["aggs"][GROUP_BY_METRIC_AGG_NAME]
        assert sub == {"avg": {"field": "cited_by_count"}}

    @pytest.mark.parametrize(
        "metric,es_type",
        [("mean", "avg"), ("sum", "sum"), ("min", "min"), ("max", "max")],
    )
    def test_metric_name_maps_to_es_agg(self, metric, es_type):
        aggs = self._build({f"cited_by_count.{metric}": "asc"})
        sub = aggs["groupby_funders_id"]["aggs"][GROUP_BY_METRIC_AGG_NAME]
        assert es_type in sub
        assert sub[es_type]["field"] == "cited_by_count"
        assert aggs["groupby_funders_id"]["terms"]["order"] == {
            GROUP_BY_METRIC_AGG_NAME: "asc"
        }

    def test_count_sort_unchanged_no_metric_sub_agg(self):
        # Regression: plain count sort builds no metric sub-agg.
        aggs = self._build({"count": "desc"})
        terms = aggs["groupby_funders_id"]
        assert terms["terms"]["order"] == {"_count": "desc"}
        assert "aggs" not in terms

    def test_key_sort_unchanged(self):
        aggs = self._build({"key": "asc"})
        assert aggs["groupby_funders_id"]["terms"]["order"] == {"_key": "asc"}

    def test_non_numeric_metric_field_rejected(self):
        with pytest.raises(APIQueryParamsError):
            self._build({"type.mean": "desc"})


class TestGetSortFieldsGroupBy:
    def test_metric_sort_accepted_with_group_by(self):
        # Returns [] (ordering applied on the agg, not on rows) — like count/key.
        assert (
            get_sort_fields(fields_dict, "funders.id", {"cited_by_count.mean": "desc"})
            == []
        )

    def test_count_still_accepted(self):
        assert get_sort_fields(fields_dict, "funders.id", {"count": "desc"}) == []

    def test_invalid_group_by_sort_still_rejected(self):
        with pytest.raises(APIQueryParamsError):
            get_sort_fields(fields_dict, "funders.id", {"display_name": "asc"})


class TestMetricResultKey:
    def test_metric_key_derivation(self):
        assert (
            get_metric_result_key({"sort": {"cited_by_count.mean": "desc"}})
            == "mean_cited_by_count"
        )

    def test_nested_field_dots_become_underscores(self):
        assert (
            get_metric_result_key({"sort": {"apc_paid.value_usd.sum": "desc"}})
            == "sum_apc_paid_value_usd"
        )

    def test_count_sort_has_no_metric_key(self):
        assert get_metric_result_key({"sort": {"count": "desc"}}) is None

    def test_no_sort(self):
        assert get_metric_result_key({}) is None


class TestGetResultSurfacesMetric:
    def test_metric_value_surfaced(self):
        b = AttrDict(
            {
                "key": "https://openalex.org/F1",
                "doc_count": 100,
                GROUP_BY_METRIC_AGG_NAME: {"value": 42.3},
            }
        )
        r = get_result(b, {}, "funders.id", "works", metric_key="mean_cited_by_count")
        assert r["mean_cited_by_count"] == 42.3
        assert r["doc_count"] == 100

    def test_no_metric_key_no_extra_field(self):
        b = AttrDict({"key": "https://openalex.org/F1", "doc_count": 100})
        r = get_result(b, {}, "funders.id", "works")
        assert "mean_cited_by_count" not in r
        assert set(r.keys()) == {"key", "key_display_name", "doc_count"}

    def test_empty_bucket_metric_none_passthrough(self):
        b = AttrDict(
            {
                "key": "https://openalex.org/F1",
                "doc_count": 0,
                GROUP_BY_METRIC_AGG_NAME: {"value": None},
            }
        )
        r = get_result(b, {}, "funders.id", "works", metric_key="mean_cited_by_count")
        assert r["mean_cited_by_count"] is None


class TestGroupBySchemaDump:
    def test_metric_key_survives_dump(self):
        out = GroupBySchema().dump(
            {
                "key": "https://openalex.org/F1",
                "key_display_name": "NIH",
                "doc_count": 100,
                "mean_cited_by_count": 42.3,
            }
        )
        assert out["mean_cited_by_count"] == 42.3
        assert out["count"] == 100

    @pytest.mark.parametrize(
        "k", ["mean_cited_by_count", "sum_cited_by_count", "min_fwci", "max_fwci"]
    )
    def test_all_metric_prefixes_survive(self, k):
        out = GroupBySchema().dump({"key": "x", "doc_count": 1, k: 9})
        assert out[k] == 9

    def test_no_metric_key_byte_compatible(self):
        # Single-dim no-metric result stays {key, key_display_name, count}.
        out = GroupBySchema().dump(
            {"key": "x", "key_display_name": "X", "doc_count": 5}
        )
        assert set(out.keys()) == {"key", "key_display_name", "count"}

    def test_nested_groups_still_serialized(self):
        # #387 regression: nested groups must still round-trip.
        out = GroupBySchema().dump(
            {
                "key": "x",
                "key_display_name": "X",
                "doc_count": 5,
                "groups": [{"key": "y", "key_display_name": "Y", "doc_count": 2}],
            }
        )
        assert out["groups"][0]["count"] == 2


class TestOQOSortByAggregate:
    def test_to_dict_includes_aggregate(self):
        d = SortBy(column_id="cited_by_count", aggregate="mean", direction="desc").to_dict()
        assert d == {
            "column_id": "cited_by_count",
            "direction": "desc",
            "aggregate": "mean",
        }

    def test_to_dict_omits_aggregate_when_none(self):
        d = SortBy(column_id="cited_by_count", direction="asc").to_dict()
        assert "aggregate" not in d

    def test_from_dict_roundtrip(self):
        d = {"column_id": "fwci", "aggregate": "sum", "direction": "asc"}
        assert SortBy.from_dict(d).to_dict() == d

    def test_from_dict_back_compat_no_aggregate(self):
        sb = SortBy.from_dict({"column_id": "fwci", "direction": "desc"})
        assert sb.aggregate is None


class TestUrlParseRenderRoundTrip:
    def test_parse_metric_sort(self):
        [sb] = parse_sort_string("cited_by_count.mean:desc")
        assert sb.column_id == "cited_by_count"
        assert sb.aggregate == "mean"
        assert sb.direction == "desc"

    def test_render_metric_sort(self):
        sb = [SortBy(column_id="cited_by_count", aggregate="mean", direction="desc")]
        assert render_sort(sb) == "cited_by_count.mean:desc"

    def test_roundtrip_metric(self):
        assert (
            render_sort(parse_sort_string("cited_by_count.mean:desc"))
            == "cited_by_count.mean:desc"
        )

    def test_dotted_nonmetric_column_not_split(self):
        [sb] = parse_sort_string("primary_topic.id:asc")
        assert sb.column_id == "primary_topic.id"
        assert sb.aggregate is None
        assert render_sort([sb]) == "primary_topic.id:asc"

    def test_plain_multi_column_unchanged(self):
        sb = parse_sort_string("publication_year:desc,cited_by_count:desc")
        assert [s.aggregate for s in sb] == [None, None]
        assert (
            render_sort(sb) == "publication_year:desc,cited_by_count:desc"
        )


class TestConstantsAligned:
    def test_metric_names_match_validator(self):
        assert set(GROUP_BY_METRICS) == VALID_SORT_AGGREGATES
