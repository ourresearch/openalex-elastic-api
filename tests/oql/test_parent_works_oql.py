"""OQL words for parent and child works (oxjob #2065).

    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_parent_works_oql.py --noconftest -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.diagnostics import OQLError
from query_translation.url_parser import parse_url_to_oqo
from query_translation.validator import validate_oqo

W = "W3109397498"


def _leaf(oql):
    oqo = L.parse(oql)
    return oqo, oqo.to_dict()["filter_rows"][0]


@pytest.mark.parametrize("oql", [
    f"works where parent work is {W}",
    f"works where parent works is {W}",
    f"works where part of is {W}",
    f"works where parent_works.id is {W}",
])
def test_parent_work_word_and_aliases(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "parent_works.id", "value": W}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == f"works where parent work is ({W})"


def test_parent_work_takes_a_work_id():
    oqo, _ = _leaf("works where parent work is A5023888391")
    assert [e["type"] for e in validate_oqo(oqo).to_dict()["errors"]] == ["invalid_value"]


@pytest.mark.parametrize("oql", [
    "works where relationship to parent work is data-series",
    "works where relationship to parent work is Data-Series",
    "works where parent work relationship is data-series",
    "works where relationship is data-series",
    "works where parent_works.relationship is data-series",
])
def test_relationship_word_and_aliases(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "parent_works.relationship", "value": "data-series"}
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == "works where relationship to parent work is (data-series)"


@pytest.mark.parametrize("value", ["volume", "component", "data-series", "part",
                                   "relationships/part", "https://openalex.org/relationships/part"])
def test_the_four_relationships_validate(value):
    oqo = parse_url_to_oqo("works", filter_string=f"parent_works.relationship:{value}")
    assert validate_oqo(oqo).valid, validate_oqo(oqo).to_dict()


def test_a_relationship_outside_the_vocabulary_is_invalid():
    oqo, _ = _leaf("works where relationship to parent work is chapter")
    assert [e["type"] for e in validate_oqo(oqo).to_dict()["errors"]] == ["invalid_value"]


@pytest.mark.parametrize("oql,value", [
    ("works where has parent work is true", True),
    ("works where has parent work is false", False),
    ("works where has_parent_work is true", True),
    ("works where it has a parent work", True),
    ("works where it doesn't have a parent work", False),
])
def test_has_parent_work(oql, value):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "has_parent_work", "value": value}
    assert validate_oqo(oqo).valid


@pytest.mark.parametrize("oql", [f"works where work lineage is {W}", f"works where lineage is {W}"])
def test_work_lineage(oql):
    oqo, leaf = _leaf(oql)
    assert leaf == {"column_id": "lineage", "value": W}
    assert validate_oqo(oqo).valid
    assert L.parse(L.render(oqo)).to_dict() == oqo.to_dict()


def test_institution_and_publisher_lineage_words_are_unchanged():
    oqo, leaf = _leaf("institutions where lineage is I27837315")
    assert leaf == {"column_id": "lineage", "value": "I27837315"}
    assert L.render(oqo) == "institutions where lineage is (I27837315)"
    assert L.render(parse_url_to_oqo("publishers", filter_string="lineage:P4310320990")) == \
        "publishers where lineage is (P4310320990)"
    _, leaf = _leaf("works where institution is I27837315")
    assert leaf["column_id"] == "authorships.institutions.lineage"


@pytest.mark.parametrize("oql,leaf", [
    ("works where child works count > 0", {"column_id": "child_works_count", "value": 0, "operator": ">"}),
    ("works where child works count is 0", {"column_id": "child_works_count", "value": 0}),
    ("works where child_works_count >= 5", {"column_id": "child_works_count", "value": 5, "operator": ">="}),
    ("works where parts count >= 5", {"column_id": "child_works_count", "value": 5, "operator": ">="}),
])
def test_child_works_count(oql, leaf):
    oqo, got = _leaf(oql)
    assert got == leaf
    assert validate_oqo(oqo).valid
    assert L.is_integer_column("child_works_count")


@pytest.mark.parametrize("word", ["relationship to parent work", "parent work", "has parent work"])
def test_group_by(word):
    oqo = L.parse(f"works where type is book group by {word}")
    assert validate_oqo(oqo).valid
    assert L.render(oqo) == f"works where type is (book) group by {word}"


def test_group_by_lineage_is_refused():
    oqo = L.parse("works where type is book group by work lineage")
    assert [e["type"] for e in validate_oqo(oqo).to_dict()["errors"]] == ["invalid_column"]


@pytest.mark.parametrize("oql", ["relationships", "relationships where works count > 100"])
def test_relationships_entity(oql):
    oqo = L.parse(oql)
    assert oqo.get_rows == "relationships"
    assert validate_oqo(oqo).valid


@pytest.mark.parametrize("oql", [f"works where volume is {W}", f"works where volume.id is {W}",
                                 "works where type is book group by volume"])
def test_the_volume_word_is_retired(oql):
    with pytest.raises(OQLError) as err:
        L.parse(oql)
    assert err.value.code == "OQL_UNKNOWN_FIELD"
    assert "retired" in err.value.message
    assert "parent work" in err.value.fixit
