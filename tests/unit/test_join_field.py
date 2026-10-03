"""JoinField (oxjob #1526): query-time join filters build the right ES query without touching ES.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_join_field.py --noconftest -q
"""

import pytest

import core.join_resolver as J
from core.exceptions import APIQueryParamsError
from core.fields import BooleanField, JoinField, RangeField, TermField
from core.validate import group_by_rejection

CALLS = []


@pytest.fixture(autouse=True)
def fake_resolver(monkeypatch):
    CALLS.clear()

    def fake(entity, param, value, label):
        CALLS.append((entity, param, value))
        return {"CA": ["https://openalex.org/S1", "https://openalex.org/S2"], "true": ["https://openalex.org/S9"],
                "big": [f"https://openalex.org/S{i}" for i in range(130000)]}.get(value, [])

    monkeypatch.setattr(J, "resolve_ids", fake)


def _field(like=TermField):
    return JoinField(param="primary_location.source.country_code", target_entity="sources",
                     target_param="country_code", local_field="primary_location.source.id", like=like)


def _q(field, value):
    field.value = value
    return field.build_query().to_dict()


def test_value_resolves_on_the_related_entity_and_filters_by_id():
    assert _q(_field(), "CA") == {"terms": {"primary_location.source.id": ["https://openalex.org/S1", "https://openalex.org/S2"]}}
    assert CALLS == [("sources", "country_code", "CA")]


def test_negation_wraps_the_terms_clause():
    assert _q(_field(), "!CA") == {"bool": {"must_not": [
        {"terms": {"primary_location.source.id": ["https://openalex.org/S1", "https://openalex.org/S2"]}}]}}


def test_no_match_matches_nothing():
    assert _q(_field(), "ZZ") == {"bool": {"must_not": [{"match_all": {}}]}}


def test_large_id_sets_split_under_the_terms_clause_cap():
    clauses = _q(_field(), "big")["bool"]["should"]
    assert [len(c["terms"]["primary_location.source.id"]) for c in clauses] == [60000, 60000, 10000]


def test_boolean_false_negates_the_true_set_among_works_with_a_source():
    q = _q(_field(BooleanField), "false")
    assert CALLS == [("sources", "country_code", "true")]
    assert q == {"bool": {"must": [{"exists": {"field": "primary_location.source.id"}}],
                          "must_not": [{"terms": {"primary_location.source.id": ["https://openalex.org/S9"]}}]}}


@pytest.mark.parametrize("value", ["null", "unknown", "!null", ""])
def test_null_is_rejected_with_a_pointer_to_the_id_filter(value):
    with pytest.raises(APIQueryParamsError, match="primary_location.source.id:null"):
        _q(_field(), value)


def test_publishes_the_related_fields_type_and_is_filter_only():
    f = _field(RangeField)
    assert f.field_type == RangeField.field_type and f.operators == list(RangeField.operators)
    assert f.sortable is False
    assert "Group by primary_location.source.id" in group_by_rejection(f)
