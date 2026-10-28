"""Sorting by a key that can't sort answers a JSON 400, never an Elasticsearch error (oxjob #1900).

Before, sort=cited_by:desc reached Elasticsearch ("No mapping found for [cited_by] in order to
sort on") and the API answered an HTML 500: 169 of 715 registered sort keys did, on 26 entities.
"""
import importlib

import pytest

from core.exceptions import APIQueryParamsError
from core.properties import CAP_SORT, ENTITY_FIELDS_MODULES, ENTITY_PROPERTIES
from core.sort import get_sort_fields


def _fields_dict(entity):
    mod = importlib.import_module(ENTITY_FIELDS_MODULES[entity])
    return getattr(mod, "fields_dict", None) or {f.param: f for f in mod.fields}


ALL_KEYS = [(e, p) for e in ENTITY_FIELDS_MODULES for p in sorted(_fields_dict(e))]


@pytest.mark.parametrize("entity,key", ALL_KEYS)
def test_every_registered_key_sorts_or_refuses_as_the_catalog_says(entity, key):
    """Each key either sorts or raises the 400 error, exactly as /properties publishes it."""
    fields_dict = _fields_dict(entity)
    promised = CAP_SORT in ENTITY_PROPERTIES[entity][key].actions
    if promised:
        path = get_sort_fields(fields_dict, None, {key: "desc"})
        assert len(path) == 1 and path[0].startswith("-") and len(path[0]) > 1
    else:
        with pytest.raises(APIQueryParamsError) as err:
            get_sort_fields(fields_dict, None, {key: "desc"})
        assert f"Cannot sort by {key}" in str(err.value)


@pytest.mark.parametrize("key", ["cited_by", "cites"])
def test_citation_links_suggest_cited_by_count(key):
    with pytest.raises(APIQueryParamsError) as err:
        get_sort_fields(_fields_dict("works"), None, {key: "desc"})
    assert "sort=cited_by_count:desc" in str(err.value)


def test_search_filters_point_to_relevance_score():
    with pytest.raises(APIQueryParamsError) as err:
        get_sort_fields(_fields_dict("works"), None, {"title.search": "desc"})
    assert "relevance_score" in str(err.value)


@pytest.mark.parametrize("entity,key,es_path", [
    ("works", "is_oa", "open_access.is_oa"),
    ("works", "oa_status", "open_access.oa_status"),
    ("works", "openalex_id", "ids.openalex"),
    ("works", "concept.id", "concepts.id"),
    ("works", "primary_location.raw_type", "primary_location.raw_type.keyword"),
    ("authors", "openalex_id", "ids.openalex"),
    ("publishers", "openalex", "ids.openalex"),
    ("concepts", "wikidata_id", "ids.wikidata"),
    ("awards", "doi", "doi.keyword"),
])
def test_keys_that_used_to_500_sort_on_the_stored_field(entity, key, es_path):
    assert get_sort_fields(_fields_dict(entity), None, {key: "asc"}) == [es_path]


def test_is_oa_null_reads_the_stored_field():
    """is_oa:null used the same missing field: it matched every work, and is_oa:!null none."""
    f = _fields_dict("works")["is_oa"]
    f.value = "null"
    assert f.build_query().to_dict() == {"bool": {"must_not": [{"exists": {"field": "open_access.is_oa"}}]}}
