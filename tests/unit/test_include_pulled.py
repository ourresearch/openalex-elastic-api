"""The works default view leaves out pulled works; include_pulled=true brings them back (oxjob #2264).

Jason, 15 Nov 2026 (oxjobs plans/retractions.md § 5, decisions 3-4a; kept 16 Nov): hidden from every works list,
search, count and group_by whatever the corpus; a filter naming is_pulled or is_retracted redirects to the same URL
with include_pulled=true (parameters add works, filters subtract); /works/W... always answers.
"""
import logging
from dataclasses import replace

import pytest
from elasticsearch_dsl import Search
from flask import Flask
from flask import request as flask_request

from autocomplete.validate import validate_entity_autocomplete_params, validate_full_autocomplete_params
from core.default_view import (HIDDEN_PULLED_KEY, HIDE_PULLED_FILTER, PULLED_PARAMS, default_view_query,
                               hides_pulled, include_pulled_param, names_pulled, not_pulled_query,
                               pulled_redirect_location)
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.utils import map_filter_params
from core.validate import validate_params
from core.vector_index import _pop_corpus_clause
from query_translation.execution import _corpus_qs, _hides_pulled
from query_translation.oqo import OQO
from query_translation.url_parser import parse_url_to_oqo
from works.fields import fields_dict

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)

NOT_PULLED = {"bool": {"must_not": [{"term": {"is_pulled": "true"}}]}}
CORE = {"term": {"is_xpac": "false"}}
VISIBLE = {"bool": {"must_not": [{"term": {"is_non_traditional_child": True}}]}}


def _args(query=""):
    with Flask(__name__).test_request_context("/works" + query):
        return flask_request.args.copy()


# --- the rule ------------------------------------------------------------------------------------

def test_not_pulled_is_what_the_public_filter_false_matches():
    assert not_pulled_query().to_dict() == NOT_PULLED
    assert fields_dict["is_pulled"].query_for("false").to_dict() == NOT_PULLED


def test_server_side_filter_applies_it():
    q = filter_records(fields_dict, [{"type": "article"}, HIDE_PULLED_FILTER], Search()).to_dict()["query"]
    assert NOT_PULLED in q["bool"]["filter"]


def test_a_request_cannot_name_the_internal_key():
    with pytest.raises(APIQueryParamsError, match="not a valid field"):
        map_filter_params(f"{HIDDEN_PULLED_KEY}:false")


@pytest.mark.parametrize("query, hides", [
    ("", True), ("?corpus=all", True), ("?corpus=expansion", True), ("?include_xpac=true", True),
    ("?include_parts=true", True),                       # one switch per kind (decision 4a)
    ("?include_pulled=true", False), ("?include-pulled=TRUE", False), ("?include_pulled=false", True),
])
def test_only_include_pulled_brings_them_back(query, hides):
    assert hides_pulled(_args(query), []) is hides


@pytest.mark.parametrize("value", ["banana", "yes", "1"])
def test_include_pulled_takes_true_or_false(value):
    with pytest.raises(APIQueryParamsError, match="include_pulled=true brings back"):
        include_pulled_param(_args(f"?include_pulled={value}"))


@pytest.mark.parametrize("filter_params, hides", [
    ([{"is_retracted": "true"}], False), ([{"is_retracted": "false"}], False), ([{"is_pulled": "true"}], False),
    ([{"is-pulled": "false"}], False), ([{"type": "article"}], True), ([{"is_paratext": "true"}], True),
])
def test_a_filter_naming_the_field_brings_them_back_where_nothing_redirects(filter_params, hides):
    assert hides_pulled(_args(), filter_params) is hides


def test_explicit_include_pulled_false_beats_the_filter():
    # parameters add, filters subtract: include_pulled=false keeps them out; is_retracted:true then finds none
    assert hides_pulled(_args("?include_pulled=false"), [{"is_retracted": "true"}])


def test_names_pulled_matches_whole_keys():
    assert names_pulled(["is_retracted"]) and names_pulled(["is-pulled"])
    assert not names_pulled(["is_retracted_title_only", "type", "is_paratext"])


# --- the redirect --------------------------------------------------------------------------------

@pytest.mark.parametrize("query, location", [
    ("filter=is_retracted:true", "/works?filter=is_retracted:true&include_pulled=true"),
    ("filter=type:article,is_pulled:false&per_page=5", "/works?filter=type:article,is_pulled:false&per_page=5&include_pulled=true"),
    ("filter=is-retracted:true", "/works?filter=is-retracted:true&include_pulled=true"),
    ("filter=type:article", None),
    ("search=kelp", None),
    ("filter=is_retracted:true&include_pulled=true", None),
    ("filter=is_retracted:true&include_pulled=false", None),   # the parameter decides; no loop, no override
    ("group_by=is_retracted", "/works?group_by=is_retracted&include_pulled=true"),   # a group_by asks about them too
    ("group-by=is_pulled:include_unknown", "/works?group-by=is_pulled:include_unknown&include_pulled=true"),
    ("group_by=type", None),
    ("group_bys=type,is_retracted", None),   # the website's batched facets describe the results as they stand
])
def test_redirect_location(query, location):
    assert pulled_redirect_location("/works", query, _args("?" + query)) == location


def test_redirect_refuses_a_bad_include_pulled():
    with pytest.raises(APIQueryParamsError):
        pulled_redirect_location("/works", "filter=is_retracted:true&include_pulled=maybe",
                                 _args("?filter=is_retracted:true&include_pulled=maybe"))


def test_redirect_is_relative():
    loc = pulled_redirect_location("/v2/works", "filter=is_pulled:true", _args("?filter=is_pulled:true"))
    assert loc.startswith("/v2/works?")


# --- the doors -----------------------------------------------------------------------------------

def test_base_query_doors_combine_both_rules():
    assert default_view_query(False, False) is None
    assert default_view_query(False, True).to_dict() == NOT_PULLED
    assert default_view_query(True, True).to_dict() == {"bool": {"filter": [VISIBLE, NOT_PULLED]}}


def test_filters_and_stats_doors():
    from works.views import _default_view_query
    with Flask(__name__).test_request_context("/works/filters/type:dataset"):
        assert _default_view_query("type:dataset").to_dict() == {"bool": {"filter": [VISIBLE, NOT_PULLED]}}
        assert _default_view_query("type:dataset,is_retracted:true").to_dict() == VISIBLE
    with Flask(__name__).test_request_context("/works/stats/?include_pulled=true&include_parts=true"):
        assert _default_view_query("type:dataset") is None


def test_works_accept_include_pulled_other_entities_refuse_it():
    with Flask(__name__).test_request_context("/works?include_pulled=true"):
        validate_params(flask_request, ("corpus", "rerank") + PULLED_PARAMS)
    with Flask(__name__).test_request_context("/authors?include_pulled=true"):
        with pytest.raises(APIQueryParamsError, match="is not a valid parameter"):
            validate_params(flask_request)


def test_autocomplete_accepts_the_parameter():
    for path in ("/autocomplete/works?q=kelp&include_pulled=true", "/autocomplete?q=kelp&include-pulled=true"):
        with Flask(__name__).test_request_context(path):
            validate_entity_autocomplete_params(flask_request)
            validate_full_autocomplete_params(flask_request)


def _oqo_qs(url_filter="", corpus=None, args=""):
    oqo = parse_url_to_oqo("works", filter_string=url_filter or None, corpus=corpus)
    with Flask(__name__).test_request_context("/" + args):
        return [q.to_dict() for q in _corpus_qs(oqo, "walden")]


def test_oqo_hides_them_whatever_the_corpus():
    assert _oqo_qs() == [CORE, VISIBLE, NOT_PULLED]
    assert _oqo_qs(corpus="all") == [NOT_PULLED]
    assert _oqo_qs(corpus="expansion") == [{"term": {"is_xpac": "true"}}, NOT_PULLED]


def test_oqo_include_pulled_and_the_filter_shortcut():
    assert _oqo_qs(args="?include_pulled=true") == [CORE, VISIBLE]
    assert _oqo_qs("is_retracted:true") == [CORE, VISIBLE]
    assert _oqo_qs("is_pulled:false") == [CORE, VISIBLE]
    assert _oqo_qs("is_retracted:true", args="?include_pulled=false") == [CORE, VISIBLE, NOT_PULLED]


def test_oqo_a_split_or_measure_naming_the_field_brings_them_back():
    """`percent retracted of works in Heliyon by year` (the OQL docs' example) needs the retracted works counted."""
    percent = OQO.from_dict({"get_rows": "works", "group_by": [{"column_id": "publication_year"}],
                             "calculate": [{"measure": "percent", "column_id": "is_retracted"}]})
    by_pulled = OQO.from_dict({"get_rows": "works", "group_by": [{"column_id": "is_pulled"}]})
    plain = OQO.from_dict({"get_rows": "works", "group_by": [{"column_id": "publication_year"}],
                           "calculate": [{"measure": "count"}]})
    with Flask(__name__).test_request_context("/"):
        assert not _hides_pulled(percent, "walden")
        assert not _hides_pulled(by_pulled, "walden")
        assert _hides_pulled(plain, "walden")
    with Flask(__name__).test_request_context("/?include_pulled=false"):
        assert _hides_pulled(percent, "walden")


def test_oqo_only_works_on_walden():
    with Flask(__name__).test_request_context("/"):
        assert _corpus_qs(OQO.from_dict({"get_rows": "authors"}), "walden") == []
        assert not _hides_pulled(OQO.from_dict({"get_rows": "works"}), "default")


def test_oqo_walk_back_from_another_entity_hides_them():
    institutions = OQO.from_dict({"get_rows": "institutions", "filter_rows": []})
    with Flask(__name__).test_request_context("/"):
        assert _hides_pulled(replace(institutions, get_rows="works"), "walden", works_filters=False)
    with Flask(__name__).test_request_context("/?include_pulled=true"):
        assert not _hides_pulled(replace(institutions, get_rows="works"), "walden", works_filters=False)


def test_vector_path_checks_it_on_the_works_index():
    params = {"filters": [{"is_xpac": "false"}, HIDE_PULLED_FILTER, {"type": "article"}]}
    assert _pop_corpus_clause(params) == {"bool": {"filter": [CORE, NOT_PULLED]}}
    assert params["filters"] == [{"type": "article"}]


# --- a lookup by identifier answers (oxjob #2264 rule 2; #1857 wave 26) ------------------------------

@pytest.mark.parametrize("url_filter", [
    "doi:10.4049/jimmunol.169.8.4594", "doi:https://doi.org/10.1234/a|10.5555/b", "pmid:12370398", "ids.pmid:12370398",
    "openalex:W1880712911", "ids.openalex:W1|W2", "openalex_id:W1", "pmcid:PMC1", "ids.pmcid:PMC1",
    "arxiv:2101.00001", "ids.arxiv:2101.00001v2", "arxiv:hep-th/9901001", "mag:2117847125", "ids.mag:2117847125",
    "openalex:https://openalex.org/W1", "pmcid:pmc123", "doi:doi:10.1234/a",
    "doi:10.1234/a,publication_year:2020",         # still bounded to the named works
    "doi:10.1234/a,doi:!10.2/b",
])
def test_an_identifier_filter_brings_its_pulled_works_back(url_filter):
    assert not hides_pulled(_args(), map_filter_params(url_filter))
    assert _oqo_qs(url_filter) == [CORE, VISIBLE]


@pytest.mark.parametrize("url_filter", [
    "doi:!10.1/a",                                 # everything but one work
    "doi:null", "doi:!null", "pmid:unknown",       # has or lacks one: a set, not a lookup
    "doi:10.1234/a|!10.2/b",
    'doi:" null "', 'doi:" !10.1234/a "', "doi:*", "doi:true", "doi:https://doi.org/", "doi:null+10.1234/a",
    "pmid:>0", "pmid:1-99", "mag:>5", "openalex:W1x",  # not an id's shape: fail closed
    "doi_starts_with:10.1016",                     # a prefix is a search
    "publication_year:2020", "has_doi:true",
])
def test_other_identifier_filters_keep_the_hiding(url_filter):
    assert hides_pulled(_args(), map_filter_params(url_filter))
    assert _oqo_qs(url_filter) == [CORE, VISIBLE, NOT_PULLED]


def test_include_pulled_false_beats_an_identifier_filter():
    assert hides_pulled(_args("?include_pulled=false"), map_filter_params("doi:10.1234/a"))
    assert _oqo_qs("doi:10.1234/a", args="?include_pulled=false") == [CORE, VISIBLE, NOT_PULLED]


def test_an_identifier_filter_does_not_redirect():
    assert pulled_redirect_location("/works", "filter=doi:10.1234/a", _args("?filter=doi:10.1234/a")) is None


def test_oqo_an_or_with_another_column_keeps_the_hiding():
    either = OQO.from_dict({"get_rows": "works", "filter_rows": [{"join": "or", "filters": [
        {"column_id": "doi", "value": "10.1234/a"}, {"column_id": "publication_year", "value": 2020}]}]})
    only_ids = OQO.from_dict({"get_rows": "works", "filter_rows": [{"join": "or", "filters": [
        {"column_id": "doi", "value": "10.1234/a"}, {"column_id": "ids.pmid", "value": 123}]}]})
    and_with_id = OQO.from_dict({"get_rows": "works", "filter_rows": [{"join": "and", "filters": [
        {"column_id": "publication_year", "value": 2020}, {"column_id": "ids.openalex", "value": "W1"}]}]})
    negated = OQO.from_dict({"get_rows": "works", "filter_rows": [
        {"column_id": "doi", "value": "10.1234/a", "is_negated": True}]})
    not_an_id = OQO.from_dict({"get_rows": "works", "filter_rows": [{"column_id": "doi", "value": "null"}]})
    nested = OQO.from_dict({"get_rows": "works", "filter_rows": [
        {"column_id": "ids.openalex", "value": {"get_rows": "works", "filter_rows": [
            {"column_id": "publication_year", "value": 2020}]}}]})
    with Flask(__name__).test_request_context("/"):
        assert _hides_pulled(either, "walden")
        assert not _hides_pulled(only_ids, "walden")
        assert not _hides_pulled(and_with_id, "walden")
        assert _hides_pulled(negated, "walden")
        assert _hides_pulled(not_an_id, "walden")
        assert _hides_pulled(nested, "walden")
        # a walk back from another entity: its filters are not works ids
        assert _hides_pulled(only_ids, "walden", works_filters=False)
