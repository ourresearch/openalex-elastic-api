"""OQL + OQO validation for the study-designs vocabulary (oxjob #1312).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_study_designs_oql.py --noconftest -q
"""

import pytest

from query_translation import oql_lang as L
from query_translation.url_parser import parse_url_to_oqo
from query_translation.validator import validate_oqo


def _leaf(oql):
    oqo = L.parse(oql)
    return oqo, oqo.to_dict()["filter_rows"][0]


@pytest.mark.parametrize(
    "oql",
    [
        "works where study design is meta-analysis",
        "works where study design is Meta-Analysis",
        "works where study designs is meta-analysis",
        "works where study_designs is meta-analysis",
        "works where study_designs.id is meta-analysis",
    ],
)
def test_study_design_word_and_aliases(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "study_designs.id", "value": "meta-analysis"}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where study design is (meta-analysis)"


@pytest.mark.parametrize(
    "value",
    [
        "systematic-review",
        "study-designs/systematic-review",
        "https://openalex.org/study-designs/systematic-review",
    ],
)
def test_slug_short_and_full_ids_validate(value):
    oqo = parse_url_to_oqo("works", filter_string=f"study_designs.id:{value}")
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


def test_value_outside_the_vocabulary_is_invalid():
    oqo, _ = _leaf("works where study design is rct")
    errors = validate_oqo(oqo).to_dict()["errors"]
    assert [e["type"] for e in errors] == ["invalid_value"]


def test_group_by_study_design():
    oqo = L.parse("works where type is review group by study design")
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where type is (review) group by study design"


@pytest.mark.parametrize("oql", ["study-designs", "study designs"])
def test_entity_word(oql):
    oqo = L.parse(oql)
    assert oqo.get_rows == "study-designs"
    assert validate_oqo(oqo).valid
