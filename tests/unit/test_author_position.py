"""works author-position filters (oxjob #1474). No ES, no app.

ES stores `authorships` as a flat object array, so `author_position` can't be paired
with an author or institution on the same authorship at query time. walden
sync_works precomputes six top-level fields instead; each must filter exactly like
its unpositioned sibling (`corresponding_author_ids` / `corresponding_institution_ids`
/ `authorships.countries`), only on its own ES field.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_author_position.py --noconftest -q
"""

import json

import pytest
from elasticsearch_dsl import Search

from core.fields import ENTITY_ID_PARAM_TYPES, OpenAlexIDField, TermField
from core.filter import filter_records
from core.group_by.filter import filter_group_by
from core.utils import map_filter_params
from works.fields import fields

FIELDS = {f.param: f for f in fields}
AUTHOR_IDS = ["first_author_ids", "last_author_ids"]
INSTITUTION_IDS = ["first_author_institution_ids", "last_author_institution_ids"]
COUNTRIES = ["first_author_countries", "last_author_countries"]
ALL = AUTHOR_IDS + INSTITUTION_IDS + COUNTRIES


def _query(param, value):
    f = FIELDS[param]
    f.value = value
    return f.build_query().to_dict()


def _swap(d, old, new):
    return json.loads(json.dumps(d).replace(old, new))


@pytest.mark.parametrize("param", ALL)
def test_registered_with_docs(param):
    f = FIELDS[param]
    assert f.docstring and f.documentation_link


@pytest.mark.parametrize("param", AUTHOR_IDS + INSTITUTION_IDS)
def test_id_fields_are_openalex_id_fields(param):
    assert isinstance(FIELDS[param], OpenAlexIDField)


@pytest.mark.parametrize("param", COUNTRIES)
def test_country_fields_are_term_fields(param):
    assert type(FIELDS[param]) is TermField


@pytest.mark.parametrize("param", AUTHOR_IDS)
def test_author_fields_link_to_authors(param):
    assert ENTITY_ID_PARAM_TYPES[param] == "authors"
    assert FIELDS[param].entity_type == "authors"


@pytest.mark.parametrize("param", INSTITUTION_IDS)
def test_institution_fields_link_to_institutions(param):
    assert ENTITY_ID_PARAM_TYPES[param] == "institutions"
    assert FIELDS[param].entity_type == "institutions"


@pytest.mark.parametrize(
    "value", ["A5023888391", "a5023888391", "https://openalex.org/A5023888391", "!A5023888391",
              "A5023888391|A5000000001", "null", "!null"]
)
@pytest.mark.parametrize("param", AUTHOR_IDS)
def test_author_ids_filter_like_corresponding_author_ids(param, value):
    want = _swap(_query("corresponding_author_ids", value), "corresponding_author_ids", param)
    assert _query(param, value) == want
    assert param in json.dumps(want)


@pytest.mark.parametrize("value", ["I136199984", "https://openalex.org/I136199984", "!I136199984", "null"])
@pytest.mark.parametrize("param", INSTITUTION_IDS)
def test_institution_ids_filter_like_corresponding_institution_ids(param, value):
    want = _swap(_query("corresponding_institution_ids", value), "corresponding_institution_ids", param)
    assert _query(param, value) == want


@pytest.mark.parametrize("value", ["us", "US", "!fr", "null"])
@pytest.mark.parametrize("param", COUNTRIES)
def test_countries_filter_like_authorships_countries(param, value):
    want = _swap(_query("authorships.countries", value), "authorships.countries", param)
    assert _query(param, value) == want


def test_short_author_id_matches_the_full_url_on_the_lower_field():
    q = json.dumps(_query("last_author_ids", "A5023888391"))
    assert "last_author_ids" in q and "openalex.org/a5023888391" in q.lower()


def test_last_author_and_first_author_institution_combine_as_and():
    params = map_filter_params("last_author_ids:A5023888391,first_author_institution_ids:I136199984")
    s = filter_records(FIELDS, params, Search())
    body = json.dumps(s.to_dict())
    assert "last_author_ids" in body and "first_author_institution_ids" in body
    assert "authorships" not in body  # never the flat authorships fields


@pytest.mark.parametrize("param,es", [
    ("first_author_ids", "authorships__author__display_name__autocomplete"),
    ("last_author_ids", "authorships__author__display_name__autocomplete"),
    ("first_author_institution_ids", "authorships__institutions__display_name__autocomplete"),
    ("last_author_institution_ids", "authorships__institutions__display_name__autocomplete"),
])
def test_group_by_q_searches_names(param, es):
    s = filter_group_by(FIELDS[param], param, "smith", Search())
    assert es.replace("__", ".") in json.dumps(s.to_dict())
