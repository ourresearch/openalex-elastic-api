"""oxjob #1682: an OR of plain OpenAlex IDs compiles to one `terms` clause (not a bool.should of `term` clauses).
Query-DSL only (no ES, no app context): run with --noconftest."""
import json

import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from works.fields import fields_dict as works_fields_dict


def _body(filters):
    return filter_records(works_fields_dict, filters, Search()).to_dict()


def _terms_clauses(body):
    found = []

    def walk(o):
        if isinstance(o, dict):
            if "terms" in o:
                found.append(o["terms"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(body)
    return found


def test_openalex_id_or_is_one_terms_clause():
    body = _body([{"openalex_id": "W2741809807|w2100837269"}])
    terms = _terms_clauses(body)
    assert len(terms) == 1
    (field, values), = terms[0].items()
    assert values == ["https://openalex.org/W2741809807", "https://openalex.org/W2100837269"]
    assert "should" not in json.dumps(body)


def _term_clauses(body):
    found = []

    def walk(o):
        if isinstance(o, dict):
            if "term" in o:
                found.append(o["term"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(body)
    return found


@pytest.mark.parametrize("param,a,b", [
    ("authorships.institutions.lineage", "I136199984", "I27837315"),
    ("authorships.institutions.id", "I136199984", "I27837315"),
    ("primary_location.source.id", "S137773608", "S4210178049"),
    ("authorships.author.id", "A5023888391", "A5003442464"),
    ("topics.id", "T10017", "T11636"),
    ("openalex_id", "W2741809807", "W2100837269"),
])
def test_same_field_and_values_as_the_single_value_path(param, a, b):
    # the single-value path is unchanged; the OR must hit the same field with the same values
    singles = [t for v in (a, b) for t in _term_clauses(_body([{param: v}])) if "is_xpac" not in t]
    assert len(singles) == 2
    (field_a, val_a), = singles[0].items()
    (field_b, val_b), = singles[1].items()
    assert field_a == field_b
    terms = [t for t in _terms_clauses(_body([{param: f"{a}|{b}"}]))]
    assert terms == [{field_a: [val_a, val_b]}]


def test_invalid_id_still_raises():
    with pytest.raises(APIQueryParamsError):
        _body([{"openalex_id": "W2741809807|not-an-id"}])


def test_negated_or_keeps_must_not_path():
    body = json.dumps(_body([{"openalex_id": "!W2741809807|W2100837269"}]))
    assert "must_not" in body


def test_repository_or_keeps_bool_should():
    body = _body([{"repository": "S4306400194|S4306400562"}])
    assert "should" in json.dumps(body)
