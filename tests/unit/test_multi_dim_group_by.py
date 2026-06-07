"""Unit tests for multi-dimensional (nested) group_by — oxjob #387.

ES-free: the bucket builder is checked via `.to_dict()` and the result
transformer against AttrDict mocks shaped like real ES bucket responses. These
exercise the *nested* path (the singular `group_by=a,b` form); single-dim and the
plural `group_bys` facet path are untouched and covered elsewhere.
"""
import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.utils import AttrDict

from core.exceptions import APIQueryParamsError
from core.group_by.buckets import (
    MAX_GROUP_BY_DIMENSIONS,
    create_nested_group_by_buckets,
)
from core.group_by.results import (
    get_nested_group_by_results,
    calculate_nested_group_by_count,
)
from core.group_by.utils import (
    is_multi_dim_group_by,
    parse_group_by_dimensions,
)
from works.fields import fields_dict


def _bucket(key, doc_count, child_key=None, children=None):
    d = {"key": key, "doc_count": doc_count}
    if child_key is not None:
        d[child_key] = {"buckets": children or []}
    return AttrDict(d)


class TestDimensionParsing:
    def test_is_multi_dim(self):
        assert is_multi_dim_group_by("a,b") is True
        assert is_multi_dim_group_by("a") is False
        assert is_multi_dim_group_by(None) is False
        assert is_multi_dim_group_by("") is False

    def test_parse_dimensions(self):
        assert parse_group_by_dimensions("primary_topic.id,publication_year") == [
            ("primary_topic.id", False),
            ("publication_year", False),
        ]

    def test_parse_dimensions_include_unknown_per_level(self):
        assert parse_group_by_dimensions(
            "primary_topic.id,publication_year:include_unknown"
        ) == [("primary_topic.id", False), ("publication_year", True)]

    def test_parse_single_dim_one_element(self):
        assert parse_group_by_dimensions("type") == [("type", False)]


class TestNestedBucketBuilder:
    def _build(self, group_by_string, params=None):
        params = params or {"per_page": 200, "cursor": None, "q": None}
        dims = parse_group_by_dimensions(group_by_string)
        s = Search(index="works")
        s = create_nested_group_by_buckets(fields_dict, dims, s, params)
        return s.to_dict()["aggs"]

    def test_case_48_nested_structure(self):
        aggs = self._build("primary_topic.id,publication_year")
        outer = aggs["groupby_primary_topic_id"]
        assert outer["terms"]["field"] == "primary_topic.id"
        inner = outer["aggs"]["groupby_publication_year"]
        assert inner["terms"]["field"] == "publication_year"

    def test_three_dimensions_nest(self):
        aggs = self._build("type,primary_topic.id,publication_year")
        lvl1 = aggs["groupby_type"]
        lvl2 = lvl1["aggs"]["groupby_primary_topic_id"]
        lvl3 = lvl2["aggs"]["groupby_publication_year"]
        assert lvl3["terms"]["field"] == "publication_year"

    def test_too_many_dimensions_rejected(self):
        too_many = ",".join(["publication_year"] * (MAX_GROUP_BY_DIMENSIONS + 1))
        with pytest.raises(APIQueryParamsError):
            self._build(too_many)

    def test_cursor_rejected(self):
        with pytest.raises(APIQueryParamsError):
            self._build(
                "type,publication_year",
                {"per_page": 200, "cursor": "abc", "q": None},
            )

    def test_unsupported_boolean_field_rejected(self):
        # is_oa is a boolean exists/not-exists field — no nesting support.
        with pytest.raises(APIQueryParamsError):
            self._build("open_access.is_oa,publication_year")

    def test_include_unknown_sets_missing(self):
        aggs = self._build("type,publication_year:include_unknown")
        inner = aggs["groupby_type"]["aggs"]["groupby_publication_year"]
        assert "missing" in inner["terms"]


class TestNestedResults:
    def _resp(self):
        return AttrDict(
            {
                "aggregations": {
                    "groupby_type": {
                        "buckets": [
                            _bucket(
                                "article",
                                5000,
                                "groupby_publication_year",
                                [
                                    _bucket("2020", 1200),
                                    _bucket("2021", 1500),
                                ],
                            ),
                            _bucket(
                                "book",
                                300,
                                "groupby_publication_year",
                                [_bucket("2020", 100)],
                            ),
                        ]
                    }
                }
            }
        )

    def test_nested_shape(self):
        dims = parse_group_by_dimensions("type,publication_year")
        params = {"group_by": "type,publication_year", "per_page": 200}
        out = get_nested_group_by_results(
            dims, params, "works-v1", fields_dict, self._resp()
        )
        assert len(out) == 2
        first = out[0]
        assert first["key"] == "https://openalex.org/types/article"
        assert first["doc_count"] == 5000
        assert "groups" in first
        assert first["groups"] == [
            {"key": "2020", "key_display_name": "2020", "doc_count": 1200},
            {"key": "2021", "key_display_name": "2021", "doc_count": 1500},
        ]

    def test_groups_count_is_outer_bucket_count(self):
        params = {"group_by": "type,publication_year"}
        assert calculate_nested_group_by_count(params, self._resp()) == 2


class TestGroupBySchemaSerialization:
    """marshmallow drops undeclared keys on dump — the nested `groups` list must
    be a declared self-referential field, or it's silently stripped (oxjob #387;
    same footgun class as the meta.x_query pass-through)."""

    def test_nested_groups_survive_dump_with_count_rename(self):
        from core.schemas import GroupBySchema

        nested = [
            {
                "key": "T1",
                "key_display_name": "Topic 1",
                "doc_count": 500,
                "groups": [
                    {"key": "2020", "key_display_name": "2020", "doc_count": 120},
                ],
            }
        ]
        out = GroupBySchema(many=True).dump(nested)
        assert out[0]["count"] == 500
        assert out[0]["groups"][0]["key"] == "2020"
        assert out[0]["groups"][0]["count"] == 120  # doc_count renamed at each level

    def test_single_dim_dump_has_no_groups_key(self):
        from core.schemas import GroupBySchema

        out = GroupBySchema(many=True).dump(
            [{"key": "2020", "key_display_name": "2020", "doc_count": 120}]
        )
        assert "groups" not in out[0]  # byte-compatible with pre-#387


class TestOqoExecutionPath:
    """The OQO/OQL execution path (corpus case 48) must no longer 400 on
    multi-dim group_by; it flows the dimension list through as the comma string."""

    def _params(self, oqo_dict):
        from flask import Flask, request
        from query_translation.oqo import OQO
        from query_translation.execution import _build_params_from_oqo

        oqo = OQO.from_dict(oqo_dict)
        app = Flask(__name__)
        with app.test_request_context("/?oqo=x"):
            return _build_params_from_oqo(oqo, request)

    def test_case_48_validates(self):
        from query_translation.oqo import OQO
        from query_translation.validator import validate_oqo

        oqo = OQO.from_dict(
            {
                "get_rows": "works",
                "filter_rows": [
                    {"column_id": "publication_year", "value": 1976, "operator": ">="}
                ],
                "group_by": [
                    {"column_id": "primary_topic.id"},
                    {"column_id": "publication_year"},
                ],
            }
        )
        assert validate_oqo(oqo).valid is True

    def test_case_48_builds_comma_joined_group_by(self):
        params = self._params(
            {
                "get_rows": "works",
                "filter_rows": [],
                "group_by": [
                    {"column_id": "primary_topic.id"},
                    {"column_id": "publication_year"},
                ],
            }
        )
        assert params["group_by"] == "primary_topic.id,publication_year"
        assert params["group_bys"] is None

    def test_single_dim_oqo_unchanged(self):
        params = self._params(
            {
                "get_rows": "works",
                "filter_rows": [],
                "group_by": [{"column_id": "publication_year"}],
            }
        )
        assert params["group_by"] == "publication_year"
