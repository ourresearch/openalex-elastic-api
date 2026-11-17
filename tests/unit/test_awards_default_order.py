"""Awards default to newest start year first (oxjob #2168).

openalex.org/awards sends no sort, so it shows the API's default. Under funded_outputs_count desc, 44 of the
top 50 were blank awards minted from paper funding notes ("HORIZON2020"), which never have a start year; every
award from a funder's own registry has one. Kyle (2026-11-12): start year, newest first; ties by funded outputs
count, then id. A desc sort puts a missing start year last. One list (awards.views.DEFAULT_SORT) serves the
classic /awards view and OQL execution; oql_core names its first key for the sort menu. No ES needed.
"""
from elasticsearch_dsl import Search

import awards.views as awards_views
from awards.fields import fields_dict as awards_fields
from core.shared_view import apply_sorting
from core.utils import map_sort_params
from query_translation import execution
from query_translation import oql_core as C
from query_translation.url_parser import parse_url_to_oqo
from query_translation.x_query import build_x_query

AWARDS_INDEX = "awards-v4"
NEWEST_FIRST = [{"start_year": {"order": "desc"}}, {"funded_outputs_count": {"order": "desc"}}, "id"]


def _params(sort=None, search=None):
    return {"sort": map_sort_params(sort) if sort else None, "search": search, "cursor": None, "sample": None,
            "seed": None, "group_by": None, "group_bys": None, "filters": None, "q": None}


def _es_sort(sort=None, search=None):
    s = apply_sorting(_params(sort, search), awards_fields, awards_views.DEFAULT_SORT, AWARDS_INDEX, Search())
    return s.to_dict()["sort"]


def test_the_default_is_newest_start_year_then_most_funded_outputs_then_id():
    assert awards_views.DEFAULT_SORT == ["-start_year", "-funded_outputs_count", "id"]


def test_the_awards_view_sends_it(monkeypatch, client):
    seen = {}

    def fake_shared_view(request, fields_dict, index_name, default_sort, connection=None):
        seen["default_sort"] = default_sort
        return {}

    monkeypatch.setattr(awards_views, "shared_view", fake_shared_view)
    with client.application.test_request_context("/awards"):
        awards_views.awards()
    assert seen["default_sort"] == ["-start_year", "-funded_outputs_count", "id"]


def test_oql_execution_reads_the_same_list():
    assert execution._resolve_entity("awards", "walden")[2] is awards_views.DEFAULT_SORT
    assert execution._resolve_entity("institutions", "walden")[2] == ["-works_count", "id"]   # unchanged


def test_the_sort_menu_names_its_first_key():
    first = C._THINGS_DEFAULT_SORT["awards"]
    assert (first.column_id, first.direction) == ("start_year", "desc")
    assert "-" + first.column_id == awards_views.DEFAULT_SORT[0]


def test_no_sort_runs_the_default(client):
    assert _es_sort() == NEWEST_FIRST


def test_sort_start_year_desc_runs_the_default(client):
    # the tie-break tail is the default's own keys, so the explicit sort is the default
    assert _es_sort("start_year:desc") == NEWEST_FIRST


def test_sort_funded_outputs_breaks_ties_by_start_year(client):
    assert _es_sort("funded_outputs_count:desc") == [
        {"funded_outputs_count": {"order": "desc"}}, {"start_year": {"order": "desc"}}, "id"]


def test_a_search_still_puts_best_matches_first(client):
    assert _es_sort(search="malaria") == ["_score", "id"]


def _order(sort=None, filters=None):
    xq = build_x_query(parse_url_to_oqo(entity_type="awards", filter_string=filters, sort_string=sort))
    return xq["order"], xq["order_default"]


def test_the_echo_names_the_default():
    assert _order() == ("highest start year first", True)
    assert _order(filters="funder.id:F4320306076") == ("highest start year first", True)
    assert _order(filters="default.search:malaria") == ("best matches first", True)


def test_the_echo_says_an_explicit_sort():
    assert _order("start_year:desc") == ("highest start year first", True)        # runs as the default
    assert _order("funded_outputs_count:desc") == ("highest funded outputs count first", False)
    assert _order("start_year:asc") == ("lowest start year first", False)
    assert _order("amount:desc") == ("highest amount first", False)
