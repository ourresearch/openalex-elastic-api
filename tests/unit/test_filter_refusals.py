"""Every filter queries a field the index has, or answers a JSON 400: never a silent 0 (oxjob #1901).

Before, 24 of 670 testable filters failed on the live API: 19 answered 0 for a value taken from a
real record (topics_count:>2, sources is_in_jstage:true, authors scopus:..., awards
lead_investigator.family_name:Hayashi, primary_location.raw_type:journal-article...) and 5 answered
an HTML 500 on a full topic URL. scripts/filter_sweep.py measures it live; the offline half runs here.
"""
import importlib
import json
import os

import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.properties import ENTITY_FIELDS_MODULES
from scripts.filter_sweep import index_field_problems, render


def _fields_dict(entity):
    mod = importlib.import_module(ENTITY_FIELDS_MODULES[entity])
    return getattr(mod, "fields_dict", None) or {f.param: f for f in mod.fields}


def _query(entity, param, value):
    return render(_fields_dict(entity)[param], value)


REFUSED = [(e, p) for e in ENTITY_FIELDS_MODULES for p, f in sorted(_fields_dict(e).items()) if f.filter_refusal]


def test_every_filter_queries_fields_the_index_has():
    """The registry against docs/index-fields.json (the live indexes' fields; refresh it after a
    rebuild with scripts/filter_sweep.py --write-index-fields)."""
    assert index_field_problems() == []


def test_the_refused_filters_are_the_ones_with_no_stored_value():
    assert set(REFUSED) == {
        ("works", "topics_count"),
        ("authors", "scopus"),
        ("institutions", "concept.id"), ("institutions", "concepts.id"), ("institutions", "x_concepts.id"),
        ("sources", "is_in_jstage"), ("sources", "is_in_jstage_since_year"),
        ("concepts", "summary_stats.2yr_mean_citedness"), ("concepts", "summary_stats.h_index"),
        ("concepts", "summary_stats.i10_index"),
    }


@pytest.mark.parametrize("entity,param", REFUSED)
def test_a_refused_filter_answers_a_400_on_every_path_and_leaves_the_catalog(entity, param):
    fields_dict = _fields_dict(entity)
    for value in ("5", "1|2", "!5"):  # one value, an OR list, a negation
        with pytest.raises(APIQueryParamsError) as err:
            filter_records(fields_dict, [{param: value}], Search())
        assert f"{param} can't be used as a filter" in str(err.value)
    field = fields_dict[param]
    assert field.unlisted and not field.sortable
    snapshot = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "properties-snapshot.json")
    with open(snapshot) as fh:
        assert param not in json.load(fh)["properties"][entity]


def test_topics_count_points_to_topic_filters():
    with pytest.raises(APIQueryParamsError) as err:
        filter_records(_fields_dict("works"), [{"topics_count": ">2"}], Search())
    assert "topics.id:!null" in str(err.value)


@pytest.mark.parametrize("entity", ["authors", "institutions", "sources"])
@pytest.mark.parametrize("param", ["topics.id", "topic_share.id"])
@pytest.mark.parametrize("value", ["T10109", "t10109", "https://openalex.org/T10109", "https://openalex.org/t10109"])
def test_a_topic_id_in_any_spelling_queries_the_stored_url(entity, param, value):
    """A full topic URL left the query unset: an HTML 500 on authors, institutions and sources."""
    ((_, stored),) = _query(entity, param, value)["term"].items()
    assert stored == "https://openalex.org/T10109"
    # and its negation excludes that topic (the bare T<n> matched nothing, so !T<n> excluded nothing)
    ((_, stored),) = _query(entity, param, "!" + value)["bool"]["must_not"][0]["term"].items()
    assert stored == "https://openalex.org/T10109"


@pytest.mark.parametrize("value", ["10.3030/649261", "https://doi.org/10.3030/649261",
                                   "http://dx.doi.org/10.3030/649261", "HTTPS://DOI.ORG/10.3030/649261"])
def test_an_award_doi_matches_every_stored_spelling(value):
    """Awards keep each funder's spelling (https://doi.org/, http://dx.doi.org/, bare; 13,585 with
    capitals). A term on the `doi` text field never matched a whole DOI."""
    should = _query("awards", "doi", value)["bool"]["should"]
    assert {c["term"]["doi.keyword"]["value"] for c in should} == {
        "10.3030/649261", "https://doi.org/10.3030/649261", "http://dx.doi.org/10.3030/649261"}
    assert all(c["term"]["doi.keyword"]["case_insensitive"] for c in should)


def test_an_award_doi_or_list_matches_each_doi():
    q = filter_records(_fields_dict("awards"), [{"doi": "10.1/a|10.2/B"}], Search()).to_dict()
    assert json.dumps(q).count('"case_insensitive": true') == 6


@pytest.mark.parametrize("param", ["lead_investigator.family_name", "lead_investigator.given_name",
                                   "lead_investigator.affiliation.name"])
def test_lead_investigator_names_match_as_a_phrase(param):
    """Text fields with no keyword copy: family_name:Hayashi was a term on "Hayashi" against the
    indexed word "hayashi" and answered 0 (users sent it)."""
    assert _query("awards", param, "Hayashi") == {"match_phrase": {param: "Hayashi"}}
    assert _query("awards", param, "!Hayashi") == {"bool": {"must_not": [{"match_phrase": {param: "Hayashi"}}]}}
    assert _query("awards", param, "null") == {"bool": {"must_not": [{"exists": {"field": param}}]}}


@pytest.mark.parametrize("entity,param,value,expected", [
    ("works", "primary_location.raw_type", "journal-article", {"term": {"primary_location.raw_type.keyword": "journal-article"}}),
    ("works", "best_oa_location.raw_type", "Article", {"term": {"best_oa_location.raw_type.keyword": "Article"}}),
    ("works", "locations.raw_type", "Dataset", {"term": {"locations_full.raw_type.keyword": "Dataset"}}),
    ("publishers", "openalex", "P4310320990", {"term": {"ids.openalex.lower": "https://openalex.org/P4310320990"}}),
    ("authors", "topic_share.id", "T10109", {"term": {"topic_share.id": "https://openalex.org/T10109"}}),
])
def test_filters_read_the_field_the_index_has(entity, param, value, expected):
    assert _query(entity, param, value) == expected


@pytest.mark.parametrize("entity,param", [(e, p) for e in ("authors", "sources", "institutions")
                                          for p in ("topics.id", "topic_share.id")])
@pytest.mark.parametrize("value", ["T11672", "t11672", "https://openalex.org/T11672"])
def test_topic_filters_take_every_id_form(entity, param, value):
    """oxjob #1907: a full topic URL left the query unset; Sentry OPENALEX-ELASTIC-API-9 caught 190 HTTP 500s
    (UnboundLocalError 'q'), all /authors or /sources?filter=topics.id:https://openalex.org/T<n>. Fixed by #1901."""
    assert "https://openalex.org/T11672" in json.dumps(_query(entity, param, value))
    assert "must_not" in json.dumps(_query(entity, param, "!" + value))


@pytest.mark.parametrize("entity,param", REFUSED)
def test_a_refused_filter_refuses_group_by_and_sort_with_the_same_reason(entity, param):
    from core.sort import sort_refusal
    from core.validate import group_by_rejection

    field = _fields_dict(entity)[param]
    assert group_by_rejection(field) == f"Cannot group by {param}: {field.filter_refusal}"
    assert sort_refusal(param, field) == f"Cannot sort by {param}: {field.filter_refusal}"
