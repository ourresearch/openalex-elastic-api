"""A number range written with spaces around its hyphen is the one range (oxjob #1091).

Since number filters took the `+` AND (oxjob #1032, 16 Nov 2026), `publication_year:2015 - 2025`
split into `2015`, `-` and `2025` and answered 400 "Value for param publication_year must be a
number." It had always run as 2015-2025: 236 saved searches carry such a range, 21 of them with a
daily alert that then failed every day.

No ES, no app:
    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_spaced_range_1091.py --noconftest -q
"""
import pytest
from elasticsearch_dsl import Search

from core.filter import filter_records, join_spaced_range
from query_translation.url_parser import parse_url_to_oqo
from works.fields import fields_dict as works_fields


def _filters(params):
    return filter_records(works_fields, params, Search()).to_dict()["query"]["bool"]["filter"]


@pytest.mark.parametrize("key, spaced, joined", [
    ("publication_year", "2015 - 2025", "2015-2025"),   # the alerts' shape
    ("publication_year", "2015 -2025", "2015-2025"),
    ("publication_year", "2015- 2025", "2015-2025"),
    ("publication_year", "2015 -", "2015-"),             # open-ended, as saved
    ("publication_year", "- 2025", "-2025"),
    ("publication_year", "!2015 - 2020", "!2015-2020"),
    ("fwci", "1.5 - 2", "1.5-2"),
    ("child_works_count", "1 - 3", "1-3"),               # a ZeroWhenMissingRangeField
])
def test_a_spaced_range_is_the_range(key, spaced, joined):
    assert _filters([{key: spaced}]) == _filters([{key: joined}])


@pytest.mark.parametrize("value", [
    ">2021 !2023",        # #1032's AND lists are unchanged
    "2015-2020 !2017",
    ">10 <20",
    ">2010 -2020",        # > and an open range: two filters, not one range
    "2015 2025",          # no hyphen
    "2015",
    "2015-2025",
])
def test_other_values_are_unchanged(value):
    assert join_spaced_range(value) == value


def test_the_and_list_still_ands():
    (clause,) = _filters([{"publication_year": "2015-2020 !2017"}])
    assert len(clause["bool"]["must"]) == 2


def _rows(filter_string):
    return parse_url_to_oqo("works", filter_string=filter_string).to_dict()["filter_rows"]


@pytest.mark.parametrize("spaced, joined", [
    ("publication_year:2015 - 2025", "publication_year:2015-2025"),
    ("publication_year:2015 -", "publication_year:2015-"),
    ("publication_year:2019 - 2025,open_access.is_oa:true", "publication_year:2019-2025,open_access.is_oa:true"),
])
def test_the_echo_reads_it_as_the_range(spaced, joined):
    assert _rows(spaced) == _rows(joined)


def test_dates_and_terms_are_not_joined():
    """Only number filters: a date or term value with ` - ` keeps the `+` AND reading."""
    assert _rows("publication_date:2020-01-01 2020-02-01") == _rows(
        "publication_date:2020-01-01,publication_date:2020-02-01")
    assert _rows("institutions.country_code:fr - gb") == _rows(
        "institutions.country_code:fr,institutions.country_code:-,institutions.country_code:gb")
