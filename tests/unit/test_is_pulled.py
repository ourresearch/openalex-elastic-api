"""`is_pulled`: the work's publisher, host or authors retracted, withdrew or removed it (oxjob #2264).

Jason's decisions 1-2 (15 Nov 2026, oxjobs plans/retractions.md § 5). Walden computes the flag; the works index
carries it only on docs re-stamped since it shipped, so `false` is NOT true (a doc without the field is not pulled),
group_by counts with the same two queries, and the work object shows false when the doc lacks the field.
"""
import pytest
from elasticsearch_dsl import Search
from elasticsearch_dsl.utils import AttrDict  # what ES hits and Lakebase docs (works/lakebase.py) are

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.group_by.utils import is_boolean_field
from works.fields import fields_dict
from works.schemas import WorksSchema


def _query(value):
    q = filter_records(fields_dict, [{"is_pulled": value}], Search()).to_dict()["query"]
    return q["bool"]["filter"][0]


def test_true_is_a_term_on_the_index_field():
    assert _query("true") == {"term": {"is_pulled": "true"}}
    assert _query("TRUE") == _query("true")


def test_false_is_not_true_so_a_doc_without_the_field_counts():
    assert _query("false") == {"bool": {"must_not": [{"term": {"is_pulled": "true"}}]}}


@pytest.mark.parametrize("value", ["maybe", "null", "!null", "withdrawn"])
def test_only_true_or_false(value):
    with pytest.raises(APIQueryParamsError, match="must be true or false"):
        _query(value)


def test_group_by_counts_with_the_filter_queries():
    field = fields_dict["is_pulled"]
    assert is_boolean_field(field)
    assert field.query_for("true").to_dict() == _query("true")
    assert field.query_for("false").to_dict() == _query("false")


def test_other_booleans_unchanged():
    # absent_means_false is opt-in: is_retracted stays a plain term on both values
    q = filter_records(fields_dict, [{"is_retracted": "false"}], Search()).to_dict()["query"]
    assert q["bool"]["filter"][0] == {"term": {"is_retracted": "false"}}


@pytest.mark.parametrize("doc, expected", [
    ({"id": "https://openalex.org/W1"}, False),                       # not re-stamped since the field shipped
    ({"id": "https://openalex.org/W1", "is_pulled": False}, False),
    ({"id": "https://openalex.org/W1", "is_pulled": True}, True),
])
def test_work_object_shows_the_flag(doc, expected):
    out = WorksSchema(only=("id", "is_pulled")).dump(AttrDict(doc))
    assert out["is_pulled"] is expected


def test_vector_search_checks_it_on_the_works_index():
    # the vector index has no is_pulled field: the filter rides with the corpus clause (oxjob #1649's post-check)
    from core.vector_index import _pop_corpus_clause
    params = {"filters": [{"is_pulled": "true"}, {"type": "article"}]}
    clause = _pop_corpus_clause(params)
    assert params["filters"] == [{"type": "article"}]
    assert clause == {"bool": {"filter": [{"term": {"is_pulled": "true"}}]}}
