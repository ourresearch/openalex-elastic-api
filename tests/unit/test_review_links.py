"""Review links and the link-types rename on works (oxjob #2481). No ES, no app.

Works carry `reviewed_by_count` (the works that review this one; the index stores it only on works that
have a review link, so no stored value counts as 0) and each `parent_works[]` item gains `link_type`, the
new name of `relationship`. The filter and group_by `parent_works.link_type` read the same index field as
`parent_works.relationship`.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_review_links.py --noconftest -q
"""
import logging

import pytest
from elasticsearch_dsl import AttrDict, Search

from core.fields import ZeroWhenMissingRangeField
from core.filter import filter_records
from core.group_by.display_names import get_key_display_name
from core.sort import get_sort_fields, sort_refusal
from core.utils import is_field_class
from core.validate import group_by_rejection
from works.fields import fields_dict
from works.schemas import WorksSchema

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given

W = "https://openalex.org/W3109397498"
W2 = "https://openalex.org/W2741809807"
NO_COUNT = {"bool": {"must_not": [{"exists": {"field": "reviewed_by_count"}}]}}


def _q(key, value):
    (clause,) = filter_records(fields_dict, [{key: value}], Search()).to_dict()["query"]["bool"]["filter"]
    return clause


def _either(*clauses):
    return {"bool": {"should": list(clauses), "minimum_should_match": 1}}


def _doc(**fields):
    from works.lakebase import LakebaseHit

    return LakebaseHit(fields)


# --- reviewed_by_count: no stored value counts as 0 ----------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("0", _either({"term": {"reviewed_by_count": "0"}}, NO_COUNT)),
    ("<1", _either({"range": {"reviewed_by_count": {"lt": 1.0}}}, NO_COUNT)),
    ("0-2", _either({"range": {"reviewed_by_count": {"gte": 0.0, "lte": 2.0}}}, NO_COUNT)),
    (">0", {"range": {"reviewed_by_count": {"gt": 0.0}}}),
    ("2", {"term": {"reviewed_by_count": "2"}}),
    ("1-3", {"range": {"reviewed_by_count": {"gte": 1.0, "lte": 3.0}}}),
])
def test_reviewed_by_count_counts_a_missing_value_as_zero(value, expected):
    assert _q("reviewed_by_count", value) == expected


@pytest.mark.parametrize("value", ["0", ">0", "2", "0-2"])
def test_reviewed_by_count_negation_is_the_exact_complement(value):
    positive = _q("reviewed_by_count", value)
    should = positive.get("bool", {}).get("should")
    assert _q("reviewed_by_count", "!" + value) == {"bool": {"must_not": should if should else [positive]}}


def test_reviewed_by_count_is_never_null():
    assert _q("reviewed_by_count", "null") == {"match_none": {}}
    assert _q("reviewed_by_count", "!null") == {"match_all": {}}


def test_reviewed_by_count_keeps_the_rules_of_a_count_stored_only_where_it_isnt_zero():
    field = fields_dict["reviewed_by_count"]
    assert type(field) is ZeroWhenMissingRangeField and is_field_class(field, "RangeField")
    assert field.documentation_link == "https://help.openalex.org/data/works/attributes/#reviewed_by_count"
    assert "link_type:review" in field.docstring
    assert sort_refusal("reviewed_by_count", field) is None
    # like child_works_count: a plain group_by would leave out every work with no stored value
    assert group_by_rejection(field) == "Cannot group by date, number, or search fields."


def test_reviewed_by_count_sorts_a_missing_value_as_zero():
    assert get_sort_fields(fields_dict, None, {"reviewed_by_count": "asc"}) == [
        {"reviewed_by_count": {"order": "asc", "missing": 0}}]
    assert get_sort_fields(fields_dict, None, {"reviewed_by_count": "desc"}) == ["-reviewed_by_count"]


def test_a_group_metric_over_reviewed_by_count_counts_a_missing_value_as_zero():
    from core.group_by.buckets import _group_order

    assert _group_order(fields_dict, "reviewed_by_count.mean", "desc")[1] == ("avg", "reviewed_by_count", {"missing": 0})


def test_no_has_reviews_filter_and_no_api_url():
    assert "has_reviews" not in fields_dict
    assert not [k for k in WorksSchema._declared_fields if k.startswith("review") and k.endswith("_api_url")]


# --- the work record -----------------------------------------------------------------------------
def test_reviewed_by_count_sits_right_after_cited_by_count():
    keys = list(WorksSchema._declared_fields)
    assert keys[keys.index("cited_by_count") + 1] == "reviewed_by_count"


@pytest.mark.parametrize("stored,served", [(None, 0), (0, 0), (3, 3)])
def test_reviewed_by_count_serves_zero_when_missing(stored, served):
    doc = {"id": W} if stored is None else {"id": W, "reviewed_by_count": stored}
    assert WorksSchema(only=("id", "reviewed_by_count")).dump(_doc(**doc)) == {"id": W, "reviewed_by_count": served}
    assert WorksSchema(only=("id", "reviewed_by_count")).dump(AttrDict(doc))["reviewed_by_count"] == served


def test_each_parent_work_carries_its_link_type_after_its_relationship():
    parents = [{"id": W2, "display_name": "A book", "relationship": "volume"},
               {"id": W, "display_name": "A series", "relationship": "data-series"}]
    for doc in (_doc(id=W, parent_works=parents), AttrDict({"id": W, "parent_works": parents})):
        out = WorksSchema(only=("id", "parent_works")).dump(doc)
        assert [(p["relationship"], p["link_type"]) for p in out["parent_works"]] == [
            ("volume", "volume"), ("data-series", "data-series")]
        assert list(out["parent_works"][0]) == ["id", "display_name", "relationship", "link_type"]


# --- parent_works.link_type: the same filter as parent_works.relationship ------------------------
@pytest.mark.parametrize("value", ["volume", "relationships/volume", "link-types/volume",
                                   "https://openalex.org/relationships/volume",
                                   "https://openalex.org/link-types/volume"])
@pytest.mark.parametrize("key", ["parent_works.link_type", "parent_works.relationship"])
def test_link_type_filters_the_relationship_field_and_takes_every_id_form(key, value):
    assert _q(key, value) == {"term": {"parent_works.relationship.lower": "volume"}}
    assert _q(key, "!" + value) == {"bool": {"must_not": [{"term": {"parent_works.relationship.lower": "volume"}}]}}


def test_link_type_or_list_entity_type_group_by_and_sort():
    assert _q("parent_works.link_type", "component|link-types/data-series") == {
        "terms": {"parent_works.relationship.lower": ["component", "data-series"]}}
    field = fields_dict["parent_works.link_type"]
    assert field.entity_type == "link-types"
    assert fields_dict["parent_works.relationship"].entity_type == "relationships"
    assert group_by_rejection(field) is None
    assert field.alias == "parent_works.relationship"  # the group_by terms field
    assert get_sort_fields(fields_dict, None, {"parent_works.link_type": "desc"}) == ["-parent_works.relationship"]


@pytest.mark.parametrize("key,name", [("volume", "Volume"), ("data-series", "Data series"), ("review", "Review"),
                                      ("other", "other")])
@pytest.mark.parametrize("group_by", ["parent_works.link_type", "parent_works.relationship"])
def test_group_by_rows_are_named_from_the_vocabulary(group_by, key, name):
    assert get_key_display_name(AttrDict({"key": key}), group_by) == name


def test_the_two_vocabularies_hold_the_same_values():
    from core.entities import get_entity_type

    rel = [(v["id"].split("/")[1], v["display_name"]) for v in get_entity_type("relationships").values]
    lt = [(v["id"].split("/")[1], v["display_name"]) for v in get_entity_type("link-types").values]
    assert rel == lt and ("review", "Review") in lt
    assert [v["id"].split("/")[0] for v in get_entity_type("link-types").values] == ["link-types"] * len(lt)
