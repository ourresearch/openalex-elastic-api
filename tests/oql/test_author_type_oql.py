"""OQL words for what kind of agent an author is (oxjob #2437).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_author_type_oql.py --noconftest -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.url_parser import parse_url_to_oqo
from query_translation.validator import validate_oqo


def _leaf(oql):
    oqo = L.parse(oql)
    return oqo, oqo.to_dict()["filter_rows"][0]


@pytest.mark.parametrize("oql", [
    "works where author type is software-agent",
    "works where author type is Software-Agent",
    "works where authorships.author.type is software-agent",
])
def test_author_type_word(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "authorships.author.type", "value": "software-agent"}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where author type is (software-agent)"


def test_not_software_agent_is_the_negated_leaf():
    oqo, leaf = _leaf("works where author type is not software-agent")
    assert leaf == {"column_id": "authorships.author.type", "value": "software-agent", "is_negated": True}
    url_oqo = parse_url_to_oqo("works", filter_string="authorships.author.type:!software-agent")
    assert url_oqo.to_dict()["filter_rows"] == [leaf]
    assert L.render(url_oqo) == "works where author type is (not software-agent)"


@pytest.mark.parametrize("value", ["human", "organization", "software-agent", "author-types/organization",
                                   "https://openalex.org/author-types/organization"])
def test_the_three_types_validate(value):
    oqo = parse_url_to_oqo("works", filter_string=f"authorships.author.type:{value}")
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


def test_a_type_outside_the_vocabulary_is_invalid():
    oqo, _ = _leaf("works where author type is robot")
    assert [e["type"] for e in validate_oqo(oqo).to_dict()["errors"]] == ["invalid_value"]


@pytest.mark.parametrize("oql", ["authors where type is software-agent", "authors where author type is software-agent"])
def test_authors_type(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "type", "value": "software-agent"}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "authors where author type is (software-agent)"
