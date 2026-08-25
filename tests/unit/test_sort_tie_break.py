"""Deterministic tie-break for explicit sorts (oxjob #879).

Explicit ?sort= used to end at the user's fields, so tied rows (e.g. all
zero-citation works under sort=cited_by_count:desc) came back in arbitrary
ES internal order. with_tie_break appends a deterministic tail.
"""
from elasticsearch_dsl import Search

from core.shared_view import apply_sorting
from core.sort import WORKS_TIE_BREAK_SORT, with_tie_break
from core.utils import map_sort_params
from works.fields import fields_dict as works_fields_dict

WORKS_DEFAULT_SORT = ["-cited_by_percentile_year.max", "-cited_by_count", "id"]
SOURCES_DEFAULT_SORT = ["-works_count", "id"]


def make_params(sort_args, search=None, cursor=None):
    return {
        "sort": map_sort_params(sort_args) if sort_args else None,
        "search": search,
        "cursor": cursor,
        "sample": None,
        "seed": None,
        "group_by": None,
        "group_bys": None,
        "filters": None,
        "q": None,
    }


# --- pure helper ---

def test_works_tail_appended():
    assert with_tie_break(["-cited_by_count"], WORKS_DEFAULT_SORT, "works-v26") == [
        "-cited_by_count",
        "-publication_date",
        "id",
    ]


def test_score_gets_works_tail():
    assert with_tie_break(["_score"], WORKS_DEFAULT_SORT, "works-v26") == [
        "_score",
        "-publication_date",
        "id",
    ]


def test_dedupe_by_base_field_either_direction():
    # user already sorts on publication_date (asc): only id is appended,
    # and no conflicting -publication_date clause is added
    assert with_tie_break(["publication_date"], WORKS_DEFAULT_SORT, "works-v26") == [
        "publication_date",
        "id",
    ]


def test_sort_containing_id_is_untouched():
    for sf in (["id"], ["-cited_by_count", "id"]):
        assert with_tie_break(sf, WORKS_DEFAULT_SORT, "works-v26") == sf


def test_empty_sort_untouched():
    assert with_tie_break([], WORKS_DEFAULT_SORT, "works-v26") == []


def test_non_works_gets_default_sort_tail():
    assert with_tie_break(["-cited_by_count"], SOURCES_DEFAULT_SORT, "sources-v9") == [
        "-cited_by_count",
        "-works_count",
        "id",
    ]


def test_non_works_dedupes_default_sort_lead():
    assert with_tie_break(["-works_count"], SOURCES_DEFAULT_SORT, "sources-v9") == [
        "-works_count",
        "id",
    ]


def test_tail_constant_ends_in_id():
    assert WORKS_TIE_BREAK_SORT[-1] == "id"


# --- through apply_sorting ---

def test_apply_sorting_explicit_sort_gets_tail(client):
    params = make_params("cited_by_count:desc")
    s = apply_sorting(params, works_fields_dict, WORKS_DEFAULT_SORT, "works-v26", Search())
    assert s.to_dict()["sort"] == [
        {"cited_by_count": {"order": "desc"}},
        {"publication_date": {"order": "desc"}},
        "id",
    ]


def test_apply_sorting_percentile_override_unchanged(client):
    # the cited_by_percentile_year rewrite already ends in id — no extra tail
    params = make_params("cited_by_percentile_year.max:desc")
    s = apply_sorting(params, works_fields_dict, WORKS_DEFAULT_SORT, "works-v26", Search())
    assert s.to_dict()["sort"] == [
        {"cited_by_percentile_year.max": {"order": "desc"}},
        {"cited_by_count": {"order": "desc"}},
        "id",
    ]


def test_apply_sorting_relevance_sort_gets_tail(client):
    params = make_params("relevance_score:desc", search="covid")
    s = apply_sorting(params, works_fields_dict, WORKS_DEFAULT_SORT, "works-v26", Search())
    assert s.to_dict()["sort"] == [
        "_score",
        {"publication_date": {"order": "desc"}},
        "id",
    ]


def test_apply_sorting_cursor_path_unchanged(client):
    params = make_params("cited_by_count:desc", cursor="*")
    s = apply_sorting(params, works_fields_dict, WORKS_DEFAULT_SORT, "works-v26", Search())
    assert s.to_dict()["sort"] == [
        {"cited_by_count": {"order": "desc"}},
        {"cited_by_percentile_year.max": {"order": "desc"}},
        {"cited_by_count": {"order": "desc"}},
        "id",
    ]
