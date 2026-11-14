"""The works default view leaves out pieces of other works (oxjob #2065, step 2). No ES.

hidden = has_parent_work:true AND is_traditional:false, with the core corpus only; a filter whose
KEY is exactly a parent-child column brings the pieces back. No public word for "hidden".

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_default_view.py -q
"""
import logging

import pytest
from elasticsearch_dsl import Search
from flask import Flask

from core.default_view import (HIDDEN_PIECES_KEY, HIDE_PIECES_FILTER, PIECE_FILTER_KEYS, hides_pieces,
                               lifts_hiding, request_filter_keys, request_filter_params, visible_works_query)
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.properties import ENTITY_PROPERTIES
from core.utils import map_filter_params
from core.vector_index import _pop_corpus_clause
from core.work_type_classes import TRADITIONAL_TYPES
from query_translation.execution import _corpus_qs, _hides_pieces
from query_translation.url_parser import parse_url_to_oqo
from query_translation.oqo import OQO
from works.fields import fields_dict

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)

HAS_PARENT = {"exists": {"field": "parent_works.id"}}
TRADITIONAL = {"terms": {"type": sorted(TRADITIONAL_TYPES)}}
VISIBLE = {"bool": {"must_not": [{"bool": {"filter": [HAS_PARENT, {"bool": {"must_not": [TRADITIONAL]}}]}}]}}
CORE = {"term": {"is_xpac": "false"}}


def _filters(filter_params):
    return filter_records(fields_dict, filter_params, Search()).to_dict()["query"]["bool"]["filter"]


# --- the rule ------------------------------------------------------------------------------------
def test_visible_works_are_not_has_parent_and_not_traditional():
    assert visible_works_query().to_dict() == VISIBLE


def test_the_rule_is_made_of_the_two_public_filters_own_queries():
    """corpus=all minus `has_parent_work:true,is_traditional:false` reproduces the hidden set."""
    hidden = _filters([{"has_parent_work": "true"}, {"is_traditional": "false"}])
    assert VISIBLE == {"bool": {"must_not": [{"bool": {"filter": hidden}}]}}


def test_no_public_word_for_hidden():
    assert HIDDEN_PIECES_KEY not in fields_dict
    assert HIDDEN_PIECES_KEY not in ENTITY_PROPERTIES["works"]
    assert not any("hidden" in key or "hide" in key for key in fields_dict)
    for spelling in (HIDDEN_PIECES_KEY, HIDDEN_PIECES_KEY.replace("_", "-", 1), "-default.hide-pieces"):
        with pytest.raises(APIQueryParamsError) as err:
            map_filter_params(f"type:article,{spelling}:true")
        assert "is not a valid field" in str(err.value)
    assert request_filter_params(f"{HIDDEN_PIECES_KEY}:false") == []  # the view answers the 400


def test_the_server_side_default_filters_as_the_rule_beside_the_corpus():
    assert _filters([{"is_xpac": "false"}, HIDE_PIECES_FILTER, {"type": "dataset"}]) == [
        CORE, VISIBLE, {"term": {"type.lower": "dataset"}}]


# --- opt-in: exact keys only ---------------------------------------------------------------------
@pytest.mark.parametrize("filter_string", [
    "lineage:W1", "lineage:!W1", "lineage:W1|W2", "type:article,lineage:W1",
    "has_parent_work:true", "has_parent_work:false", "has-parent-work:true",
    "parent_works.id:W1", "parent_works.id:!W1|W2", "parent-works.id:W1",
    "parent_works.relationship:component", "parent_works.relationship:!volume",
])
def test_a_parent_child_filter_lifts_the_rule(filter_string):
    assert lifts_hiding(request_filter_keys(filter_string))
    assert not hides_pieces(None, False, request_filter_params(filter_string))
    assert not hides_pieces("core", False, request_filter_params(filter_string))


@pytest.mark.parametrize("filter_string", [
    "authorships.institutions.lineage:I123",
    "institution_assertions.lineage:I123",
    "primary_location.source.host_organization_lineage:P1",
    "locations.source.host_institution_lineage:I123",
    "locations.source.publisher_lineage:P1",
    "is_traditional:false", "is_traditional:true", "type:dataset", "child_works_count:>0",
    "title.search:lineage", "display_name.search:has_parent_work", "doi:10.1/lineage:W1",
    "",
])
def test_no_other_filter_lifts_it(filter_string):
    assert not lifts_hiding(request_filter_keys(filter_string))
    assert hides_pieces(None, False, request_filter_params(filter_string))


def test_the_opt_in_keys_are_the_four_parent_child_filters():
    assert PIECE_FILTER_KEYS == {"has_parent_work", "parent_works.id", "parent_works.relationship", "lineage"}
    assert PIECE_FILTER_KEYS <= set(fields_dict)


# --- corpus --------------------------------------------------------------------------------------
@pytest.mark.parametrize("corpus,include_xpac,filter_string,hides", [
    (None, False, "", True),                       # the /works default
    ("core", False, "", True),
    ("CORE", False, "type:book", True),
    ("all", False, "", False),                     # both back: expansion works and hidden pieces
    ("expansion", False, "", False),               # unchanged: is_xpac:true only
    (None, True, "", False),                       # legacy include_xpac=true means corpus=all
    (None, False, "is_xpac:true", False),          # legacy spelling of corpus=expansion
    (None, False, "is_xpac:false", True),          # legacy spelling of corpus=core
    ("core", False, "lineage:W1", False),
])
def test_the_rule_rides_with_the_core_corpus(corpus, include_xpac, filter_string, hides):
    assert hides_pieces(corpus, include_xpac, request_filter_params(filter_string)) is hides


# --- the OQO executor mirrors the REST view ------------------------------------------------------
def _oqo_qs(url_filter="", corpus=None, args=""):
    oqo = parse_url_to_oqo("works", filter_string=url_filter or None, corpus=corpus)
    with Flask(__name__).test_request_context("/" + args):
        return [q.to_dict() for q in _corpus_qs(oqo, "walden")]


def test_oqo_default_is_core_and_visible():
    assert _oqo_qs() == [CORE, VISIBLE]
    assert _oqo_qs("type:dataset") == [CORE, VISIBLE]
    assert _oqo_qs(corpus="core") == [CORE, VISIBLE]


def test_oqo_corpus_all_and_expansion():
    assert _oqo_qs(corpus="all") == []
    assert _oqo_qs(corpus="expansion") == [{"term": {"is_xpac": "true"}}]
    assert _oqo_qs(args="?include_xpac=true") == []


@pytest.mark.parametrize("url_filter", ["lineage:W3109397498", "lineage:!W3109397498", "has_parent_work:true",
                                        "parent_works.id:W3109397498|W2741809807",
                                        "parent_works.relationship:component"])
def test_oqo_parent_child_filter_lifts_only_the_rule(url_filter):
    assert _oqo_qs(url_filter) == [CORE]  # the corpus stays


@pytest.mark.parametrize("url_filter", ["authorships.institutions.lineage:I27837315", "is_traditional:false",
                                        "child_works_count:>0"])
def test_oqo_other_filters_do_not_lift_it(url_filter):
    assert _oqo_qs(url_filter) == [CORE, VISIBLE]


def test_oqo_nested_leaf_lifts_it():
    oqo = OQO.from_dict({"get_rows": "works", "filter_rows": [
        {"column_id": "type", "value": "dataset"},
        {"join": "or", "filters": [
            {"column_id": "publication_year", "value": 2024},
            {"join": "and", "filters": [{"column_id": "lineage", "value": "W3109397498", "is_negated": True}]},
        ]},
    ]})
    nested_other = OQO.from_dict({"get_rows": "works", "filter_rows": [
        {"join": "or", "filters": [{"column_id": "authorships.institutions.lineage", "value": "I27837315"},
                                   {"column_id": "is_traditional", "value": False}]}]})
    with Flask(__name__).test_request_context("/"):
        assert not _hides_pieces(oqo, "walden")
        assert _hides_pieces(nested_other, "walden")
        # a walk back to works from another entity: that entity's own `lineage` is not the works column
        institutions = OQO.from_dict({"get_rows": "institutions",
                                      "filter_rows": [{"column_id": "lineage", "value": "I27837315"}]})
        from dataclasses import replace
        assert _hides_pieces(replace(institutions, get_rows="works"), "walden", works_filters=False)


def test_only_works_have_the_rule():
    with Flask(__name__).test_request_context("/"):
        assert _corpus_qs(OQO.from_dict({"get_rows": "authors"}), "walden") == []


# --- semantic search: checked on the works index with the corpus --------------------------------
def test_vector_path_checks_the_rule_on_the_works_index():
    params = {"filters": [{"is_xpac": "false"}, HIDE_PIECES_FILTER, {"type": "article"}]}
    assert _pop_corpus_clause(params) == {"bool": {"filter": [CORE, VISIBLE]}}
    assert params["filters"] == [{"type": "article"}]  # the vector index never sees the internal key
