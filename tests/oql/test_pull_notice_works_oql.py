"""OQL words for pull notices (oxjob #2264): "pull notice" (the notice's work id) and "pull notice link type"
(retraction, withdrawal, removal).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_pull_notice_works_oql.py --noconftest -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.url_parser import parse_url_to_oqo
from query_translation.validator import validate_oqo

NOTICE = "W4245876183"


def _leaf(oql):
    oqo = L.parse(oql)
    return oqo, oqo.to_dict()["filter_rows"][0]


@pytest.mark.parametrize("oql", [
    f"works where pull notice is {NOTICE}",
    f"works where pull notices is {NOTICE}",
    f"works where pull_notice_works.id is {NOTICE}",
])
def test_pull_notice_word_and_aliases(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "pull_notice_works.id", "value": NOTICE}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == f"works where pull notice is ({NOTICE})"
    assert L.parse(L.render(oqo)).to_dict() == oqo.to_dict()


@pytest.mark.parametrize("oql", [
    "works where pull notice link type is withdrawal",
    "works where pull notice type is withdrawal",
    "works where link type of pull notice is withdrawal",
    "works where pull_notice_works.link_type is withdrawal",
])
def test_pull_notice_link_type_word_and_aliases(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "pull_notice_works.link_type", "value": "withdrawal"}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where pull notice link type is (withdrawal)"


@pytest.mark.parametrize("value", ["retraction", "removal", "link-types/withdrawal",
                                   "https://openalex.org/link-types/retraction", "relationships/removal"])
def test_link_type_values_validate(value):
    oqo = parse_url_to_oqo("works", filter_string=f"pull_notice_works.link_type:{value}")
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


def test_an_unknown_link_type_is_invalid():
    result = validate_oqo(parse_url_to_oqo("works", filter_string="pull_notice_works.link_type:erratum"))
    assert not result.valid
    assert result.errors[0].type == "invalid_value"


def test_the_new_link_types_are_relationships_too():
    oqo = parse_url_to_oqo("works", filter_string="parent_works.link_type:retraction")
    assert validate_oqo(oqo).valid


def test_group_by_pull_notice_link_type():
    oqo = L.parse("works where type is article group by pull notice link type")
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where type is (article) group by pull notice link type"
