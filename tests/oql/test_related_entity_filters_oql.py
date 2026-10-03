"""OQL + OQO validation for the topic-hierarchy and geo filters on non-works entities (oxjob #1526).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_related_entity_filters_oql.py --noconftest -q
"""

import pytest

from query_translation import oql_lang as L
from query_translation.url_parser import parse_url_to_oqo
from query_translation.validator import validate_oqo


@pytest.mark.parametrize(
    "oql, column",
    [
        ("authors where subfield is (subfields/1702)", "topics.subfield.id"),
        ("authors where field is (fields/17)", "topics.field.id"),
        ("authors where domain is (domains/3)", "topics.domain.id"),
        ("sources where subfield is (subfields/1204)", "topics.subfield.id"),
        ("institutions where subfield is (subfields/1702)", "topics.subfield.id"),
        ("institutions where field is (fields/17)", "topics.field.id"),
        ("institutions where domain is (domains/3)", "topics.domain.id"),
        ("institutions where region is (Catalonia)", "geo.region"),
        ("institutions where city is (Paris)", "geo.city"),
    ],
)
def test_word_parses_to_the_entity_column_and_validates(oql, column):
    oqo = L.parse(oql)
    assert oqo.to_dict()["filter_rows"][0]["column_id"] == column
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


@pytest.mark.parametrize(
    "entity, filter_string",
    [
        ("authors", "topics.subfield.id:1702"),
        ("authors", "topics.field.id:17,topics.domain.id:3"),
        ("sources", "topics.subfield.id:1204"),
        ("institutions", "topics.subfield.id:1702"),
        ("institutions", "geo.region:Catalonia"),
        ("institutions", 'geo.city:"New York"'),
    ],
)
def test_url_filter_validates(entity, filter_string):
    oqo = parse_url_to_oqo(entity, filter_string=filter_string)
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


@pytest.mark.parametrize(
    "oql",
    ["institutions where region is (Catalonia)", "institutions where city is (Paris)"],
)
def test_geo_renders_back_identically(oql):
    assert L.render(L.parse(oql)) == oql
