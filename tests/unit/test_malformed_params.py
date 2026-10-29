"""Malformed parameters answer 200 or a JSON 400, never an HTTP 500 (oxjob #1913).

Live before (29 Oct 2026): 23 of 34 probes answered HTML 500.
- select= with nothing in it reached marshmallow as only="" (Sentry OPENALEX-SEARCH-API-4, ~19 a day).
- publication_year:!null reached float("null") (OPENALEX-SEARCH-API-H).
- publication_year:2016_2019 passed float() (Python reads it as 20162019) and Elasticsearch
  rejected it (OPENALEX-SEARCH-API-X); nan and inf did the same.
"""
import pytest
from elasticsearch_dsl import Search
from werkzeug.datastructures import MultiDict

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.utils import process_only_fields, select_fields
from core.validate import validate_select_param
from ids.utils import process_id_only_fields
from works.fields import fields_dict as works_fields
from works.schemas import WorksSchema


class _Request:
    def __init__(self, **args):
        self.args = MultiDict(args)


def _filter(param, value):
    return filter_records(works_fields, [{param: value}], Search()).to_dict()["query"]


# --- empty select ---

@pytest.mark.parametrize("select", ["", " ", ",", " , ", ",,"])
def test_an_empty_select_means_every_field(select):
    request = _Request(select=select)
    assert select_fields(request) is None
    assert process_only_fields(request, WorksSchema) is None
    assert process_id_only_fields(request, WorksSchema) is None


def test_a_stray_comma_in_select_is_ignored():
    request = _Request(select="id, doi,")
    assert process_only_fields(request, WorksSchema) == ["meta", "results.id", "results.doi", "group_by"]
    assert process_id_only_fields(request, WorksSchema) == ["id", "doi"]


def test_no_select_is_unchanged():
    assert process_only_fields(_Request(), WorksSchema) is None
    assert process_id_only_fields(_Request(), WorksSchema) is None


def test_an_unknown_select_field_still_answers_a_400():
    with pytest.raises(APIQueryParamsError, match="nope is not a valid select field"):
        process_only_fields(_Request(select="id,nope"), WorksSchema)
    with pytest.raises(APIQueryParamsError, match="nope is not a valid select field"):
        process_id_only_fields(_Request(select="nope"), WorksSchema)


def test_an_empty_select_works_with_group_by():
    validate_select_param(_Request(group_by="type", select=""))
    with pytest.raises(APIQueryParamsError, match="select does not work with group_by"):
        validate_select_param(_Request(group_by="type", select="id"))


# --- numbers ---

@pytest.mark.parametrize("param", ["publication_year", "cited_by_count", "fwci"])
def test_not_null_on_a_number_means_has_a_value(param):
    assert _filter(param, "!null") == {"bool": {"filter": [{"exists": {"field": param}}]}}
    assert _filter(param, "null") == {"bool": {"filter": [{"bool": {"must_not": [{"exists": {"field": param}}]}}]}}


@pytest.mark.parametrize("value", [
    "2016_2019", "!2016_2019", "1_000", ">1_000", "<1_000", "1_000-", "2016_2019|2020",
    "nan", "inf", "-inf", "infinity", "!nan", ">nan", "<inf", "nan-2020", "2016-inf",
    "!abc", "abc", "2016-2019-2020", "!2016-2019-2020", "2019|", ">", "!",
])
def test_a_value_that_is_not_a_number_answers_a_400(value):
    with pytest.raises(APIQueryParamsError, match="publication_year must be a number"):
        _filter("publication_year", value)


@pytest.mark.parametrize("param,value,hint", [
    ("publication_year", "2016_2019", "For a range, use a hyphen: publication_year:2016-2019."),
    ("publication_year", "!2016_2019", "For a range, use a hyphen: publication_year:2016-2019."),
    ("cited_by_count", "1_000", "Write it without underscores: 1000."),
    ("cited_by_count", ">1_000_000", "Write it without underscores: 1000000."),
])
def test_an_underscore_names_the_fix(param, value, hint):
    with pytest.raises(APIQueryParamsError) as err:
        _filter(param, value)
    assert hint in str(err.value)


@pytest.mark.parametrize("value,query", [
    ("2020", {"term": {"publication_year": "2020"}}),
    ("2016-2019", {"range": {"publication_year": {"gte": 2016.0, "lte": 2019.0}}}),
    ("!2020", {"bool": {"must_not": [{"term": {"publication_year": 2020.0}}]}}),
    ("!2016-2019", {"bool": {"must_not": [{"range": {"publication_year": {"gte": 2016.0, "lte": 2019.0}}}]}}),
    (">2020", {"range": {"publication_year": {"gt": 2020.0}}}),
    ("<1900", {"range": {"publication_year": {"lt": 1900.0}}}),
    ("2020-", {"range": {"publication_year": {"gte": 2020.0}}}),
    ("-2020", {"range": {"publication_year": {"lte": 2020.0}}}),
    ("1e3", {"term": {"publication_year": "1e3"}}),
    ("2020.5", {"term": {"publication_year": "2020.5"}}),
])
def test_documented_number_values_build_the_same_query(value, query):
    assert _filter("publication_year", value) == {"bool": {"filter": [query]}}


def test_an_or_list_of_years_still_works():
    q = _filter("publication_year", "2019|2020")
    assert q["bool"]["filter"][0]["bool"]["should"] == [
        {"term": {"publication_year": "2019"}}, {"term": {"publication_year": "2020"}},
    ]
