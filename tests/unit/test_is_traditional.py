"""`is_traditional`: a work type is a traditional scholarly work or not (oxjob #2064).

The works filter `is_traditional:true|false` expands to the traditional types (a terms query on `type`, no
reindex), every work object carries `is_traditional` computed from its type, and group_by=is_traditional counts
with the filter's own two queries. The type list lives in core/work_type_classes.py.
"""
import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.group_by.utils import is_boolean_field
from core.work_type_classes import NON_TRADITIONAL_TYPES, TRADITIONAL_TYPES, is_traditional
from core.work_type_values import work_types
from works.fields import fields_dict
from works.schemas import WorksSchema

# The calls Jason and Kyle made (charter plans/worktype.md § 2, 5-6 Nov 2026; #1647 table of 22 Oct).
TRADITIONAL = {
    "article", "book", "book-chapter", "dissertation", "conference-paper", "preprint", "review", "editorial",
    "letter", "erratum", "retraction", "book-review", "data-paper", "software-paper",
}
NOT_TRADITIONAL = {
    "dataset", "software", "conference-abstract", "report", "reference-entry", "peer-review", "standard",
    "supplementary-materials", "paratext", "other", "study-registration", "libguides",
}


def _query(value):
    q = filter_records(fields_dict, [{"is_traditional": value}], Search()).to_dict()["query"]
    return q["bool"]["filter"][0]


def test_the_calls_are_the_decided_ones():
    assert TRADITIONAL_TYPES == TRADITIONAL
    assert NON_TRADITIONAL_TYPES == NOT_TRADITIONAL
    assert not TRADITIONAL_TYPES & NON_TRADITIONAL_TYPES


def test_every_work_type_is_classified():
    # A new type in config/work-types.yaml fails here until it is put in one of the two sets.
    unclassified = set(work_types()) - TRADITIONAL_TYPES - NON_TRADITIONAL_TYPES
    assert not unclassified, f"classify these in core/work_type_classes.py: {sorted(unclassified)}"


def test_only_the_coming_and_going_types_are_classified_but_not_in_the_vocabulary():
    # study-registration arrives with oxjob #2063; libguides leaves 7 Nov 2026 (oxjob #1647)
    assert (TRADITIONAL_TYPES | NON_TRADITIONAL_TYPES) - set(work_types()) <= {"study-registration", "libguides"}


def test_true_is_the_traditional_types():
    assert _query("true") == {"terms": {"type": sorted(TRADITIONAL)}}
    assert _query("TRUE") == _query("true")


def test_false_is_every_other_type():
    # NOT(true), so true and false always split the results, whatever types the index holds
    assert _query("false") == {"bool": {"must_not": [{"terms": {"type": sorted(TRADITIONAL)}}]}}


@pytest.mark.parametrize("value", ["maybe", "null", "!null", "!true", "article"])
def test_only_true_or_false(value):
    with pytest.raises(APIQueryParamsError, match="must be true or false"):
        _query(value)


def test_group_by_counts_with_the_filter_queries():
    field = fields_dict["is_traditional"]
    assert is_boolean_field(field)
    assert field.query_for("true").to_dict() == _query("true")
    assert field.query_for("false").to_dict() == _query("false")


def test_not_sortable():
    # no index field holds it
    assert fields_dict["is_traditional"].sortable is False


@pytest.mark.parametrize("work_type, expected", [
    ("article", True), ("preprint", True), ("editorial", True), ("software-paper", True),
    ("dataset", False), ("paratext", False), ("other", False), ("study-registration", False),
    ("some-future-type", False), (None, None), ("", None),
])
def test_the_value_on_a_work(work_type, expected):
    assert is_traditional(work_type) is expected


class _Meta:
    score = None


class _Hit:
    """An ES hit as the schema reads it (attributes + meta.score)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.meta = _Meta()


def test_work_objects_carry_it_after_type():
    out = WorksSchema().dump(_Hit(id="https://openalex.org/W1", type="article"))
    keys = list(out)
    assert out["is_traditional"] is True
    assert keys.index("is_traditional") == keys.index("type") + 1
    assert WorksSchema().dump(_Hit(id="https://openalex.org/W2", type="dataset"))["is_traditional"] is False
    assert WorksSchema().dump(_Hit(id="https://openalex.org/W3"))["is_traditional"] is None


def test_select_takes_it():
    out = WorksSchema(only=("id", "is_traditional")).dump(_Hit(id="https://openalex.org/W1", type="review"))
    assert out == {"id": "https://openalex.org/W1", "is_traditional": True}
