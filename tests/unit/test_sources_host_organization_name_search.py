"""`host_organization_name.search` on /sources: select sources by the name of who runs them (oxjob #2398).

The host is a publisher or, for a repository, an institution; `host_organization_name` holds either. The bare field
is a whole-string keyword, so a word search has to run on its analyzed `.autocomplete` subfield
(search_as_you_type): `term` on the keyword would match only an exact, case-sensitive full name.
"""
import json

from elasticsearch_dsl import Search

from core.filter import filter_records
from query_translation.oql_parser import parse_oql_to_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.url_parser import parse_url_to_oqo
from sources.fields import fields_dict

PARAM = "host_organization_name.search"
ES_FIELD = "host_organization_name.autocomplete"


def _query(value):
    return filter_records(fields_dict, [{PARAM: value}], Search()).to_dict()["query"]


def _fields_queried(node, found=None):
    """Every ES field name a query clause reads (match, match_phrase, query_string default_field)."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, val in node.items():
            if key in ("match", "match_phrase") and isinstance(val, dict):
                found.update(val)
            elif key == "query_string":
                found.add(val.get("default_field"))
            else:
                _fields_queried(val, found)
    elif isinstance(node, list):
        for item in node:
            _fields_queried(item, found)
    return found


def test_registered_as_a_search_filter_on_the_analyzed_subfield():
    field = fields_dict[PARAM]
    assert field.es_field() == ES_FIELD
    assert field.field_type == "search"


def test_a_word_matches_the_host_name_words():
    q = _query("university")
    assert _fields_queried(q) == {ES_FIELD}
    assert '"match": {"host_organization_name.autocomplete": {"query": "university", "operator": "and"}}' in \
        json.dumps(q)


def test_a_wildcard_runs_on_the_unstemmed_subfield():
    # The requester's own spelling (universit* also finds Universität, Università, Universiteit): the
    # subfield is not stemmed, so the literal prefix is in the index and the wildcard is allowed.
    q = _query("universit*")
    assert _fields_queried(q) == {ES_FIELD}
    assert "universit*" in json.dumps(q)


def test_negation_and_or_work_like_other_search_filters():
    neg = _query("!university")
    assert list(neg["bool"]) == ["must_not"]
    assert _fields_queried(neg) == {ES_FIELD}
    either = _query("university|academy")
    assert either["bool"]["minimum_should_match"] == 1
    assert len(either["bool"]["should"]) == 2


def test_oql_word_is_host_organization_name_and_round_trips():
    oqo = parse_url_to_oqo("sources", f"{PARAM}:university")
    assert oqo.to_dict()["filter_rows"] == [{"column_id": PARAM, "value": "university", "operator": "has"}]
    oql = render_oqo_to_oql(oqo)
    assert "host organization name has" in oql
    assert parse_oql_to_oqo(oql).to_dict() == oqo.to_dict()
    parsed = parse_oql_to_oqo("get sources where host organization name has university")
    assert parsed.to_dict()["filter_rows"][0]["column_id"] == PARAM


def test_negated_oql_parses_to_the_negated_filter():
    parsed = parse_oql_to_oqo("get sources where host organization name does not have university")
    assert parsed.to_dict()["filter_rows"] == [
        {"column_id": PARAM, "value": "university", "operator": "has", "is_negated": True}
    ]
