"""`+` (a space, once a URL is read) is AND within one filter, the same as repeating it (oxjob #1032).

1. Number filters refused it: publication_year:>2021+!2023 answered "Value for param publication_year
   must be a number." while publication_year:>2021,publication_year:!2023 answered 53,762,327 works
   (ZD 2601, 16 Nov 2026). Dates and terms already took it.
2. The x_query echo read an AND list as one quoted value: institutions.country_code:fr+gb ran
   fr AND gb (324,255 works) but echoed `country_code:"fr gb"`, a different query; and
   raw_affiliation_strings:Harvard University ran the AND of two strings but echoed the quoted phrase.

No ES, no app:
    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_plus_and_1032.py --noconftest -q
"""
import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import render_oqo_to_url
from works.fields import fields_dict as works_fields


def _filters(params):
    return filter_records(works_fields, params, Search()).to_dict()["query"]["bool"]["filter"]


def _and_clauses(key, value):
    """The clauses one `key:value` with spaces ANDs together."""
    (clause,) = _filters([{key: value}])
    return clause["bool"]["must"]


def _repeated_clauses(key, values):
    """The clauses the repeated filter `key:v1,key:v2` applies."""
    return _filters([{key: v} for v in values])


# ---------- 1. number filters take `+` ----------

@pytest.mark.parametrize("key, value", [
    ("publication_year", ">2021 !2023"),       # the ticket's example
    ("publication_year", "2015-2020 !2017"),
    ("cited_by_count", ">10 <20"),
    ("cited_by_count", "  >10   <20 "),       # extra spaces are one separator
    ("fwci", ">1 <2.5"),
    ("child_works_count", ">0 !3"),           # a ZeroWhenMissingRangeField
])
def test_number_filter_plus_is_the_repeated_filter(key, value):
    assert _and_clauses(key, value) == _repeated_clauses(key, value.split())


@pytest.mark.parametrize("value", ["2020", " 2020", "2020 ", ">2021", "!2023", "2015-2020"])
def test_one_number_is_unchanged(value):
    """A single number with a stray space isn't an AND list: same query as before this change."""
    (clause,) = _filters([{"publication_year": value}])
    assert "must" not in clause.get("bool", {})


@pytest.mark.parametrize("value", [">2021 x", "2020 nan", ">2021 2016_2019"])
def test_a_bad_number_in_the_list_is_still_a_400(value):
    with pytest.raises(APIQueryParamsError):
        _filters([{"publication_year": value}])


def test_terms_and_dates_unchanged():
    assert _and_clauses("institutions.country_code", "fr gb") == _repeated_clauses(
        "institutions.country_code", ["fr", "gb"])
    assert _and_clauses("publication_date", ">2020-01-01 <2020-02-01") == _repeated_clauses(
        "publication_date", [">2020-01-01", "<2020-02-01"])


def test_boolean_filters_still_refuse_an_and_list():
    with pytest.raises(APIQueryParamsError):
        _filters([{"is_oa": "true false"}])


# ---------- 2. the echo reads `+` as AND ----------

def _rows(filter_string):
    return parse_url_to_oqo("works", filter_string=filter_string).to_dict()["filter_rows"]


@pytest.mark.parametrize("plus, repeated", [
    ("institutions.country_code:fr gb", "institutions.country_code:fr,institutions.country_code:gb"),
    ("institutions.country_code:fr !gb", "institutions.country_code:fr,institutions.country_code:!gb"),
    ("publication_year:>2021 !2023", "publication_year:>2021,publication_year:!2023"),
    ("cited_by_count:>10 <20", "cited_by_count:>10,cited_by_count:<20"),
    ("publication_date:>2020-01-01 <2020-02-01",
     "publication_date:>2020-01-01,publication_date:<2020-02-01"),
    ("authorships.author.id:A5079208483 A5027467000",
     "authorships.author.id:A5079208483,authorships.author.id:A5027467000"),
    ("raw_affiliation_strings:Harvard University",
     "raw_affiliation_strings:Harvard,raw_affiliation_strings:University"),
])
def test_plus_echoes_as_the_repeated_filter(plus, repeated):
    assert _rows(plus) == _rows(repeated)


@pytest.mark.parametrize("filter_string, value", [
    ('institutions.country_code:"fr gb"', "fr gb"),             # quoted: one value
    ("locations.source.type:book series", "book series"),       # a source type with a space (#1035)
    ("primary_location.source.type:ebook platform", "ebook platform"),
    ('awards.funder_award_id:"973 Program"', "973 Program"),
])
def test_one_value_stays_one_row(filter_string, value):
    rows = _rows(filter_string)
    assert len(rows) == 1 and rows[0]["value"] == value


@pytest.mark.parametrize("filter_string", [
    "institutions.country_code:fr gb",
    "publication_year:>2021 !2023",
    "raw_affiliation_strings:Harvard University",
    "locations.source.type:book series",
])
def test_echoed_url_runs_the_same_query(filter_string):
    """The x_query url parses back to the same rows (it used to quote `fr gb` into one value)."""
    oqo = parse_url_to_oqo("works", filter_string=filter_string)
    rendered = render_oqo_to_url(oqo)["filter"]
    assert parse_url_to_oqo("works", filter_string=rendered).to_dict() == oqo.to_dict()


def test_search_filters_keep_their_spaces():
    rows = _rows("title.search:machine learning")
    assert len(rows) == 1 and rows[0]["value"] == "machine learning"
