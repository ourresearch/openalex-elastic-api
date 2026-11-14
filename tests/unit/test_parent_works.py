"""Parent and child works (oxjob #2065). No ES, no app.

Works carry `parent_works` [{id, display_name, relationship}], `lineage` (the work, then its
ancestors nearest first) and `child_works_count`. The index stores the last two only on works that
have a parent or a child, so the API fills them (`[self]`, 0) and the filters count a work with no
stored value the same way. `volume` (oxjob #1554) is retired into `parent_works`.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_parent_works.py --noconftest -q
"""
import logging

import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.fields import WorkLineageField, ZeroWhenMissingRangeField
from core.filter import filter_records
from core.group_by.display_names import get_key_display_name
from core.sort import get_sort_fields, sort_refusal, with_tie_break
from core.utils import check_select_field, is_field_class
from core.validate import group_by_rejection
from works.fields import fields_dict
from works.schemas import WorksSchema

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given

W = "https://openalex.org/W3109397498"
W2 = "https://openalex.org/W2741809807"
NO_COUNT = {"bool": {"must_not": [{"exists": {"field": "child_works_count"}}]}}


def _q(key, value):
    """The one filter clause `filter=<key>:<value>` adds."""
    (clause,) = filter_records(fields_dict, [{key: value}], Search()).to_dict()["query"]["bool"]["filter"]
    return clause


def _either(*clauses):
    return {"bool": {"should": list(clauses), "minimum_should_match": 1}}


def _neither(positive):
    """NOT of a clause, as Elasticsearch DSL writes it: NOT (a OR b) is must_not [a, b]."""
    should = positive.get("bool", {}).get("should")
    return {"bool": {"must_not": should if should else [positive]}}


def _doc(**fields):
    """A works doc as the schema gets it (an Elasticsearch hit or a Lakebase row)."""
    from works.lakebase import LakebaseHit

    return LakebaseHit(fields)


# --- lineage: the work itself OR a stored lineage that holds it ---------------------------------
LINEAGE_W = _either({"term": {"id": W}}, {"term": {"lineage.lower": W}})


@pytest.mark.parametrize("value", ["W3109397498", "w3109397498", W])
def test_lineage_matches_the_work_itself_and_every_work_under_it(value):
    assert _q("lineage", value) == LINEAGE_W


def test_lineage_negation_is_the_exact_complement():
    assert _q("lineage", "!W3109397498") == _neither(LINEAGE_W)
    assert _q("lineage", "!W3109397498") == {"bool": {"must_not": [{"term": {"id": W}}, {"term": {"lineage.lower": W}}]}}


def test_lineage_or_list():
    one = _either({"term": {"id": W2}}, {"term": {"lineage.lower": W2}})
    assert _q("lineage", "W3109397498|W2741809807") == _either(LINEAGE_W, one)


def test_lineage_terms_query_for_a_collection_of_works():
    q = fields_dict["lineage"].build_terms_query(["W3109397498", "W2741809807"]).to_dict()
    assert q == _either({"terms": {"id": [W, W2]}}, {"terms": {"lineage.lower": [W, W2]}})


def test_lineage_is_never_null():
    assert _q("lineage", "null") == {"match_none": {}}
    assert _q("lineage", "!null") == {"match_all": {}}


@pytest.mark.parametrize("value", ["I27837315", "A5023888391", "!I27837315"])
def test_lineage_takes_work_ids_only(value):
    with pytest.raises(APIQueryParamsError) as err:
        _q("lineage", value)
    assert "lineage takes works IDs" in str(err.value)


def test_the_works_lineage_key_leaves_the_institution_lineage_filters_alone():
    assert type(fields_dict["lineage"]) is WorkLineageField
    inst = _q("authorships.institutions.lineage", "I27837315")
    assert inst == {"term": {"authorships_full.institutions.lineage": "https://openalex.org/I27837315"}}
    for param in ("institution_assertions.lineage", "primary_location.source.host_organization_lineage",
                  "locations.source.host_institution_lineage"):
        assert type(fields_dict[param]).__name__ == "OpenAlexIDField"


def test_lineage_is_a_filter_only():
    field = fields_dict["lineage"]
    assert group_by_rejection(field).startswith("Cannot group by lineage: ")
    assert "parent_works.id" in group_by_rejection(field)
    assert sort_refusal("lineage", field).startswith("Cannot sort by lineage")


# --- child_works_count: no stored value counts as 0 ---------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("0", _either({"term": {"child_works_count": "0"}}, NO_COUNT)),
    ("<1", _either({"range": {"child_works_count": {"lt": 1.0}}}, NO_COUNT)),
    ("-3", _either({"range": {"child_works_count": {"lte": 3.0}}}, NO_COUNT)),
    ("0-", _either({"range": {"child_works_count": {"gte": 0.0}}}, NO_COUNT)),
    ("0-5", _either({"range": {"child_works_count": {"gte": 0.0, "lte": 5.0}}}, NO_COUNT)),
    # 0 is outside these, so a work with no stored value is too
    (">0", {"range": {"child_works_count": {"gt": 0.0}}}),
    ("1-", {"range": {"child_works_count": {"gte": 1.0}}}),
    ("3", {"term": {"child_works_count": "3"}}),
    ("2-5", {"range": {"child_works_count": {"gte": 2.0, "lte": 5.0}}}),
    ("<0", {"range": {"child_works_count": {"lt": 0.0}}}),
])
def test_child_works_count_counts_a_missing_value_as_zero(value, expected):
    assert _q("child_works_count", value) == expected


@pytest.mark.parametrize("value", ["0", "3", "0-5", "2-5"])
def test_child_works_count_negation_is_the_exact_complement(value):
    assert _q("child_works_count", "!" + value) == _neither(_q("child_works_count", value))


def test_child_works_count_not_zero_leaves_out_works_with_no_stored_value():
    assert _q("child_works_count", "!0") == {"bool": {"must_not": [{"term": {"child_works_count": "0"}}, NO_COUNT]}}
    assert _q("child_works_count", "!3") == {"bool": {"must_not": [{"term": {"child_works_count": "3"}}]}}


def test_child_works_count_is_never_null():
    assert _q("child_works_count", "null") == {"match_none": {}}
    assert _q("child_works_count", "!null") == {"match_all": {}}


def test_child_works_count_or_list():
    assert _q("child_works_count", "0|3") == _either(
        _either({"term": {"child_works_count": "0"}}, NO_COUNT), {"term": {"child_works_count": "3"}})


@pytest.mark.parametrize("value", ["many", "1_000", "!x"])
def test_child_works_count_wants_a_number(value):
    with pytest.raises(APIQueryParamsError) as err:
        _q("child_works_count", value)
    assert "must be a number" in str(err.value)


def test_child_works_count_keeps_the_rules_of_a_number():
    field = fields_dict["child_works_count"]
    assert type(field) is ZeroWhenMissingRangeField and is_field_class(field, "RangeField")
    assert group_by_rejection(field) == "Cannot group by date, number, or search fields."
    assert sort_refusal("child_works_count", field) is None


def test_child_works_count_sorts_a_missing_value_as_zero():
    # ascending: works with no stored value come first, with the zeros (Elasticsearch puts them last)
    sort = get_sort_fields(fields_dict, None, {"child_works_count": "asc"})
    assert sort == [{"child_works_count": {"order": "asc", "missing": 0}}]
    assert with_tie_break(sort, ["-cited_by_count", "id"], "works-v41") == sort + ["-publication_date", "id"]
    assert Search().sort(*sort).to_dict()["sort"] == sort  # Elasticsearch DSL takes the entry
    # descending: missing last is already right
    assert get_sort_fields(fields_dict, None, {"child_works_count": "desc"}) == ["-child_works_count"]


# --- parent_works.id, parent_works.relationship, has_parent_work ---------------------------------
@pytest.mark.parametrize("value", ["W3109397498", W])
def test_parent_works_id_lists_the_works_whose_parent_is_that_work(value):
    assert _q("parent_works.id", value) == {"term": {"parent_works.id.lower": W}}
    assert _q("parent_works.id", "!" + value) == {"bool": {"must_not": [{"term": {"parent_works.id.lower": W}}]}}


def test_parent_works_id_takes_work_ids_only():
    with pytest.raises(APIQueryParamsError) as err:
        _q("parent_works.id", "S137773608")
    assert "parent_works.id takes works IDs" in str(err.value)


@pytest.mark.parametrize("value", ["volume", "relationships/volume", "https://openalex.org/relationships/volume"])
def test_relationship_takes_the_key_the_short_id_and_the_full_id(value):
    assert _q("parent_works.relationship", value) == {"term": {"parent_works.relationship.lower": "volume"}}
    assert _q("parent_works.relationship", "!" + value) == {
        "bool": {"must_not": [{"term": {"parent_works.relationship.lower": "volume"}}]}}


def test_relationship_or_list_and_entity_type():
    assert _q("parent_works.relationship", "component|relationships/data-series") == {
        "terms": {"parent_works.relationship.lower": ["component", "data-series"]}}
    assert fields_dict["parent_works.relationship"].entity_type == "relationships"
    assert group_by_rejection(fields_dict["parent_works.relationship"]) is None
    assert group_by_rejection(fields_dict["parent_works.id"]) is None


@pytest.mark.parametrize("key,name", [("volume", "Volume"), ("component", "Component"),
                                      ("data-series", "Data series"), ("part", "Part"), ("other", "other")])
def test_group_by_relationship_rows_are_named_from_the_vocabulary(key, name):
    from elasticsearch_dsl import AttrDict
    assert get_key_display_name(AttrDict({"key": key}), "parent_works.relationship") == name


def test_has_parent_work_is_an_exists_on_the_parent_id():
    exists = {"exists": {"field": "parent_works.id"}}
    assert _q("has_parent_work", "true") == exists
    assert _q("has_parent_work", "false") == {"bool": {"must_not": [exists]}}
    field = fields_dict["has_parent_work"]
    assert field.query_for("true").to_dict() == exists  # group_by counts with the same queries
    assert not field.sortable


# --- volume is retired ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["W3109397498", "W3109397498|W2741809807", "!W3109397498", "null"])
def test_the_volume_filter_answers_a_400_that_names_parent_works(value):
    with pytest.raises(APIQueryParamsError) as err:
        _q("volume.id", value)
    message = str(err.value)
    assert message.startswith("volume.id can't be used as a filter: volume was retired on 14 November 2026")
    assert "Use parent_works.id (the same work id), e.g. filter=parent_works.id:W123" in message


def test_volume_group_by_and_sort_say_the_same():
    field = fields_dict["volume.id"]
    assert group_by_rejection(field).startswith("Cannot group by volume.id: volume was retired")
    assert sort_refusal("volume.id", field).startswith("Cannot sort by volume.id: volume was retired")
    assert field.unlisted


def test_select_volume_answers_a_400_that_names_parent_works():
    schema_fields = list(WorksSchema._declared_fields)
    assert "volume" not in schema_fields
    with pytest.raises(APIQueryParamsError) as err:
        check_select_field("volume", schema_fields)
    assert "volume was retired on 14 November 2026" in str(err.value)
    assert "select=parent_works" in str(err.value)
    for field in ("parent_works", "lineage", "child_works_count"):
        check_select_field(field, schema_fields)


# --- the work record -----------------------------------------------------------------------------
ONLY = ("id", "parent_works", "lineage", "child_works_count")


def test_a_work_with_no_parent_or_child_is_its_own_lineage():
    assert WorksSchema(only=ONLY).dump(_doc(id=W)) == {
        "id": W, "parent_works": [], "lineage": [W], "child_works_count": 0}
    assert WorksSchema(only=ONLY).dump(_doc(id=W, parent_works=None, lineage=None, child_works_count=None)) == {
        "id": W, "parent_works": [], "lineage": [W], "child_works_count": 0}


def test_a_chapter_names_its_book_and_nothing_else_about_it():
    doc = {
        "id": W,
        "parent_works": [{"id": W2, "display_name": "A book", "relationship": "volume",
                          "type": "book", "asserted_by": "crossref"}],
        "lineage": [W, W2],
        "child_works_count": 0,
        "volume": {"id": W2, "display_name": "A book"},  # still in the index until walden drops it
    }
    out = WorksSchema(context={"display_relevance": False}).dump(_doc(**doc, biblio={"volume": "12"}))
    assert out["parent_works"] == [{"id": W2, "display_name": "A book", "relationship": "volume"}]
    assert list(out["parent_works"][0]) == ["id", "display_name", "relationship"]
    assert out["lineage"] == [W, W2]
    assert out["child_works_count"] == 0
    assert "volume" not in out
    assert out["biblio"]["volume"] == "12"  # the printed volume number stays


def test_a_book_counts_its_children_and_the_fields_sit_where_volume_did():
    out = WorksSchema(context={"display_relevance": False}).dump(_doc(id=W2, lineage=[W2], child_works_count=12))
    assert (out["parent_works"], out["lineage"], out["child_works_count"]) == ([], [W2], 12)
    keys = list(WorksSchema._declared_fields)
    at = keys.index("primary_location")
    assert keys[at + 1:at + 4] == ["parent_works", "lineage", "child_works_count"]


def test_the_single_work_path_serves_the_same_fields():
    """/works/W... dumps the same schema over a Lakebase or Elasticsearch doc (ids/views.py)."""
    from works.lakebase import LakebaseHit

    out = WorksSchema(context={"display_relevance": False, "single_record": True}, only=ONLY).dump(
        LakebaseHit({"id": W, "volume": {"id": W2, "display_name": "A book"}}))
    assert out == {"id": W, "parent_works": [], "lineage": [W], "child_works_count": 0}


def test_a_group_metric_over_child_works_count_counts_a_missing_value_as_zero():
    from core.group_by.buckets import _group_order

    assert _group_order(fields_dict, "child_works_count.mean", "desc")[1] == ("avg", "child_works_count", {"missing": 0})
    assert _group_order(fields_dict, "cited_by_count.mean", "desc")[1] == ("avg", "cited_by_count", {})
