"""authorships.countries and authorships.is_corresponding read `authorships_full` (oxjob #1730).

ES caps a work's `authorships` at 100 for list views and keeps every authorship in
`authorships_full`. These two filters read the capped list, so a country or a
corresponding author past position 100 was missed. Filters, group_bys and sorts
must read `authorships_full`. No ES needed: these assert on the queries the code builds.
"""
import json
import re

from elasticsearch_dsl import Search

from core.filter import filter_records
from core.group_by.buckets import create_group_by_buckets
from core.sort import get_sort_fields
from works.fields import fields_dict as works_fields

CAPPED = re.compile(r'"authorships\.(countries|is_corresponding)')

PARAMS = {
    "authorships.countries": ["US", "us", "countries/US", "!US", "US|GB", "!US|GB", "DE|null", "null", "!null"],
    "authorships.is_corresponding": ["true", "false", "TRUE", "null", "!null"],
    "is_corresponding": ["true", "false", "null", "!null"],
}


def filter_body(param, value):
    return json.dumps(filter_records(works_fields, [{param: value}], Search()).to_dict())


def group_by_body(param, include_unknown=False):
    params = {"per_page": 200, "cursor": None, "q": None, "sort": None}
    return json.dumps(create_group_by_buckets(works_fields, param, include_unknown, Search(), params).to_dict())


def test_filters_read_authorships_full():
    for param, values in PARAMS.items():
        for value in values:
            body = filter_body(param, value)
            assert not CAPPED.search(body), (param, value, body)
            assert '"authorships_full.' in body, (param, value, body)


def test_countries_filter_keeps_case_insensitive_subfield():
    assert filter_body("authorships.countries", "us") == json.dumps(
        {"query": {"bool": {"filter": [{"term": {"authorships_full.countries.lower": "us"}}]}}})


def test_countries_null_reads_authorships_full():
    assert filter_body("authorships.countries", "null") == json.dumps(
        {"query": {"bool": {"filter": [{"bool": {"must_not": [{"exists": {"field": "authorships_full.countries.lower"}}]}}]}}})


def test_is_corresponding_true_reads_authorships_full():
    for param in ("authorships.is_corresponding", "is_corresponding"):
        assert filter_body(param, "true") == json.dumps(
            {"query": {"bool": {"filter": [{"term": {"authorships_full.is_corresponding": "true"}}]}}})


def test_group_bys_aggregate_on_authorships_full():
    """countries aggregates on the raw keyword, so bucket keys stay upper-case country codes."""
    for include_unknown in (False, True):
        assert '"field": "authorships_full.countries"' in group_by_body("authorships.countries", include_unknown)
        for param in ("authorships.is_corresponding", "is_corresponding"):
            body = group_by_body(param, include_unknown)
            assert '"field": "authorships_full.is_corresponding"' in body, body
            assert not CAPPED.search(body), body


def test_sorts_read_authorships_full():
    assert get_sort_fields(works_fields, None, {"authorships.countries": "asc"}) == ["authorships_full.countries"]
    assert get_sort_fields(works_fields, None, {"is_corresponding": "desc"}) == ["-authorships_full.is_corresponding"]
